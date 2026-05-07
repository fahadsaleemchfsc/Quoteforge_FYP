# QuoteForge — engineering challenges + how we resolved them

A running log of non-obvious design decisions, latent bugs we found, and the
band-aids vs. proper fixes we chose during the FYP build.

---

## CRM connection per-tenant — May 6, 2026

**Symptom.** The Mapping Wizard's "Add custom feature" dropdown showed only
17 standard Opportunity fields — never any `__c` custom fields, regardless
of which tenant was authenticated. Investigation revealed the
`/api/insights/schema` endpoint was returning a stock-fallback list because
`get_salesforce_client(db)` returned `None` for every caller.

**Root cause.** The pattern was identical to the user→tenant gap fixed
earlier: `crm_connections` had no `tenant_id` FK. Every tenant shared one
global Salesforce row. If that row's tokens were stale or the row didn't
exist, every tenant got the stock fallback. There was no way for two
tenants to maintain separate Salesforce orgs in parallel.

**Fix.** Same shape as the user→tenant fix:

1. **Schema migration** (`migrate_add_crm_connections_tenant_id` in
   `app/seed.py`) — added `tenant_id VARCHAR(36) FK` + index, idempotent
   PRAGMA-checked, called twice in lifespan for fresh-DB safety. Backfilled
   the 3 existing rows to the default tenant (their historical owner).
2. **Resolver update** (`app/services/salesforce_connector.py:707`) —
   `get_salesforce_client(db, tenant_id, conn_id=None)`: tenant_id is now
   required; the SQL filter is `WHERE tenant_id=:tid AND platform='Salesforce'
   AND status='connected'`. When `conn_id` is supplied, the lookup is by
   id but still scoped to tenant_id (defense-in-depth — prevents tenant A
   from passing tenant B's connection id).
3. **Call-site update** — 10 callers across `crm.py`, `schema_inspector.py`,
   and `salesforce_fetch.py` updated to pass `tenant_id`. Routers get it
   from `Depends(get_current_tenant_id)`; service-layer functions already
   accepted `tenant_id` as a parameter and just thread it through.

**Bonus catch.** `crm.py::import_salesforce_products` was doing its own
direct `select(CRMConnection).where(platform='Salesforce', status='connected')`
lookup outside `get_salesforce_client`. Same bug pattern. Added a
`tenant_id` filter to that query too. (Endpoint already had `tenant_id`
from the Phase 3 isolation work.)

**OAuth-flow band-aid.** A Salesforce Connected App + redirect callback is
the right way to provision a tenant's connection. For the FYP defense the
`client-sandbox` tenant's row was provisioned by **direct token injection
from the local `sf` CLI**, via
`backend/scripts/provision_sf_connection.py`. The script shells out to
`sf org display --target-org <alias> --json`, extracts `accessToken` +
`instanceUrl`, and UPSERTs the `crm_connections` row scoped to the named
tenant.

Caveats baked into the band-aid:

- `sf org display` does **not** expose the refresh token (kept in the OS
  keychain). The script writes `refresh_token=""`. Once the access token
  expires (sandbox: ~2-4h), `get_salesforce_client.test_connection()`
  returns 401, the refresh path bails (no token), and the function
  returns `None`. **Re-run the script when this happens.**
- The script is the dev-bootstrap path. Production deployment uses the
  standard OAuth 2.0 flow already wired at `app/routers/crm.py:194
  (oauth_callback)` — that path was untouched. Post-defense work: extend
  the OAuth callback to accept a `state=tenant_id` query param so a
  customer admin can complete OAuth scoped to their own tenant, eliminating
  the need for the injection script.

**Result.** Verified end-to-end in Phase D: `client-sandbox` tenant hits
`/api/insights/schema` and gets DMI's live Opportunity describe — 92 fields
including 45 `__c` customs (`Budget_Confirmed__c`, `Discovery_Completed__c`,
`Pipeline__c`, `Loss_Reason__c`, etc.) — over **17,378 closed Opportunities**.
Default tenant continues to see its stock fallback in isolation; no
cross-tenant leak (Phase E).

**Out of scope but flagged.**
- `get_refresh_aware_client(db, conn_id)` still takes only `conn_id` and
  doesn't enforce tenant_id ownership. The single caller (`crm_sync_worker`)
  already iterates per-tenant CRMSyncJob rows so the leak vector is small,
  but a 1-line filter add would close it. Post-defense.
- `document_logs` and `audit_logs` have no `tenant_id` columns either —
  the same pattern of latent isolation gap. Identified during Phase 6 test
  authoring; left for post-defense.
- **`oauth_callback` does not parse the `reauth:<id>` state prefix.**
  `reauthenticate_connection` (`app/routers/crm.py:737`) sets
  `state=f"reauth:{conn_id}"`, but the callback at `:201` does
  `environment = state` unconditionally — so the literal string
  `"reauth:4"` gets passed to `exchange_code_for_tokens` as the
  environment (which expects `production` or `sandbox`) and to
  `store_salesforce_tokens`, which would create a new connection row
  rather than updating the existing `conn_id` in place. Consequence:
  the API-driven reauth path is currently broken; we use
  `scripts/provision_sf_connection.py` instead as the dev workaround.
  Until this is fixed, `refresh_token` stays empty in dev (the script
  cannot extract it from the `sf` CLI keychain) and the connection
  goes `reauth_required` every 2-4 hours when the access token expires
  — re-run the script to restore.
  Post-defense: parse `state` with a `reauth:` prefix branch in
  `oauth_callback`, look up the existing `conn_id`, update tokens in
  place, and route the redirect environment from the persisted row
  rather than from `state`.

---
