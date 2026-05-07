"""
Provision a Salesforce CRMConnection for a tenant by injecting tokens
extracted from the local `sf` CLI's stored alias.

This is the FYP-defense band-aid replacement for a proper Connected App
OAuth flow. Production deployment uses standard Salesforce OAuth 2.0 with
a Connected App + redirect callback — see app/routers/crm.py:194 for the
real flow. Deferred to post-defense Phase 2.

Usage
-----
    python -m scripts.provision_sf_connection <tenant_slug> <sf_alias>

Examples
--------
    python -m scripts.provision_sf_connection client-sandbox client-sandbox

The script:
  1. Runs `sf org display --target-org <sf_alias> --json` and pulls
     accessToken, instanceUrl, username, id (orgId).
  2. Resolves the tenant by slug.
  3. UPSERTs the crm_connections row for (tenant_id, platform='Salesforce').
  4. Prints a summary so the operator can re-run the schema endpoint to
     verify connectivity.

Notes
-----
- `sf org display` does NOT expose the refresh token (it's stored in the
  OS keychain and the CLI reads it directly when refreshing). The script
  records refresh_token="" — the backend's get_salesforce_client will
  refuse to refresh and return None once the access token expires.
  Re-run this script when that happens. Sandbox tokens typically live
  ~2-4 hours.
- Idempotent: re-running with the same (tenant_slug, sf_alias) updates
  the existing row in place.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import async_session
from app.models.crm_connection import CRMConnection
from app.models.tenant import Tenant


def _usage_and_exit(code: int = 2) -> None:
    print(__doc__, file=sys.stderr)
    sys.exit(code)


def _run_sf_org_display(sf_alias: str) -> dict:
    """Shell out to `sf org display --target-org <alias> --json` and return
    the parsed `result` block. Raises SystemExit on failure."""
    try:
        completed = subprocess.run(
            ["sf", "org", "display", "--target-org", sf_alias, "--json"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        print("error: `sf` CLI not found on PATH", file=sys.stderr)
        sys.exit(1)

    if completed.returncode != 0:
        print(f"error: sf org display failed (exit {completed.returncode})",
              file=sys.stderr)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as e:
        print(f"error: could not parse sf JSON output: {e}", file=sys.stderr)
        sys.exit(1)

    result = payload.get("result")
    if not isinstance(result, dict):
        print(f"error: sf org display returned unexpected payload: {payload}",
              file=sys.stderr)
        sys.exit(1)

    for key in ("accessToken", "instanceUrl", "username"):
        if not result.get(key):
            print(f"error: sf org display result missing `{key}`", file=sys.stderr)
            sys.exit(1)

    return result


async def _upsert_connection(
    *, tenant_slug: str, sf_alias: str, sf_result: dict,
) -> tuple[str, str, str]:
    """Resolve tenant, UPSERT the row. Returns (tenant_id, instance_url, action)."""
    tokens_json = json.dumps({
        "access_token": sf_result["accessToken"],
        "refresh_token": "",  # not exposed by `sf org display` — see module docstring
        "instance_url": sf_result["instanceUrl"],
    })

    async with async_session() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"error: tenant '{tenant_slug}' not found in tenants table",
                  file=sys.stderr)
            sys.exit(1)

        existing = (
            await db.execute(
                select(CRMConnection).where(
                    CRMConnection.tenant_id == tenant.id,
                    CRMConnection.platform == "Salesforce",
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        environment = "sandbox" if "sandbox" in sf_result["instanceUrl"] else "production"

        if existing is not None:
            existing.oauth_tokens = tokens_json
            existing.status = "connected"
            existing.environment = environment
            existing.health = 100.0
            existing.last_synced = now
            action = "updated"
        else:
            db.add(CRMConnection(
                tenant_id=tenant.id,
                platform="Salesforce",
                environment=environment,
                status="connected",
                oauth_tokens=tokens_json,
                health=100.0,
                last_synced=now,
                field_mappings=json.dumps([]),
            ))
            action = "created"

        await db.commit()
        return tenant.id, sf_result["instanceUrl"], action


async def _main(tenant_slug: str, sf_alias: str) -> None:
    sf_result = _run_sf_org_display(sf_alias)
    tenant_id, instance_url, action = await _upsert_connection(
        tenant_slug=tenant_slug, sf_alias=sf_alias, sf_result=sf_result,
    )

    print("=" * 60)
    print(f"  tenant_slug:  {tenant_slug}")
    print(f"  tenant_id:    {tenant_id}")
    print(f"  sf_alias:     {sf_alias}")
    print(f"  username:     {sf_result.get('username')}")
    print(f"  org_id:       {sf_result.get('id')}")
    print(f"  instance_url: {instance_url}")
    print(f"  status:       connected")
    print(f"  action:       {action}")
    print("=" * 60)
    print("ready to use — hit /api/insights/schema as this tenant to verify.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        _usage_and_exit()
    asyncio.run(_main(sys.argv[1], sys.argv[2]))
