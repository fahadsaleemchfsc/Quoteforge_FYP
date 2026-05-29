"""Authenticated Salesforce REST client for the one-click Connected App flow.

`sf_request` is the only entry point. It loads the tenant's
SalesforceOAuthToken, decrypts the access token, fires the request, and
on a 401 refreshes once using the stored refresh_token (then retries with
the new access token, persisting it back to the DB).

Callers should never reach for `httpx` directly — going through this
helper keeps refresh logic in one place and means every Salesforce-bound
call automatically benefits from token rotation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str, encrypt_str
from app.models.salesforce_oauth_token import SalesforceOAuthToken

_logger = logging.getLogger(__name__)


async def _load_token(
    db: AsyncSession, tenant_id: str
) -> SalesforceOAuthToken:
    stmt = select(SalesforceOAuthToken).where(
        SalesforceOAuthToken.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Tenant is not connected to a Salesforce org. Click "
                "Connect inside the QuoteForge app first."
            ),
        )
    return token


async def _refresh_access_token(token: SalesforceOAuthToken) -> str:
    """Exchange the stored refresh_token for a fresh access_token."""
    if not settings.SALESFORCE_CLIENT_ID or not settings.SALESFORCE_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail="Salesforce Connected App is not configured on the backend",
        )

    refresh = decrypt_str(token.refresh_token)
    token_url = (
        f"{settings.SALESFORCE_LOGIN_URL.rstrip('/')}/services/oauth2/token"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": settings.SALESFORCE_CLIENT_ID,
                "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            },
        )
    if resp.status_code >= 400:
        _logger.warning(
            "Salesforce refresh failed: %s %s", resp.status_code, resp.text
        )
        raise HTTPException(
            status_code=401,
            detail=(
                "Salesforce refresh token rejected — the org may have "
                "revoked access. Re-run the Connect flow."
            ),
        )
    return resp.json()["access_token"]


async def sf_request(
    db: AsyncSession,
    tenant_id: str,
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> httpx.Response:
    """Call Salesforce REST as `tenant_id`'s connected org.

    `path` is appended to the org's instance_url, so callers pass
    something like `/services/data/v60.0/sobjects/Quote`.

    On a 401 we refresh the access_token once and retry — anything other
    than success after that surfaces to the caller as the raw response.
    """
    token = await _load_token(db, tenant_id)
    base = token.instance_url.rstrip("/")
    url = f"{base}{path}"
    base_headers = {"Accept": "application/json"}
    if json is not None:
        base_headers["Content-Type"] = "application/json"
    if headers:
        base_headers.update(headers)

    async def _send(access_token: str) -> httpx.Response:
        merged = {**base_headers, "Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method,
                url,
                json=json,
                params=params,
                headers=merged,
            )

    access = decrypt_str(token.access_token)
    resp = await _send(access)
    if resp.status_code != 401:
        return resp

    # Refresh + retry once. Persist the new access token so subsequent
    # calls skip the refresh hop.
    _logger.info("Salesforce returned 401 for tenant %s — refreshing", tenant_id)
    new_access = await _refresh_access_token(token)
    token.access_token = encrypt_str(new_access)
    await db.commit()
    return await _send(new_access)
