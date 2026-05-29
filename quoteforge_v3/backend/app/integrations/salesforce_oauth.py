"""One-click Salesforce Connected App OAuth — Web Server Flow + PKCE.

Distinct from app/routers/crm.py (the legacy CRMConnection-based flow):
this module is the canonical install path for the QuoteForge Connected
App. Flow:

  1. LWC "Connect" button → window.open(.../start?tenant_id=X) opens a
     popup logged in to Salesforce.
  2. /start builds a PKCE verifier+challenge, packs {tenant_id, verifier,
     nonce, exp} into an HMAC-signed `state` param, and 302s the user
     to <SALESFORCE_LOGIN_URL>/services/oauth2/authorize.
  3. Salesforce redirects back to /callback with ?code= and ?state=.
     We verify the state signature + expiry, POST the code+verifier to
     /services/oauth2/token, then GET /services/oauth2/userinfo to learn
     the org_id, and upsert SalesforceOAuthToken (encrypted).
  4. /callback 302s the popup to PUBLIC_BASE_URL/integrations/salesforce/
     success — the LWC polls /status until it flips to connected=true.

When SALESFORCE_CLIENT_ID or SALESFORCE_CLIENT_SECRET is unset, every
endpoint returns 501 with a clear message instead of a half-working
flow — local dev with empty creds stays functional.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt_str
from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.models.salesforce_oauth_token import SalesforceOAuthToken

router = APIRouter(prefix="/integrations/salesforce", tags=["salesforce-oauth"])
_logger = logging.getLogger(__name__)

# Lifetime of a /start → /callback state. Salesforce login can take a
# while (MFA, password reset) but anything beyond 10 minutes is almost
# certainly a stale redirect we should reject.
_STATE_TTL_SECONDS = 600

# Minimum scopes we ask for. `api` lets us call REST; `refresh_token`
# is required to refresh access tokens; `offline_access` keeps refresh
# tokens valid even after the user logs out of Salesforce.
_OAUTH_SCOPES = "api refresh_token offline_access"


# ─── Configuration helpers ────────────────────────────────────────────


def _is_configured() -> bool:
    return bool(settings.SALESFORCE_CLIENT_ID and settings.SALESFORCE_CLIENT_SECRET)


def _require_configured() -> None:
    if not _is_configured():
        raise HTTPException(
            status_code=501,
            detail=(
                "Salesforce Connected App is not configured. Set "
                "SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET in the "
                "backend environment, then restart."
            ),
        )


def _public_base_url() -> str:
    """Base URL the backend is reachable at — no trailing slash."""
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if base:
        # Render passes RENDER_EXTERNAL_HOSTNAME without scheme; normalize.
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "https://" + base
        return base
    return "http://localhost:8000"


def _redirect_uri() -> str:
    return f"{_public_base_url()}/api/integrations/salesforce/callback"


def _success_redirect_url() -> str:
    return f"{_public_base_url()}/integrations/salesforce/success"


# ─── PKCE + signed state ──────────────────────────────────────────────


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 S256."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def sign_state(payload: dict[str, Any]) -> str:
    """HMAC-SHA256-sign a JSON payload and return a compact `body.sig` string.

    Payload is serialised with sorted keys for stable signing. The signing
    key is settings.SECRET_KEY — rotating it invalidates every in-flight
    state, which is the desired behaviour.
    """
    body = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    sig = _b64url(
        hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    return f"{body}.{sig}"


def verify_state(state: str) -> dict[str, Any]:
    """Verify a signed state token and return its payload.

    Raises HTTPException(400) on tamper, malformed input, or expiry.
    """
    if not state or "." not in state:
        raise HTTPException(status_code=400, detail="Malformed OAuth state")
    body, sig = state.rsplit(".", 1)
    expected = _b64url(
        hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature")
    try:
        payload = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Malformed OAuth state body")
    exp = payload.get("exp", 0)
    if not isinstance(exp, (int, float)) or exp < time.time():
        raise HTTPException(status_code=400, detail="OAuth state expired — please retry")
    return payload


# ─── Salesforce HTTP helpers ──────────────────────────────────────────


async def _exchange_code(
    code: str, code_verifier: str
) -> dict[str, Any]:
    """POST the auth code + PKCE verifier; return the parsed token JSON."""
    token_url = f"{settings.SALESFORCE_LOGIN_URL.rstrip('/')}/services/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.SALESFORCE_CLIENT_ID,
        "client_secret": settings.SALESFORCE_CLIENT_SECRET,
        "redirect_uri": _redirect_uri(),
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code >= 400:
        _logger.warning(
            "Salesforce token exchange failed: %s %s", resp.status_code, resp.text
        )
        raise HTTPException(
            status_code=502,
            detail=f"Salesforce token exchange failed: {resp.text}",
        )
    return resp.json()


async def _fetch_userinfo(instance_url: str, access_token: str) -> dict[str, Any]:
    url = f"{instance_url.rstrip('/')}/services/oauth2/userinfo"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {access_token}"}
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Salesforce userinfo failed: {resp.status_code} {resp.text}",
        )
    return resp.json()


# ─── Endpoints ────────────────────────────────────────────────────────


def _build_authorize_url(tenant_id: str) -> str:
    verifier, challenge = generate_pkce()
    state = sign_state(
        {
            "tenant_id": tenant_id,
            "v": verifier,
            "n": secrets.token_hex(8),
            "exp": int(time.time()) + _STATE_TTL_SECONDS,
        }
    )
    return (
        f"{settings.SALESFORCE_LOGIN_URL.rstrip('/')}/services/oauth2/authorize?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.SALESFORCE_CLIENT_ID,
                "redirect_uri": _redirect_uri(),
                "scope": _OAUTH_SCOPES,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                # `prompt=consent` makes Salesforce always re-confirm
                # consent. Drop later for a smoother re-install flow.
                "prompt": "consent",
            }
        )
    )


@router.get("/start")
async def start_oauth(
    request: Request,
    tenant_id: str = Query(..., description="QuoteForge tenant UUID initiating the install"),
) -> RedirectResponse:
    """Kick off the OAuth flow. 302s the browser to Salesforce consent.

    Used when the caller already knows the tenant_id (e.g. an admin
    triggering the flow from a setup wizard URL). The LWC instead uses
    /init below, which derives tenant_id from the JWT.
    """
    _require_configured()
    return RedirectResponse(url=_build_authorize_url(tenant_id), status_code=302)


@router.get("/init")
async def init_oauth(
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, Any]:
    """LWC-friendly variant of /start: returns the authorize URL as JSON.

    The LWC opens this URL with window.open(...) so the user sees the
    Salesforce login screen in a popup. Tenant id comes from the JWT, so
    the browser never has to know it.
    """
    _require_configured()
    return {"authorize_url": _build_authorize_url(tenant_id)}


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Salesforce's redirect-back: exchange code, store token, bounce."""
    _require_configured()
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Salesforce returned error: {error}: {error_description or ''}",
        )

    payload = verify_state(state)
    tenant_id = payload["tenant_id"]
    verifier = payload["v"]

    token_data = await _exchange_code(code, verifier)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    instance_url = token_data["instance_url"]
    scopes = token_data.get("scope", _OAUTH_SCOPES)

    if not refresh_token:
        # `offline_access` should have guaranteed this — fail loudly
        # rather than silently store a non-renewable token.
        raise HTTPException(
            status_code=502,
            detail=(
                "Salesforce did not return a refresh_token. Verify the "
                "Connected App requests api, refresh_token, and "
                "offline_access scopes."
            ),
        )

    userinfo = await _fetch_userinfo(instance_url, access_token)
    org_id = userinfo.get("organization_id")
    if not org_id:
        raise HTTPException(
            status_code=502,
            detail="Salesforce userinfo did not return an organization_id",
        )

    existing = await db.get(SalesforceOAuthToken, org_id)
    if existing:
        existing.instance_url = instance_url
        existing.access_token = encrypt_str(access_token)
        existing.refresh_token = encrypt_str(refresh_token)
        existing.scopes = scopes
        existing.tenant_id = tenant_id
    else:
        db.add(
            SalesforceOAuthToken(
                org_id=org_id,
                instance_url=instance_url,
                access_token=encrypt_str(access_token),
                refresh_token=encrypt_str(refresh_token),
                scopes=scopes,
                tenant_id=tenant_id,
            )
        )
    await db.commit()

    return RedirectResponse(url=_success_redirect_url(), status_code=302)


