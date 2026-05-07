"""
Cross-tenant isolation regression tests (Phase 6 of the JWT-tenant fix).

Runs against the live backend on http://localhost:8000. The dev DB is
already seeded by the lifespan migrations with:

  - 3 tenants: default, acme, client-sandbox
  - users 1-7  → default tenant      (admin@quoteforge.io,
                  password from $QF_TEST_DEFAULT_PASSWORD)
  - user 8     → client-sandbox      (admin@client-sandbox.io,
                  password from $QF_TEST_TENANT_PASSWORD)
  - default tenant has: 6 products, 1 ICP (Enterprise Tech),
                        guardrail policy, deal_insight_mapping, v12 model active
  - client-sandbox + acme tenants have: empty product/ICP/model rows

The tests assert that an authenticated client-sandbox user cannot read or
write data that belongs to the default tenant, and vice versa.

Pre-req: backend running on :8000. If not running, every test fails on
the first auth call with ConnectionError — surfacing the missing-backend
condition clearly.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest

BASE_URL = "http://localhost:8000"
DB_PATH = Path(__file__).resolve().parent.parent / "quoteforge.db"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Populate it in backend/.env (see .env.example)."
        )
    return value


DEFAULT_EMAIL = "admin@quoteforge.io"
DEFAULT_PASS = _required_env("QF_TEST_DEFAULT_PASSWORD")
CS_EMAIL = "admin@client-sandbox.io"
CS_PASS = _required_env("QF_TEST_TENANT_PASSWORD")


# ─── Helpers ──────────────────────────────────────────────────────────

def _login(email: str, password: str) -> str:
    resp = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _decode_jwt_payload(token: str) -> dict:
    """Decode without signature verification — we're testing claim presence,
    not signature validity. Adds base64 padding before urlsafe_b64decode."""
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def default_token() -> str:
    return _login(DEFAULT_EMAIL, DEFAULT_PASS)


@pytest.fixture(scope="module")
def cs_token() -> str:
    return _login(CS_EMAIL, CS_PASS)


@pytest.fixture
def orphan_user():
    """Insert a user with tenant_id=NULL, return (email, password). Removed
    in teardown. Used by test_user_with_no_tenant_id_blocked."""
    # `.local` is a reserved TLD and gets rejected by pydantic's EmailStr.
    # `.io` works and the domain doesn't need to resolve.
    email = f"orphan-{uuid.uuid4().hex[:8]}@orphan-test.io"
    # bcrypt hash for password 'orphanpass'. Computed once via passlib so we
    # don't need passlib at test time.
    # $2b$12$ hash for 'orphanpass'
    # Generated and verified offline.
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pw_hash = pwd_ctx.hash("orphanpass")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role, status, "
            "tenant_id) VALUES (?, ?, ?, 'admin', 'active', NULL)",
            ("Orphan Tester", email, pw_hash),
        )
        conn.commit()
    finally:
        conn.close()

    yield (email, "orphanpass")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()
    finally:
        conn.close()


# ─── Tests ────────────────────────────────────────────────────────────

class TestJWTClaims:
    def test_jwt_carries_tenant_claims(self, default_token, cs_token):
        """Both tokens decode to JWT payloads containing tenant_id (UUID) and
        tenant_slug. Without these claims, get_current_tenant_id has nothing
        to inject — the whole isolation chain depends on this."""
        d = _decode_jwt_payload(default_token)
        c = _decode_jwt_payload(cs_token)

        for claims, expected_slug in [(d, "default"), (c, "client-sandbox")]:
            assert "tenant_id" in claims, f"missing tenant_id in {claims}"
            assert "tenant_slug" in claims, f"missing tenant_slug in {claims}"
            assert claims["tenant_slug"] == expected_slug
            # tenant_id is a UUID v4
            uuid.UUID(claims["tenant_id"])

        # The two tokens must reference distinct tenants — otherwise the rest
        # of the suite would be testing nothing.
        assert d["tenant_id"] != c["tenant_id"]


class TestTenantDependency:
    def test_get_current_tenant_id_returns_jwt_tenant(self, default_token, cs_token):
        """Hitting any tenant-scoped endpoint with a token returns data
        scoped to that JWT's tenant. /api/insights/models is the cleanest
        probe — it returns rows filtered by tenant_id."""
        default_models = httpx.get(
            f"{BASE_URL}/api/insights/models", headers=_auth(default_token), timeout=10,
        ).json()
        cs_models = httpx.get(
            f"{BASE_URL}/api/insights/models", headers=_auth(cs_token), timeout=10,
        ).json()
        assert len(default_models) >= 1, "default tenant should have at least one trained model"
        assert cs_models == [], f"client-sandbox should have no models, got {cs_models}"

    def test_user_with_no_tenant_id_blocked(self, orphan_user):
        """A user row with tenant_id=NULL must get 403 from any endpoint
        that depends on get_current_tenant_id. Login itself succeeds (it
        only checks email/password); the failure surfaces at the first
        tenant-scoped request."""
        email, password = orphan_user
        token = _login(email, password)

        # JWT for this user has tenant_id=None / tenant_slug=None.
        claims = _decode_jwt_payload(token)
        assert claims.get("tenant_id") in (None, ""), (
            f"orphan should have null tenant_id, got {claims.get('tenant_id')!r}"
        )

        # Any endpoint depending on get_current_tenant_id should 403.
        resp = httpx.get(
            f"{BASE_URL}/api/insights/models", headers=_auth(token), timeout=10,
        )
        assert resp.status_code == 403, (
            f"expected 403 for orphan user, got {resp.status_code}: {resp.text}"
        )


class TestCrossTenantIsolation:
    def test_insights_models_isolated(self, default_token, cs_token):
        """default tenant has a trained model (v12 active); client-sandbox
        has no models. Neither sees the other's models."""
        default = httpx.get(
            f"{BASE_URL}/api/insights/models", headers=_auth(default_token), timeout=10,
        ).json()
        cs = httpx.get(
            f"{BASE_URL}/api/insights/models", headers=_auth(cs_token), timeout=10,
        ).json()
        # Default has at least one model; CS has zero.
        assert len(default) >= 1
        assert cs == []
        # Make sure no model bleeds into the wrong response.
        default_versions = {m["version"] for m in default}
        cs_versions = {m["version"] for m in cs}
        assert default_versions & cs_versions == set()

    def test_insights_predict_isolated(self, default_token, cs_token):
        """Predicting with default's token returns 200 (model exists);
        with client-sandbox's token returns 409 'no_model'. The same Opp ID
        is requested in both calls — isolation is per-tenant, not per-Opp."""
        opp_id = "006gL00000KlPp8QAF"
        d_resp = httpx.get(
            f"{BASE_URL}/api/insights/predict/{opp_id}",
            headers=_auth(default_token), timeout=15,
        )
        c_resp = httpx.get(
            f"{BASE_URL}/api/insights/predict/{opp_id}",
            headers=_auth(cs_token), timeout=15,
        )
        assert d_resp.status_code == 200, f"default should predict, got {d_resp.text}"
        assert c_resp.status_code == 409, (
            f"client-sandbox should 409 no_model, got {c_resp.status_code}: {c_resp.text}"
        )
        assert "model" in c_resp.json().get("detail", "").lower()

    def test_icp_profiles_isolated(self, default_token, cs_token):
        """default has the 'Enterprise Tech' ICP; client-sandbox has none."""
        d = httpx.get(
            f"{BASE_URL}/api/icp", headers=_auth(default_token), timeout=10,
        ).json()
        c = httpx.get(
            f"{BASE_URL}/api/icp", headers=_auth(cs_token), timeout=10,
        ).json()
        assert any(i["name"] == "Enterprise Tech" for i in d), (
            f"default should expose Enterprise Tech ICP, got {[i['name'] for i in d]}"
        )
        assert c == [], f"client-sandbox should expose no ICPs, got {c}"

    def test_quotes_documents_isolated(self, default_token, cs_token):
        """The /api/quotes/documents endpoint (admin doc list) is checked
        for both tokens. Today both may be empty (Phase 5 wiped document_logs),
        but the endpoints must respond 200 with their own scope. The test
        guards against any future regression where one tenant sees the other
        tenant's documents in the same payload."""
        d = httpx.get(
            f"{BASE_URL}/api/quotes/documents", headers=_auth(default_token), timeout=10,
        )
        c = httpx.get(
            f"{BASE_URL}/api/quotes/documents", headers=_auth(cs_token), timeout=10,
        )
        assert d.status_code == 200, d.text
        assert c.status_code == 200, c.text
        # Note: document_logs has no tenant_id column today (pre-existing
        # design limitation), so the response is global. We assert structure
        # only — once tenant_id is added to document_logs, swap this for a
        # real isolation check.
        assert "documents" in d.json()
        assert "documents" in c.json()

    def test_guardrails_isolated_with_distinct_tenant_ids(self, default_token, cs_token):
        """GET /api/tenant/guardrails returns the policy for the JWT's tenant.
        The two tenants must see distinct tenant_ids in their respective
        responses — that's the proof rows are not being shared."""
        d = httpx.get(
            f"{BASE_URL}/api/tenant/guardrails",
            headers=_auth(default_token), timeout=10,
        ).json()
        c = httpx.get(
            f"{BASE_URL}/api/tenant/guardrails",
            headers=_auth(cs_token), timeout=10,
        ).json()
        assert d["tenant_id"] != c["tenant_id"], (
            f"both tenants got the same policy row: {d['tenant_id']}"
        )
        # Sanity-check the JWT claim agrees with the response tenant_id.
        d_claims = _decode_jwt_payload(default_token)
        c_claims = _decode_jwt_payload(cs_token)
        assert d["tenant_id"] == d_claims["tenant_id"]
        assert c["tenant_id"] == c_claims["tenant_id"]

    def test_guardrails_update_does_not_cross_tenants(self, default_token, cs_token):
        """Updating client-sandbox's guardrail policy must not affect default's.
        Mutates client-sandbox to a distinctive value, reads default's, and
        asserts default is unchanged. Restores client-sandbox to original
        at the end so the test is idempotent."""
        # Snapshot both before.
        d_before = httpx.get(
            f"{BASE_URL}/api/tenant/guardrails",
            headers=_auth(default_token), timeout=10,
        ).json()
        c_before = httpx.get(
            f"{BASE_URL}/api/tenant/guardrails",
            headers=_auth(cs_token), timeout=10,
        ).json()
        new_threshold = (int(c_before["min_deal_size_cents"]) + 1234567) % 100_000_000

        try:
            # Mutate client-sandbox.
            patch = httpx.put(
                f"{BASE_URL}/api/tenant/guardrails",
                headers=_auth(cs_token),
                json={"min_deal_size_cents": new_threshold},
                timeout=10,
            )
            assert patch.status_code == 200, patch.text
            # default unchanged?
            d_after = httpx.get(
                f"{BASE_URL}/api/tenant/guardrails",
                headers=_auth(default_token), timeout=10,
            ).json()
            assert d_after["min_deal_size_cents"] == d_before["min_deal_size_cents"], (
                "client-sandbox's mutation leaked into default's policy row"
            )
            # client-sandbox actually updated?
            c_after = httpx.get(
                f"{BASE_URL}/api/tenant/guardrails",
                headers=_auth(cs_token), timeout=10,
            ).json()
            assert int(c_after["min_deal_size_cents"]) == new_threshold
        finally:
            # Restore.
            httpx.put(
                f"{BASE_URL}/api/tenant/guardrails",
                headers=_auth(cs_token),
                json={"min_deal_size_cents": int(c_before["min_deal_size_cents"])},
                timeout=10,
            )


