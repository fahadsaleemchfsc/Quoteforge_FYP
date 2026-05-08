"""
Database seeder — populates initial data matching the frontend mock data.
Only runs if the users table is empty (first launch).
"""
import json
import logging
import os
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.database import async_session
from app.core.security import hash_password

# Default admin/user passwords for the seed data. Real values must come from
# the environment so they're never committed to source. The fallback is an
# obviously-not-real placeholder so a fresh clone can boot, but never with
# working credentials matching anything in production.
_DEFAULT_ADMIN_PASSWORD = os.environ.get("QF_DEFAULT_ADMIN_PASSWORD", "change-me-locally")
_DEFAULT_USER_PASSWORD = os.environ.get("QF_DEFAULT_USER_PASSWORD", "change-me-locally")
from app.models.user import User
from app.models.template import Template
from app.models.pricing_rule import PricingRule
from app.models.ai_prompt import AIPrompt
from app.models.crm_connection import CRMConnection
from app.models.document_log import DocumentLog
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig, DEFAULT_APPROVAL_THRESHOLD_CENTS
from app.models.product import Product
from app.models.guardrail_policy import GuardrailPolicy, DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS
# Register these with Base.metadata so init_db() creates their tables.
from app.models import pending_approval as _pending_approval  # noqa: F401
from app.models import crm_sync_job as _crm_sync_job  # noqa: F401
from app.models import replay_event as _replay_event  # noqa: F401
from app.models import deal_share_token as _deal_share_token  # noqa: F401
from app.models.document_id_counter import DocumentIdCounter
from app.services.crm_service import DEFAULT_FIELD_MAPPINGS


# Slug used by the admin portal (single-tenant dev mode). The MCP dev bearer
# token format "dev-<slug>" matches against Tenant.slug, and unknown slugs are
# auto-provisioned by ensure_tenant_by_slug below.
DEFAULT_TENANT_SLUG = "default"

logger = logging.getLogger(__name__)


