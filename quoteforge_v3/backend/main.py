"""
QuoteForge Backend — FastAPI Application
AI-Powered Quote & Proposal Generation Tool for CRM Platforms
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env into os.environ before any module reads via os.environ.get(...).
# Pydantic Settings reads its own fields from .env, but vars not declared on
# the Settings class (e.g. INSIGHTS_REAL_DATA_PATH, consumed by salesforce_fetch
# via os.environ.get) need an explicit dotenv load.
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.cors import cors_config
from app.core.database import init_db
from app.routers import auth, users, templates, pricing, prompts, crm, quotes, settings, learning, products, approvals, tenant_config, guardrails, negotiations, offers, activity, share_tokens, buyer_room, sf_prompt_to_quote, insights, icp, admin
from app.integrations import salesforce_oauth as salesforce_oauth_integration
from app.integrations import salesforce_actions as salesforce_actions_integration
# Import so SQLAlchemy registers the new tables under Base.metadata before init_db().
from app.models import tenant as _tenant_model  # noqa: F401
from app.models import product as _product_model  # noqa: F401
from app.models import tenant_config as _tenant_config_model  # noqa: F401
from app.models import pending_approval as _pending_approval_model  # noqa: F401
from app.models import crm_sync_job as _crm_sync_job_model  # noqa: F401
from app.models import guardrail_policy as _guardrail_policy_model  # noqa: F401
from app.models import replay_event as _replay_event_model  # noqa: F401
from app.models import deal_share_token as _deal_share_token_model  # noqa: F401
from app.models import insights as _insights_models  # noqa: F401 — Module 6 Deal Insights
from app.models import icp as _icp_models  # noqa: F401 — Phase 3 ICP Builder
from app.models import salesforce_oauth_token as _sf_oauth_token_model  # noqa: F401 — one-click Connected App flow
from app.gateway.router import router as gateway_router, register_builtin_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed data on first run + one-shot guardrail migration on every startup
    from app.seed import (
        seed_database,
        migrate_tenant_config_to_guardrails,
        migrate_add_negotiation_mode_column,
        migrate_add_crm_sync_columns,
        migrate_add_insights_mapping_columns,
        migrate_add_insights_v65_columns,
        migrate_add_user_tenant_id,
        migrate_add_crm_connections_tenant_id,
        migrate_add_icp_contact_fields,
        migrate_add_template_master_columns,
        bootstrap_doc_id_counters,
    )
    # Schema migration must run before seed_database, which queries User —
    # the model now references users.tenant_id and would crash on an existing
    # DB where the column hasn't been added yet.
    await migrate_add_user_tenant_id()
    # crm_connections.tenant_id added before seed too, for symmetry with the
    # user migration. Backfill bails early on a fresh DB (no default tenant
    # yet) and runs on the second call below.
    await migrate_add_crm_connections_tenant_id()
    await seed_database()
    await migrate_add_negotiation_mode_column()
    await migrate_add_crm_sync_columns()
    await migrate_add_insights_mapping_columns()
    await migrate_add_insights_v65_columns()
    # Second call backfills users seeded by seed_database on a fresh DB
    # (which created tenants in the same step). Idempotent — no-op once
    # every user has a tenant_id.
    await migrate_add_user_tenant_id()
    await migrate_add_crm_connections_tenant_id()
    await migrate_add_icp_contact_fields()
    # Adds html_body/is_master/tenant_id to templates and seeds a default
    # master row per tenant — needs tenants to exist (after seed_database).
    await migrate_add_template_master_columns()
    await migrate_tenant_config_to_guardrails()
    await bootstrap_doc_id_counters()
    # Demo seed — idempotent, generates synthetic activity for the dashboard + impact preview
    from app.demo_seed import seed_demo_activity
    await seed_demo_activity()
    # Register Agent Gateway MCP tools
    register_builtin_tools()
    # Start the CRM sync worker (drains queued CRMSyncJob rows every 15s).
    from app.gateway.workers import start_scheduler, stop_scheduler
    start_scheduler()
    # Deal Insights nightly retrain worker (demo-path, 02:00 UTC).
    from app.gateway.workers.insights_retrain_worker import (
        start_retrain_scheduler, stop_retrain_scheduler,
    )
    start_retrain_scheduler()
    _real_data = os.environ.get("INSIGHTS_REAL_DATA_PATH", "")
    logging.getLogger(__name__).info(
        "INSIGHTS_REAL_DATA_PATH=%s",
        _real_data if _real_data else "(unset — trainer will use n=300 synthetic)",
    )
    logging.getLogger(__name__).info("QuoteForge backend ready")
    yield
    stop_scheduler()
    stop_retrain_scheduler()


app = FastAPI(
    title="QuoteForge API",
    description="AI-Powered Quote & Proposal Generation Tool for CRM Platforms",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — exact-match allowlist from CORS_ALLOW_ORIGINS env + regex for
# Salesforce Lightning hosts (which have per-org subdomains). Empty env
# var keeps the legacy "*" behaviour for local dev. See app/core/cors.py.
app.add_middleware(CORSMiddleware, **cors_config())

# Mount all routers under /api prefix
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(pricing.router, prefix="/api")
app.include_router(prompts.router, prefix="/api")
app.include_router(crm.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(learning.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(tenant_config.router, prefix="/api")
app.include_router(guardrails.router, prefix="/api")
app.include_router(negotiations.router, prefix="/api")
app.include_router(offers.router, prefix="/api")
app.include_router(activity.router, prefix="/api")
app.include_router(share_tokens.router, prefix="/api")
app.include_router(buyer_room.router, prefix="/api")
app.include_router(sf_prompt_to_quote.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(icp.router, prefix="/api")
# Platform super-admin (cross-tenant visibility). Gated by
# SUPER_ADMIN_EMAILS env var; see app/routers/admin.py.
app.include_router(admin.router, prefix="/api")
# One-click Salesforce Connected App flow — distinct from the legacy
# /api/crm endpoints which use CRMConnection.oauth_tokens JSON.
app.include_router(salesforce_oauth_integration.router, prefix="/api")
app.include_router(salesforce_actions_integration.router, prefix="/api")

# Agent Gateway — mounted at root (NOT /api) so /.well-known and /oauth
# and /mcp sit at spec-conformant paths for MCP clients.
app.include_router(gateway_router)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Cheap liveness probe for Render / Docker HEALTHCHECK.

    Intentionally does NOT touch the DB — Render hits this every 30s and
    we don't want probe traffic competing with real requests on a busy
    Postgres pool. Use /api/health for richer status.
    """
    return {"ok": True}


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "QuoteForge API", "version": "3.0.0"}


@app.get("/api/llm/health")
async def llm_health():
    """Check self-hosted LLM status — shows we're NOT using third-party APIs."""
    from app.services.llm_wrapper import check_llm_health
    from app.services.mlx_inference import check_mlx_available
    result = await check_llm_health()
    result["mlx"] = check_mlx_available()
    return result