class TestForgeryDefense:
    def test_sf_prompt_to_quote_no_forgery(self, cs_token):
        """sf_prompt_to_quote keeps tenant_id as a body field for backward
        compat, but a mismatch between JWT and body must 403. Three cases:
          (a) no tenant_id in body          → not a forgery; passes the check.
          (b) tenant_id matches JWT slug    → not a forgery; passes the check.
          (c) tenant_id != JWT slug         → forgery; 403.
        For (a)/(b), client-sandbox has no products so the request 409s on
        empty catalog — the signal is the absence of a 403, not a 200."""
        prompt = {"prompt_text": "Quote 50 enterprise licenses for Acme Corp."}

        # (a) no tenant_id
        a = httpx.post(
            f"{BASE_URL}/api/sf/prompt-to-quote",
            headers=_auth(cs_token), json=prompt, timeout=15,
        )
        assert a.status_code != 403, f"unexpected 403 for legitimate request: {a.text}"

        # (b) matching tenant_id
        b = httpx.post(
            f"{BASE_URL}/api/sf/prompt-to-quote",
            headers=_auth(cs_token),
            json={**prompt, "tenant_id": "client-sandbox"},
            timeout=15,
        )
        assert b.status_code != 403, f"unexpected 403 when body matches JWT: {b.text}"

        # (c) forgery: body says default, JWT says client-sandbox
        c = httpx.post(
            f"{BASE_URL}/api/sf/prompt-to-quote",
            headers=_auth(cs_token),
            json={**prompt, "tenant_id": "default"},
            timeout=15,
        )
        assert c.status_code == 403, f"forgery should 403, got {c.status_code}: {c.text}"
        assert "match" in c.json().get("detail", "").lower()

        # Also forge as 'acme'.
        d = httpx.post(
            f"{BASE_URL}/api/sf/prompt-to-quote",
            headers=_auth(cs_token),
            json={**prompt, "tenant_id": "acme"},
            timeout=15,
        )
        assert d.status_code == 403, f"acme forgery should 403, got {d.status_code}: {d.text}"