async def seed_database():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            logger.info("Database already seeded, skipping")
            return

        logger.info("Seeding database with initial data...")

        # ─── Users ────────────────────────────────────────────────
        users = [
            User(name="Agha Zain Nadir", email="admin@quoteforge.io", password_hash=hash_password(_DEFAULT_ADMIN_PASSWORD), role="admin", department="Engineering", status="active", avatar="AZ", quotes_generated=342),
            User(name="Sarah Johnson", email="sarah@quoteforge.io", password_hash=hash_password(_DEFAULT_USER_PASSWORD), role="user", department="Sales", status="active", avatar="SJ", quotes_generated=156),
            User(name="Mike Rodriguez", email="mike@quoteforge.io", password_hash=hash_password(_DEFAULT_USER_PASSWORD), role="user", department="Sales", status="active", avatar="MR", quotes_generated=89),
            User(name="Faraz Ali", email="faraz@quoteforge.io", password_hash=hash_password(_DEFAULT_ADMIN_PASSWORD), role="admin", department="AI Engineering", status="active", avatar="FA", quotes_generated=0),
            User(name="Lisa Kim", email="lisa@quoteforge.io", password_hash=hash_password(_DEFAULT_USER_PASSWORD), role="user", department="Sales", status="inactive", avatar="LK", quotes_generated=201),
            User(name="Fahad Saleem", email="fahad@quoteforge.io", password_hash=hash_password(_DEFAULT_ADMIN_PASSWORD), role="admin", department="Backend", status="active", avatar="FS", quotes_generated=0),
            User(name="Saad Khalid", email="saad@quoteforge.io", password_hash=hash_password(_DEFAULT_ADMIN_PASSWORD), role="admin", department="Frontend", status="active", avatar="SK", quotes_generated=0),
        ]
        db.add_all(users)

        # ─── Templates ────────────────────────────────────────────
        templates = [
            Template(name="Enterprise Sales Proposal", type="Proposal", format="PDF", status="active", usage_count=342, author="Admin",
                     content="Professional enterprise proposal template with executive summary, scope, pricing, and terms sections."),
            Template(name="Standard Quote Template", type="Quote", format="DOCX", status="active", usage_count=891, author="Admin",
                     content="Standard quote template with line items, pricing breakdown, and payment terms."),
            Template(name="SaaS Renewal Template", type="Proposal", format="PDF", status="active", usage_count=56, author="System",
                     content="Renewal proposal template for annual SaaS contracts."),
            Template(name="SaaS Subscription Quote", type="Quote", format="PDF", status="draft", usage_count=0, author="Mike R.",
                     content="SaaS subscription pricing quote with monthly/annual billing options."),
            Template(name="Consulting Services Proposal", type="Proposal", format="DOCX", status="active", usage_count=234, author="Admin",
                     content="Consulting engagement proposal with methodology, timeline, and deliverables."),
            Template(name="Managed Services Quote", type="Quote", format="PDF", status="archived", usage_count=178, author="Admin",
                     content="Managed services quote template — legacy, archived."),
        ]
        db.add_all(templates)

        # ─── Pricing Rules ────────────────────────────────────────
        rules = [
            PricingRule(name="Volume Discount Tier 1", type="Discount", condition="Qty > 100", value="10%", region="Global", status="active"),
            PricingRule(name="Enterprise Discount", type="Discount", condition="Deal > $50K", value="15%", region="US", status="active"),
            PricingRule(name="Sales Tax — US", type="Tax", condition="Region = US", value="Variable", region="US", status="active"),
            PricingRule(name="VAT — EU", type="Tax", condition="Region = EU", value="20%", region="EU", status="active"),
        ]
        db.add_all(rules)

        # ─── AI Prompts ───────────────────────────────────────────
        prompts = [
            AIPrompt(name="Cover Letter Generator", section="Cover Letter", version="v3.2", status="active", tokens="~450",
                     prompt_text=(
                         "Write a professional cover letter for a B2B sales proposal.\n\n"
                         "Client: {{client_name}}\nDeal: {{deal_name}}\nTotal Value: ${{deal_amount}}\n"
                         "Products/Services: {{line_items}}\n\n"
                         "Requirements:\n- Professional and confident tone\n- Personalized to the client\n"
                         "- 2-3 paragraphs maximum\n- Highlight value proposition\n- Include a call to action"
                     )),
            AIPrompt(name="Scope of Work Builder", section="Scope", version="v2.8", status="active", tokens="~680",
                     prompt_text=(
                         "Write a detailed Scope of Work for the following engagement.\n\n"
                         "Client: {{client_name}}\nProject: {{deal_name}}\n"
                         "Products/Services:\n{{line_items}}\n\n"
                         "Include:\n- Project objectives\n- Detailed deliverables\n- Timeline and milestones\n"
                         "- Success criteria\n- Assumptions and dependencies"
                     )),
            AIPrompt(name="Pricing Notes Composer", section="Pricing", version="v4.1", status="active", tokens="~320",
                     prompt_text=(
                         "Write a pricing summary section.\n\n"
                         "Client: {{client_name}}\nLine Items:\n{{line_items}}\n"
                         "Subtotal: ${{subtotal}}\nDiscount: ${{discount}}\nTax: ${{tax}}\nTotal: ${{total}}\n\n"
                         "Present pricing clearly. Explain any discounts applied. Note payment terms."
                     )),
            AIPrompt(name="Deliverables Formatter", section="Deliverables", version="v2.0", status="active", tokens="~520",
                     prompt_text=(
                         "Write a deliverables section for this proposal.\n\n"
                         "Client: {{client_name}}\nProject: {{deal_name}}\n"
                         "Products/Services:\n{{line_items}}\n\n"
                         "List each deliverable with:\n- Description\n- Acceptance criteria\n- Expected timeline"
                     )),
            AIPrompt(name="Terms & Conditions Writer", section="Terms", version="v3.5", status="testing", tokens="~780",
                     prompt_text=(
                         "Write Terms and Conditions for this proposal.\n\n"
                         "Region: {{region}}\n\n"
                         "Include:\n- Payment terms (Net 30)\n- Warranty provisions\n"
                         "- Limitation of liability\n- Confidentiality clause\n- Termination conditions\n"
                     )),
            AIPrompt(name="Executive Summary", section="Summary", version="v1.2", status="draft", tokens="~400",
                     prompt_text=(
                         "Write an executive summary.\n\n"
                         "Client: {{client_name}}\nProject: {{deal_name}}\nValue: ${{deal_amount}}\n"
                         "Products/Services: {{line_items}}\n\n"
                         "Summarize the value proposition concisely in 2-3 paragraphs."
                     )),
        ]
        db.add_all(prompts)

        # ─── CRM Connections ──────────────────────────────────────
        connections = [
            CRMConnection(platform="Salesforce", environment="production", status="connected",
                          deals_count=1247, health=99.8,
                          last_synced=datetime.now(timezone.utc),
                          field_mappings=json.dumps(DEFAULT_FIELD_MAPPINGS)),
            CRMConnection(platform="HubSpot", environment="sandbox", status="connected",
                          deals_count=342, health=98.2,
                          last_synced=datetime.now(timezone.utc),
                          field_mappings=json.dumps(DEFAULT_FIELD_MAPPINGS)),
            CRMConnection(platform="Custom", environment="sandbox", status="disconnected",
                          deals_count=89, health=0,
                          field_mappings=json.dumps(DEFAULT_FIELD_MAPPINGS)),
        ]
        db.add_all(connections)

        # ─── Document Logs (seed some recent activity) ────────────
        doc_logs = [
            DocumentLog(doc_id="DOC-2401", client="Acme Corp", deal_name="Enterprise License", type="Quote", format="PDF",
                        status="delivered", delivery_status="delivered", amount=45000,
                        user_id=2, user_name="Sarah J.", generation_time=3.2),
            DocumentLog(doc_id="DOC-2400", client="TechStart Inc", deal_name="SaaS Platform", type="Proposal", format="DOCX",
                        status="generated", delivery_status="pending", amount=128000,
                        user_id=3, user_name="Mike R.", generation_time=4.1),
            DocumentLog(doc_id="DOC-2399", client="Global Traders", deal_name="Consulting Package", type="Quote", format="PDF",
                        status="pending", delivery_status="pending", amount=22500,
                        user_id=5, user_name="Lisa K.", generation_time=2.8),
            DocumentLog(doc_id="DOC-2398", client="Nexus Systems", deal_name="Infrastructure", type="Proposal", format="PDF",
                        status="delivered", delivery_status="delivered", amount=89000,
                        user_id=2, user_name="James W.", generation_time=5.1),
            DocumentLog(doc_id="DOC-2397", client="Pinnacle Health", deal_name="Data Analytics", type="Quote", format="DOCX",
                        status="failed", delivery_status="failed", amount=67200,
                        user_id=2, user_name="Sarah J.", generation_time=0),
        ]
        db.add_all(doc_logs)

        await db.commit()
        logger.info("Database seeded successfully with 7 users, 6 templates, 7 pricing rules, 6 AI prompts, 3 CRM connections, 5 documents")

    # Tenant + Product seeding is idempotent and runs on every startup so that
    # adding these tables to an existing dev DB does not require a wipe.
    await seed_tenants_and_products()