@router.get("/status")
async def status(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Connection state for the JWT-authed tenant. Polled by the LWC."""
    if not _is_configured():
        return {"connected": False, "configured": False}

    stmt = select(SalesforceOAuthToken).where(
        SalesforceOAuthToken.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    if token is None:
        return {"connected": False, "configured": True}
    return {
        "connected": True,
        "configured": True,
        "org_id": token.org_id,
        "instance_url": token.instance_url,
        "scopes": token.scopes,
        "connected_at": token.issued_at.isoformat() if token.issued_at else None,
    }


@router.post("/disconnect")
async def disconnect(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Revoke the access token at Salesforce and delete the local row."""
    _require_configured()
    stmt = select(SalesforceOAuthToken).where(
        SalesforceOAuthToken.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    if token is None:
        return {"disconnected": True, "had_token": False}

    # Best-effort revoke — if it fails (network, already revoked) we still
    # delete the local row so the tenant can re-connect cleanly.
    from app.core.crypto import decrypt_str

    try:
        plain_refresh = decrypt_str(token.refresh_token)
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.SALESFORCE_LOGIN_URL.rstrip('/')}/services/oauth2/revoke",
                data={"token": plain_refresh},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception as exc:  # noqa: BLE001 — best-effort
        _logger.warning("Salesforce revoke failed (ignored): %s", exc)

    await db.delete(token)
    await db.commit()
    return {"disconnected": True, "had_token": True}
