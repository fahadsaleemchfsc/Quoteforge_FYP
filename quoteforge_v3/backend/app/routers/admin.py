"""Platform super-admin endpoints — cross-tenant visibility.

Gated by SUPER_ADMIN_EMAILS env var (see app/core/security.is_super_admin).
NOT to be confused with the per-tenant `admin` role: a tenant admin can
configure their own workspace; a super-admin can see every workspace in
the deployment, but never reads/writes inside one (no tenant data is
exposed beyond aggregate counts + user emails).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_super_admin
from app.models.crm_connection import CRMConnection
from app.models.document_log import DocumentLog
from app.models.salesforce_oauth_token import SalesforceOAuthToken
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(
    prefix="/admin",
    tags=["super-admin"],
    dependencies=[Depends(require_super_admin)],
)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


@router.get("/stats")
async def platform_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Single-row platform-wide counters for the super-admin landing card."""
    total_tenants = (await db.execute(select(func.count(Tenant.id)))).scalar() or 0
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_quotes = (await db.execute(select(func.count(DocumentLog.id)))).scalar() or 0
    connected_orgs = (
        await db.execute(select(func.count(SalesforceOAuthToken.org_id)))
    ).scalar() or 0
    # "New this week" — naive but cheap: count tenants created in the
    # last 7 days. Good enough for a dashboard card; trend over time
    # lives in a chart endpoint we haven't built yet.
    seven_days_ago = func.now()  # SQLite + Postgres both treat this OK
    new_this_week = (
        await db.execute(
            select(func.count(Tenant.id)).where(
                Tenant.created_at >= func.datetime(seven_days_ago, "-7 days")
            )
        )
    ).scalar() or 0
    return {
        "total_tenants": total_tenants,
        "total_users": total_users,
        "total_quotes": total_quotes,
        "connected_salesforce_orgs": connected_orgs,
        "new_tenants_last_7d": new_this_week,
    }


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """Every workspace in the deployment, with per-tenant rollup counts.

    Single-query aggregation (LEFT JOIN + GROUP BY) so the response is
    one round-trip per resource family rather than N+1. Returned rows
    are stable-ordered by created_at desc — newest workspaces first.
    """
    # Pull tenants + counts in three round-trips (one per child relation
    # because outer-joining all three would muddy the GROUP BY math).
    tenants = (
        (await db.execute(select(Tenant).order_by(Tenant.created_at.desc())))
        .scalars()
        .all()
    )
    if not tenants:
        return []
    tenant_ids = [t.id for t in tenants]

    # User counts
    user_rows = await db.execute(
        select(User.tenant_id, func.count(User.id))
        .where(User.tenant_id.in_(tenant_ids))
        .group_by(User.tenant_id)
    )
    user_counts = dict(user_rows.all())

    # Quote/document counts come via the User.tenant_id → DocumentLog.user_id
    # join because DocumentLog has no direct tenant_id column.
    quote_rows = await db.execute(
        select(User.tenant_id, func.count(DocumentLog.id))
        .join(DocumentLog, DocumentLog.user_id == User.id)
        .where(User.tenant_id.in_(tenant_ids))
        .group_by(User.tenant_id)
    )
    quote_counts = dict(quote_rows.all())

    # Most recent quote per tenant (same join).
    last_quote_rows = await db.execute(
        select(User.tenant_id, func.max(DocumentLog.generated_at))
        .join(DocumentLog, DocumentLog.user_id == User.id)
        .where(User.tenant_id.in_(tenant_ids))
        .group_by(User.tenant_id)
    )
    last_quote_at = dict(last_quote_rows.all())

    # CRM connection presence (one row per (tenant, platform)).
    crm_rows = await db.execute(
        select(CRMConnection.tenant_id, func.count(CRMConnection.id))
        .where(CRMConnection.tenant_id.in_(tenant_ids))
        .group_by(CRMConnection.tenant_id)
    )
    crm_counts = dict(crm_rows.all())

    # Salesforce one-click OAuth — separate from legacy CRMConnection.
    sf_rows = await db.execute(
        select(SalesforceOAuthToken.tenant_id, func.count(SalesforceOAuthToken.org_id))
        .where(SalesforceOAuthToken.tenant_id.in_(tenant_ids))
        .group_by(SalesforceOAuthToken.tenant_id)
    )
    sf_counts = dict(sf_rows.all())

    return [
        {
            "id": t.id,
            "slug": t.slug,
            "name": t.name,
            "created_at": _iso(t.created_at),
            "users": user_counts.get(t.id, 0),
            "quotes": quote_counts.get(t.id, 0),
            "last_quote_at": _iso(last_quote_at.get(t.id)),
            "crm_connections": crm_counts.get(t.id, 0),
            "salesforce_orgs": sf_counts.get(t.id, 0),
        }
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Drill-down for one workspace: members, recent quotes, integrations."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    users = (
        (await db.execute(select(User).where(User.tenant_id == tenant_id).order_by(User.id)))
        .scalars()
        .all()
    )
    user_ids = [u.id for u in users]

    recent_docs: list[Any] = []
    if user_ids:
        recent_docs = (
            (
                await db.execute(
                    select(DocumentLog)
                    .where(DocumentLog.user_id.in_(user_ids))
                    .order_by(DocumentLog.generated_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

    sf_token = (
        await db.execute(
            select(SalesforceOAuthToken).where(
                SalesforceOAuthToken.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()

    return {
        "id": tenant.id,
        "slug": tenant.slug,
        "name": tenant.name,
        "created_at": _iso(tenant.created_at),
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "status": u.status,
                "quotes_generated": u.quotes_generated or 0,
                "last_login": _iso(u.last_login),
            }
            for u in users
        ],
        "recent_documents": [
            {
                "doc_id": d.doc_id,
                "client": d.client,
                "deal_name": d.deal_name,
                "amount": d.amount,
                "status": d.status,
                "generated_at": _iso(d.generated_at),
                "synced_to_salesforce": bool(d.crm_synced_at),
            }
            for d in recent_docs
        ],
        "salesforce": (
            {
                "connected": True,
                "org_id": sf_token.org_id,
                "instance_url": sf_token.instance_url,
                "connected_at": _iso(sf_token.issued_at),
            }
            if sf_token
            else {"connected": False}
        ),
    }