async def ensure_tenant_by_slug(db, slug: str, name: str | None = None) -> Tenant:
    """Look up or auto-provision a tenant (and its config + policy) by slug."""
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=slug, name=name or slug.title())
        db.add(tenant)
        await db.flush()

    cfg_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    if cfg_result.scalar_one_or_none() is None:
        db.add(TenantConfig(
            tenant_id=tenant.id,
            approval_threshold_cents=DEFAULT_APPROVAL_THRESHOLD_CENTS,
            auto_commit_enabled=True,
        ))
        await db.flush()

    policy_result = await db.execute(
        select(GuardrailPolicy).where(GuardrailPolicy.tenant_id == tenant.id)
    )
    if policy_result.scalar_one_or_none() is None:
        db.add(GuardrailPolicy(
            tenant_id=tenant.id,
            require_approval_above_cents=DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS,
        ))
        await db.flush()

    counter_result = await db.execute(
        select(DocumentIdCounter).where(DocumentIdCounter.tenant_id == tenant.id)
    )
    if counter_result.scalar_one_or_none() is None:
        # Fresh tenant → first emitted id is DOC-2457, aligned with the
        # legacy sequence. bootstrap_doc_id_counters() will raise this above
        # any existing global doc_id on startup.
        db.add(DocumentIdCounter(tenant_id=tenant.id, last_number=2456))
        await db.flush()

    return tenant


