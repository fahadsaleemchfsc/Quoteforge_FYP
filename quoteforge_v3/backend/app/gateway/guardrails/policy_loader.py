"""
Policy loading — the only module that knows how to bridge the GuardrailPolicy
ORM row to a pure-data PolicySnapshot.

Auto-provisions a default policy row if one doesn't exist yet (e.g. legacy
tenant that predates the engine). Keeps the engine's contract clean: it never
sees a None policy.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.guardrails.engine import PolicySnapshot, snapshot_from_orm
from app.models.guardrail_policy import (
    DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS,
    GuardrailPolicy,
)
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig


@dataclass(frozen=True)
class LoadedPolicy:
    tenant_id_uuid: str          # Tenant.id, UUID
    policy_orm: GuardrailPolicy
    snapshot: PolicySnapshot
    auto_commit_enabled: bool    # from TenantConfig


async def load_policy_by_slug(db: AsyncSession, tenant_slug: str) -> LoadedPolicy | None:
    """Returns None if the tenant doesn't exist."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        return None

    policy = (
        await db.execute(select(GuardrailPolicy).where(GuardrailPolicy.tenant_id == tenant.id))
    ).scalar_one_or_none()
    if policy is None:
        # Auto-provision — belt-and-braces. ensure_tenant_by_slug already does
        # this at creation time; this is the migration-safety net.
        policy = GuardrailPolicy(
            tenant_id=tenant.id,
            require_approval_above_cents=DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS,
        )
        db.add(policy)
        await db.flush()

    cfg = (
        await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    ).scalar_one_or_none()
    auto_commit = bool(cfg.auto_commit_enabled) if cfg is not None else True

    return LoadedPolicy(
        tenant_id_uuid=tenant.id,
        policy_orm=policy,
        snapshot=snapshot_from_orm(policy),
        auto_commit_enabled=auto_commit,
    )


async def load_policy_by_uuid(db: AsyncSession, tenant_uuid: str) -> LoadedPolicy | None:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    ).scalar_one_or_none()
    if tenant is None:
        return None
    return await load_policy_by_slug(db, tenant.slug)
