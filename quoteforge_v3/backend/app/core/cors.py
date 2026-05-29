"""CORS configuration helper.

Two ways to whitelist an origin:

  * Exact match — set CORS_ALLOW_ORIGINS to a comma-separated list of
    origins, e.g. "https://app.quoteforge.io,https://staging.quoteforge.io".
  * Regex match — Salesforce Lightning hosts have org-specific subdomains
    that change per customer, so we match them with a regex rather than
    forcing every admin to add their org to the env var.

Local dev: leaving CORS_ALLOW_ORIGINS empty falls back to "*" so the
React dev server and curl still work.
"""

from __future__ import annotations

from app.core.config import settings

# Matches the Lightning Experience and classic Salesforce hosts every
# org gets, regardless of subdomain. `--c` covers Lightning sandbox
# branches like acme--full.sandbox.my.salesforce.com.
SALESFORCE_ORIGIN_REGEX = (
    r"https://([a-zA-Z0-9-]+\.)?"
    r"(lightning\.force\.com|my\.salesforce\.com|salesforce\.com|visualforce\.com)"
)


def cors_config() -> dict:
    """Return kwargs ready to splat into add_middleware(CORSMiddleware, **...)."""
    raw = (settings.CORS_ALLOW_ORIGINS or "").strip()
    if not raw:
        # Dev default — wide open. Switch this off by setting any value.
        return {
            "allow_origins": ["*"],
            "allow_origin_regex": SALESFORCE_ORIGIN_REGEX,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return {
        "allow_origins": origins,
        "allow_origin_regex": SALESFORCE_ORIGIN_REGEX,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