async def bootstrap_doc_id_counters() -> None:
    """
    Idempotent startup migration for the atomic doc_id counter.

    For every tenant without a counter row, provision one initialized to
    max(global max existing doc_id, 2456). Using the GLOBAL max guarantees
    the next emitted DOC-N is strictly higher than any existing row, even
    though DocumentLog.doc_id is globally UNIQUE and the counter is keyed
    per-tenant. Safe to call on every startup.
    """
    from app.gateway.adapters.doc_id import (
        DEFAULT_BOOTSTRAP_LAST_NUMBER,
        _global_max_doc_number,
    )

    async with async_session() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        if not tenants:
            return
        global_max = await _global_max_doc_number(db)
        bootstrap = max(global_max, DEFAULT_BOOTSTRAP_LAST_NUMBER)
        created = 0
        for t in tenants:
            existing = (await db.execute(
                select(DocumentIdCounter).where(DocumentIdCounter.tenant_id == t.id)
            )).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(DocumentIdCounter(tenant_id=t.id, last_number=bootstrap))
            created += 1
        if created:
            await db.commit()
            logger.info(
                "doc_id counters bootstrapped: %d tenant(s) start at last_number=%d",
                created, bootstrap,
            )


async def migrate_add_insights_v65_columns() -> None:
    """
    Session 6.5 — new columns on deal_insight_models and deal_insight_predictions:
      - models.data_quality_tier (insufficient | early_stage | standard | mature)
      - models.holdout_predictions (JSON array for Accuracy endpoint)
      - predictions.probability_lower, probability_upper (bootstrap range)
    Idempotent — safe to re-run on every startup.
    """
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(deal_insight_models)")
        cols = {r[1] for r in rows.fetchall()}
        added: list[str] = []
        if "data_quality_tier" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_models ADD COLUMN data_quality_tier VARCHAR(20)"
            )
            added.append("models.data_quality_tier")
        if "holdout_predictions" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_models ADD COLUMN holdout_predictions TEXT"
            )
            added.append("models.holdout_predictions")

        rows = await conn.exec_driver_sql("PRAGMA table_info(deal_insight_predictions)")
        cols = {r[1] for r in rows.fetchall()}
        if "probability_lower" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_predictions ADD COLUMN probability_lower FLOAT"
            )
            added.append("predictions.probability_lower")
        if "probability_upper" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_predictions ADD COLUMN probability_upper FLOAT"
            )
            added.append("predictions.probability_upper")
        if added:
            logger.info("Session 6.5 columns added: %s", ", ".join(added))


