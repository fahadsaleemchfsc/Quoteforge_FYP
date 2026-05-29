"""Happy-path tests for the one-click Salesforce OAuth flow.

These run fully in-process — no live backend on :8000 — so CI can pick
them up without the server-orchestration overhead the older tests need.
Run with:

    cd backend && ./venv/bin/pytest tests/test_salesforce_oauth.py -v
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings


# ─── State signing (pure, no I/O) ────────────────────────────────────


def test_sign_state_roundtrip():
    from app.integrations.salesforce_oauth import sign_state, verify_state

    payload = {
        "tenant_id": "tenant-123",
        "v": "verifier-abc",
        "n": "nonce-xyz",
        "exp": int(time.time()) + 60,
    }
    token = sign_state(payload)
    decoded = verify_state(token)
    assert decoded["tenant_id"] == "tenant-123"
    assert decoded["v"] == "verifier-abc"


def test_verify_state_rejects_tampered_body():
    from fastapi import HTTPException

    from app.integrations.salesforce_oauth import sign_state, verify_state

    token = sign_state(
        {"tenant_id": "t", "v": "v", "n": "n", "exp": int(time.time()) + 60}
    )
    body, sig = token.rsplit(".", 1)
    # Flip a single character in the body — signature must no longer match.
    tampered = body[:-1] + ("A" if body[-1] != "A" else "B") + "." + sig
    with pytest.raises(HTTPException) as exc:
        verify_state(tampered)
    assert exc.value.status_code == 400


def test_verify_state_rejects_expired():
    from fastapi import HTTPException

    from app.integrations.salesforce_oauth import sign_state, verify_state

    token = sign_state(
        {"tenant_id": "t", "v": "v", "n": "n", "exp": int(time.time()) - 1}
    )
    with pytest.raises(HTTPException) as exc:
        verify_state(token)
    assert "expired" in exc.value.detail.lower()


def test_generate_pkce_produces_correct_challenge():
    """code_challenge must be url-safe-base64(sha256(verifier))."""
    import base64
    import hashlib

    from app.integrations.salesforce_oauth import generate_pkce

    verifier, challenge = generate_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected


# ─── /status endpoint via ASGI transport ─────────────────────────────


@pytest.mark.asyncio
async def test_status_unconfigured_returns_not_configured(monkeypatch):
    """When SALESFORCE_CLIENT_ID/SECRET are empty, /status reports it."""
    monkeypatch.setattr(settings, "SALESFORCE_CLIENT_ID", "")
    monkeypatch.setattr(settings, "SALESFORCE_CLIENT_SECRET", "")

    from main import app
    from app.core.security import get_current_tenant_id

    app.dependency_overrides[get_current_tenant_id] = lambda: "tenant-stub"
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/integrations/salesforce/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["configured"] is False
    finally:
        app.dependency_overrides.pop(get_current_tenant_id, None)


# ─── sf_request 401 → refresh → retry ────────────────────────────────


@pytest.mark.asyncio
async def test_sf_request_refreshes_on_401(monkeypatch):
    """A 401 should trigger one refresh attempt followed by a single retry."""
    monkeypatch.setattr(settings, "SALESFORCE_CLIENT_ID", "client-x")
    monkeypatch.setattr(settings, "SALESFORCE_CLIENT_SECRET", "secret-x")
    monkeypatch.setattr(
        settings, "SALESFORCE_LOGIN_URL", "https://login.salesforce.com"
    )

    from app.core.crypto import encrypt_str
    from app.integrations import salesforce_client
    from app.models.salesforce_oauth_token import SalesforceOAuthToken

    token = SalesforceOAuthToken(
        org_id="00Dtest000000001",
        instance_url="https://acme.my.salesforce.com",
        access_token=encrypt_str("stale-access-token"),
        refresh_token=encrypt_str("refresh-token-abc"),
        scopes="api refresh_token offline_access",
        tenant_id="tenant-1",
    )

    # Fake DB that returns the token from _load_token, accepts commit.
    fake_db = AsyncMock()
    fake_db.commit = AsyncMock()

    async def fake_load_token(_db, _tenant_id):
        return token

    # Sequence the HTTP calls: first GET → 401, refresh POST → 200 with
    # new token, retry GET → 200.
    call_log: list[str] = []

    class _MockClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def request(self, method, url, **_kwargs):
            call_log.append(f"{method} {url}")
            access = _kwargs.get("headers", {}).get("Authorization", "")
            if "fresh-access-token" in access:
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(401, json={"error": "INVALID_SESSION_ID"})

        async def post(self, url, **_kwargs):
            call_log.append(f"POST {url}")
            return httpx.Response(
                200, json={"access_token": "fresh-access-token"}
            )

    with patch.object(salesforce_client, "_load_token", fake_load_token), patch.object(
        salesforce_client.httpx, "AsyncClient", _MockClient
    ):
        resp = await salesforce_client.sf_request(
            fake_db,
            "tenant-1",
            "GET",
            "/services/data/v60.0/sobjects/Quote/0Q0xx00000004C9",
        )

    assert resp.status_code == 200
    # First request (401), refresh POST, retry (200) — three calls total.
    assert len(call_log) == 3
    assert call_log[0].startswith("GET ")
    assert "oauth2/token" in call_log[1]
    assert call_log[2].startswith("GET ")
    fake_db.commit.assert_awaited()
