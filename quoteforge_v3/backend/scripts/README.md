# scripts/

One-off operator scripts. Each is runnable as `python -m scripts.<name>`
from the `backend/` directory with the venv active.

## `provision_tenant.py`

Creates a new tenant + admin user. Idempotent on the slug.

```bash
python -m scripts.provision_tenant <slug> "<Company Name>" [admin-email] [admin-password]
```

## `provision_sf_connection.py`

Bootstraps a Salesforce `crm_connections` row for a tenant by injecting
tokens extracted from the local `sf` CLI's stored alias. Replaces the
absent OAuth redirect flow for FYP-defense purposes.

```bash
python -m scripts.provision_sf_connection <tenant_slug> <sf_alias>
```

Example:
```bash
python -m scripts.provision_sf_connection client-sandbox client-sandbox
```

### When to use it

- Bootstrapping a tenant's Salesforce connection without an OAuth-callback
  UI (e.g., the QuoteForge admin portal hasn't been deployed where the
  customer admin can click through OAuth).
- Re-pointing an existing tenant's connection at a different sandbox/org —
  re-running the script with the same `tenant_slug` updates the row in place.

### What it does

1. Shells out to `sf org display --target-org <sf_alias> --json` and pulls
   `accessToken`, `instanceUrl`, `username`, `id` (orgId).
2. Resolves the tenant by slug. Errors if the tenant doesn't exist.
3. UPSERTs the `crm_connections` row keyed on `(tenant_id, platform='Salesforce')`,
   stamping it `status='connected'`, `health=100`, `last_synced=now`.
4. Auto-detects `environment='sandbox' | 'production'` from the
   `instance_url` (substring match on `.sandbox.`).

### Token expiry

`sf org display` does **not** expose the refresh token (it's in the OS
keychain). The script stores `refresh_token=""`. Consequences:

- Sandbox access tokens expire in **~2-4 hours**. After expiry,
  `get_salesforce_client.test_connection()` returns 401, the refresh path
  bails because there's no token, and the function returns `None`. Schema
  scans / predictions fall back to stock or `no_model`.
- **Mitigation: re-run the script.** It's idempotent — the row is updated
  in place with the freshly-issued access token from `sf org display`.

### Post-defense replacement

The proper fix is to extend `app/routers/crm.py::oauth_callback` to accept
`state=tenant_id` so an admin completing OAuth gets their tokens stored
against the correct tenant. That removes the need for this script entirely
and gives us refresh tokens for free (full OAuth 2.0 includes them when
scope `refresh_token` is requested). Tracked under post-defense Phase 2.