async def migrate_add_insights_mapping_columns() -> None:
    """
    One-shot: add Phase 2 columns to deal_insight_mappings if missing.
    `create_all` doesn't issue ALTER TABLE, so existing DBs need this.
    Idempotent — re-runs are no-ops.
    """
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(deal_insight_mappings)")
        cols = {r[1] for r in rows.fetchall()}
        added: list[str] = []
        if "product_tier_field" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_mappings ADD COLUMN product_tier_field VARCHAR(255)"
            )
            added.append("product_tier_field")
        if "billing_country_field" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_mappings ADD COLUMN billing_country_field VARCHAR(255)"
            )
            added.append("billing_country_field")
        if "stage_change_date_field" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE deal_insight_mappings ADD COLUMN stage_change_date_field VARCHAR(255)"
            )
            added.append("stage_change_date_field")
        if added:
            logger.info("added deal_insight_mappings columns: %s", ", ".join(added))


async def migrate_add_crm_sync_columns() -> None:
    """
    One-shot: add DocumentLog.crm_synced_at + DocumentLog.crm_external_id.
    Populated by the CRM sync worker so the admin UI can show which offers
    made it to Salesforce and the external record id.
    """
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(document_logs)")
        cols = {r[1] for r in rows.fetchall()}
        added = []
        if "crm_synced_at" not in cols:
            await conn.exec_driver_sql("ALTER TABLE document_logs ADD COLUMN crm_synced_at DATETIME")
            added.append("crm_synced_at")
        if "crm_external_id" not in cols:
            await conn.exec_driver_sql("ALTER TABLE document_logs ADD COLUMN crm_external_id VARCHAR(64)")
            added.append("crm_external_id")
        if added:
            logger.info("added document_logs columns: %s", ", ".join(added))


async def migrate_add_user_tenant_id() -> None:
    """
    One-shot: add users.tenant_id (FK to tenants.id) if missing, then backfill
    any NULL rows via an email-domain rule.

    Backfill rule:
      - email matches *@<slug>.io for an existing tenant slug → that tenant
      - everything else → DEFAULT_TENANT_SLUG

    Idempotent — re-running is a no-op once every user has a tenant_id.
    """
    from sqlalchemy import text
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(users)")
        cols = {r[1] for r in rows.fetchall()}
        if "tenant_id" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN tenant_id VARCHAR(36) "
                "REFERENCES tenants(id)"
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users(tenant_id)"
            )
            logger.info("added users.tenant_id column + index")

    async with async_session() as db:
        # Map every existing tenant slug → tenant_id for the email-domain rule.
        tenants = (await db.execute(select(Tenant))).scalars().all()
        slug_to_id = {t.slug: t.id for t in tenants}
        default_id = slug_to_id.get(DEFAULT_TENANT_SLUG)
        if default_id is None:
            # Tenants haven't been seeded yet; bail. Will run again on next
            # startup once seed_tenants_and_products completes.
            return

        # All users with NULL tenant_id.
        unassigned = (
            await db.execute(select(User).where(User.tenant_id.is_(None)))
        ).scalars().all()
        if not unassigned:
            return

        assigned_count = 0
        for user in unassigned:
            email = (user.email or "").lower()
            domain = email.split("@", 1)[1] if "@" in email else ""
            slug = domain.split(".", 1)[0] if domain else ""
            target_id = slug_to_id.get(slug, default_id)
            user.tenant_id = target_id
            assigned_count += 1

        await db.commit()
        logger.info(
            "backfilled users.tenant_id for %d user(s)", assigned_count
        )


async def migrate_add_crm_connections_tenant_id() -> None:
    """
    One-shot: add crm_connections.tenant_id (FK to tenants.id) if missing,
    then backfill any NULL rows to the default tenant. Pre-existing rows
    are assumed to belong to the default tenant historically — there was
    only one global Salesforce/HubSpot connection before this migration.

    Idempotent — re-running is a no-op once every connection row has a
    tenant_id and the column exists.
    """
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(crm_connections)")
        cols = {r[1] for r in rows.fetchall()}
        if "tenant_id" not in cols:
            await conn.exec_driver_sql(
                "ALTER TABLE crm_connections ADD COLUMN tenant_id VARCHAR(36) "
                "REFERENCES tenants(id)"
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_crm_connections_tenant_id "
                "ON crm_connections(tenant_id)"
            )
            logger.info("added crm_connections.tenant_id column + index")

    async with async_session() as db:
        # Resolve default tenant; bail if it doesn't exist yet (fresh DB,
        # tenants haven't been seeded). Will run again on next startup.
        default_tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
        ).scalar_one_or_none()
        if default_tenant is None:
            return

        from app.models.crm_connection import CRMConnection
        unassigned = (
            await db.execute(
                select(CRMConnection).where(CRMConnection.tenant_id.is_(None))
            )
        ).scalars().all()
        if not unassigned:
            return

        for row in unassigned:
            row.tenant_id = default_tenant.id
        await db.commit()
        logger.info(
            "backfilled crm_connections.tenant_id for %d row(s) → default tenant",
            len(unassigned),
        )


async def migrate_add_icp_contact_fields() -> None:
    """
    One-shot: add Contact-level filter columns to ideal_customer_profiles.
    Idempotent — only adds the columns that don't already exist.
    """
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql(
            "PRAGMA table_info(ideal_customer_profiles)"
        )
        existing = {r[1] for r in rows.fetchall()}
        if not existing:
            # Table not yet created — Base.metadata.create_all will produce
            # the new shape directly on next init_db(). Nothing to do here.
            return
        for col, ddl in [
            ("required_contact_levels", "TEXT NOT NULL DEFAULT '[]'"),
            ("required_contact_departments", "TEXT NOT NULL DEFAULT '[]'"),
            ("min_contacts_on_account", "INTEGER"),
        ]:
            if col not in existing:
                await conn.exec_driver_sql(
                    f"ALTER TABLE ideal_customer_profiles ADD COLUMN {col} {ddl}"
                )
                logger.info(
                    "added ideal_customer_profiles.%s column", col,
                )


async def migrate_add_negotiation_mode_column() -> None:
    """
    One-shot: add tenant_configs.negotiation_mode if it's missing.

    `create_all` doesn't issue ALTER TABLE. On a fresh DB the column already
    exists from the CREATE TABLE; on an existing DB this adds it. Idempotent.
    """
    from sqlalchemy import text
    from app.core.database import engine

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(tenant_configs)")
        cols = {r[1] for r in rows.fetchall()}
        if "negotiation_mode" in cols:
            return
        await conn.exec_driver_sql(
            "ALTER TABLE tenant_configs ADD COLUMN negotiation_mode "
            "VARCHAR(20) NOT NULL DEFAULT 'deterministic'"
        )
        logger.info("added negotiation_mode column to tenant_configs")


async def migrate_tenant_config_to_guardrails() -> None:
    """
    One-shot migration. For any tenant with a TenantConfig but no
    GuardrailPolicy, create a policy row copying over approval_threshold_cents.
    Idempotent — re-running is a no-op once every tenant has a policy.
    """
    async with async_session() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        migrated = 0
        for tenant in tenants:
            existing_policy = (
                await db.execute(
                    select(GuardrailPolicy).where(GuardrailPolicy.tenant_id == tenant.id)
                )
            ).scalar_one_or_none()
            if existing_policy is not None:
                continue

            old_cfg = (
                await db.execute(
                    select(TenantConfig).where(TenantConfig.tenant_id == tenant.id)
                )
            ).scalar_one_or_none()
            threshold = (
                old_cfg.approval_threshold_cents if old_cfg is not None
                else DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS
            )
            db.add(GuardrailPolicy(
                tenant_id=tenant.id,
                require_approval_above_cents=threshold,
            ))
            migrated += 1
        if migrated:
            await db.commit()
            logger.info("migrated %d tenants from TenantConfig to GuardrailPolicy", migrated)


async def seed_tenants_and_products() -> None:
    async with async_session() as db:
        existing = await db.execute(select(Tenant).limit(1))
        if existing.scalar_one_or_none():
            return

        logger.info("Seeding tenants + product catalog...")

        default_tenant = Tenant(slug=DEFAULT_TENANT_SLUG, name="Default Org")
        acme_tenant = Tenant(slug="acme", name="Acme Corp")
        db.add_all([default_tenant, acme_tenant])
        await db.flush()

        # One TenantConfig + one GuardrailPolicy per tenant with sensible defaults.
        db.add_all([
            TenantConfig(
                tenant_id=default_tenant.id,
                approval_threshold_cents=DEFAULT_APPROVAL_THRESHOLD_CENTS,
                auto_commit_enabled=True,
            ),
            TenantConfig(
                tenant_id=acme_tenant.id,
                approval_threshold_cents=DEFAULT_APPROVAL_THRESHOLD_CENTS,
                auto_commit_enabled=True,
            ),
            GuardrailPolicy(
                tenant_id=default_tenant.id,
                require_approval_above_cents=DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS,
            ),
            GuardrailPolicy(
                tenant_id=acme_tenant.id,
                require_approval_above_cents=DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS,
            ),
        ])

        # Half agent-exposed, half internal-only so the admin toggle is
        # meaningful from day one and get_products filter tests have both cases.
        products_default = [
            Product(
                tenant_id=default_tenant.id, sku="ENT-LIC",
                name="Enterprise License", category="Licensing",
                description="Annual enterprise license with unlimited seats.",
                base_price=50000, min_price_floor=40000, unit="license",
                agent_exposed=True,
            ),
            Product(
                tenant_id=default_tenant.id, sku="SEAT-STD",
                name="Standard Seat License", category="Licensing",
                description="Per-seat annual license.",
                base_price=1200, min_price_floor=900, unit="seat",
                agent_exposed=True,
            ),
            Product(
                tenant_id=default_tenant.id, sku="SUP-PREM",
                name="Premium Support", category="Support",
                description="24/7 premium support with 1-hour response SLA.",
                base_price=10000, min_price_floor=7500, unit="year",
                agent_exposed=True,
            ),
            Product(
                tenant_id=default_tenant.id, sku="ONBOARD-PKG",
                name="Onboarding Package", category="Professional Services",
                description="One-time onboarding engagement including training and migration.",
                base_price=15000, min_price_floor=12000, unit="package",
                agent_exposed=True,
            ),
            Product(
                tenant_id=default_tenant.id, sku="PS-HOUR",
                name="Professional Services Hour", category="Professional Services",
                description="Senior consultant hourly rate.",
                base_price=275, min_price_floor=225, unit="hour",
                agent_exposed=False,  # internal only — priced case-by-case
            ),
            Product(
                tenant_id=default_tenant.id, sku="CUSTOM-INTEG",
                name="Custom Integration Build", category="Engineering",
                description="Bespoke integration engineering — scoped per deal.",
                base_price=75000, min_price_floor=50000, unit="project",
                agent_exposed=False,  # internal only — needs human scoping
            ),
        ]
        products_acme = [
            Product(
                tenant_id=acme_tenant.id, sku="ACME-PLAT",
                name="Acme Platform Subscription", category="SaaS",
                description="Acme's flagship SaaS subscription, billed annually.",
                base_price=36000, min_price_floor=28000, unit="year",
                agent_exposed=True,
            ),
            Product(
                tenant_id=acme_tenant.id, sku="ACME-ADD-ANALYTICS",
                name="Advanced Analytics Add-on", category="SaaS",
                description="Analytics module for the Acme platform.",
                base_price=8000, min_price_floor=6000, unit="year",
                agent_exposed=True,
            ),
        ]
        db.add_all([*products_default, *products_acme])

        await db.commit()
        logger.info(
            "Seeded 2 tenants and %d products (%d agent-exposed)",
            len(products_default) + len(products_acme),
            sum(1 for p in (*products_default, *products_acme) if p.agent_exposed),
        )
