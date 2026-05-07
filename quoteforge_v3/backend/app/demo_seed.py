"""
Demo seed — synthetic activity the dashboard + guardrails impact preview lean on.

Runs once (idempotent): checks if ReplayEvents already exist for the default
tenant; if any, skips. Otherwise synthesizes ~45 events spanning the last
7 days that tell a believable story.

What it generates:
  - Mix of guardrail_evaluation verdicts: ~60% pass, ~20% review, ~20% block
  - 5 recurring buyer_agent_ids so the dashboard feed shows repeat traffic
  - Realistic deal sizes in $1k–$120k range
  - Negotiation_attempt chains for a handful of offers so the
    Negotiations page has retry examples
  - Offer_id references that are looked up by the impact preview
  - DocumentLog draft + AuditLog rows paired to the events so the
    impact preview can reconstruct OfferContexts from metadata

All synthetic entries are neutral B2B SaaS deals — no regulatory references.
"""
from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.core.database import async_session
from app.gateway.money import dollars_to_cents
from app.models.audit_log import AuditLog
from app.models.document_log import DocumentLog
from app.models.product import Product
from app.models.replay_event import (
    EVENT_GUARDRAIL_EVALUATION,
    EVENT_NEGOTIATION_ATTEMPT,
    ReplayEvent,
)
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

# Rich-but-neutral buyer-agent identities. No customer names or real brands.
DEMO_BUYER_AGENTS = [
    "claude-buyer-7f3a",
    "pactum-procurement-01",
    "gpt-deals-a9b2",
    "nec-purchaser-v2",
    "zapier-procure-b14",
]

DEMO_CLIENTS = [
    "Meridian Robotics", "Helio Payments", "Northwind Labs",
    "Kestrel Analytics", "BluePeak Logistics", "Lighthouse CRM",
    "Pepper Biotech", "Marlin Security", "Orbital Retail",
    "Sable Financial", "Coastal Outfitters", "Grayscale Manufacturing",
]

REGIONS = ["US", "US", "US", "EU", "EU", "APAC", "UK"]


@dataclass(frozen=True)
class _FakeAttempt:
    attempt_number: int
    verdict: str
    proposed_unit_price_cents: int
    blocking: list[str]
    latency_ms: int
    rationale: str


def _policy_snapshot_payload() -> dict[str, Any]:
    return {
        "min_margin_percent": 15.0,
        "max_discount_percent": 20.0,
        "max_discount_with_approval_percent": 35.0,
        "allowed_regions": ["US", "EU", "APAC", "UK", "PK"],
        "currency_allowlist": ["USD"],
        "min_deal_size_cents": 0,
        "max_deal_size_cents": None,
        "require_approval_above_cents": 5_000_000,
    }


def _evaluation_payload(
    *,
    verdict: str,
    blocking: list[str],
    region: str,
    currency: str,
    line_items_snapshot: list[dict[str, Any]],
    total_cents: int,
) -> dict[str, Any]:
    """Shape mirrors what record_evaluation writes, plus offer_context_snapshot
    so impact_preview can re-evaluate against new policies without needing the
    DocumentLog join."""
    check_results: list[dict[str, Any]] = []
    for name in ("min_margin", "max_discount", "region", "currency", "deal_size", "approval_threshold"):
        if name in blocking:
            check_results.append({
                "name": name,
                "verdict": "block",
                "reason_internal": f"{name} violated (demo synthetic)",
                "reason_external": "offer exceeds allowed parameters",
                "suggested_adjustment": None,
            })
        elif verdict == "review" and name == "approval_threshold" and total_cents >= 5_000_000:
            check_results.append({
                "name": name, "verdict": "review",
                "reason_internal": "total above approval threshold",
                "reason_external": "offer requires seller review before commitment",
                "suggested_adjustment": None,
            })
        elif verdict == "review" and name == "max_discount" and not blocking:
            check_results.append({
                "name": name, "verdict": "review",
                "reason_internal": "discount above auto-approve",
                "reason_external": "offer requires seller review before commitment",
                "suggested_adjustment": None,
            })
        else:
            check_results.append({
                "name": name, "verdict": "pass",
                "reason_internal": "within limits", "reason_external": "",
                "suggested_adjustment": None,
            })
    return {
        "verdict": verdict,
        "check_results": check_results,
        "policy_snapshot": _policy_snapshot_payload(),
        "offer_context_snapshot": {
            "region": region,
            "currency": currency,
            "total_cents": total_cents,
            "line_items": line_items_snapshot,
        },
        "extra": {"phase": "request_quote", "demo_synthetic": True},
    }


def _negotiation_attempt_payload(att: _FakeAttempt, sku: str) -> dict[str, Any]:
    return {
        "attempt_number": att.attempt_number,
        "backend": "stub" if att.attempt_number <= 3 else "fallback",
        "verdict": att.verdict,
        "blocking_check_names": att.blocking,
        "latency_ms": att.latency_ms,
        "proposed_lines": [{
            "sku": sku, "quantity": 1,
            "proposed_unit_price_cents": att.proposed_unit_price_cents,
        }],
        "rationale": att.rationale,
        "confidence": 0.8 if att.verdict in ("pass", "review") else 0.4,
        "fell_back": att.verdict == "pass" and att.attempt_number > 3,
    }


async def seed_demo_activity() -> None:
    rng = random.Random(20260422)

    async with async_session() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == "default"))
        ).scalar_one_or_none()
        if tenant is None:
            logger.info("demo_seed: default tenant missing, skipping")
            return

        existing = (
            await db.execute(
                select(func.count(ReplayEvent.id)).where(ReplayEvent.tenant_id == tenant.id)
            )
        ).scalar_one()
        if existing and existing > 3:
            return

        products = (
            await db.execute(
                select(Product).where(
                    Product.tenant_id == tenant.id,
                    Product.agent_exposed.is_(True),
                )
            )
        ).scalars().all()
        if not products:
            logger.info("demo_seed: no agent-exposed products, skipping")
            return

        now = datetime.now(timezone.utc)
        total_generated = 0
        n_events_target = 45

        # Keep doc_id counter coherent with the existing seed rows.
        doc_count_now = (
            await db.execute(select(func.count(DocumentLog.id)))
        ).scalar_one() or 0
        next_doc_n = 2400 + int(doc_count_now) + 1

        for i in range(n_events_target):
            # Pick a product, synthesize a line item snapshot + offer metadata.
            product = rng.choice(products)
            qty = rng.choice([1, 1, 1, 2, 3, 5])
            base_cents = dollars_to_cents(product.base_price)
            floor_cents = dollars_to_cents(product.min_price_floor)

            # Verdict mix: 60% pass, 20% review, 20% block
            roll = rng.random()
            if roll < 0.6:
                verdict = "pass"
                unit_cents = base_cents
                blocking: list[str] = []
            elif roll < 0.8:
                verdict = "review"
                # Either threshold crossed (big deal) or discount above auto
                if rng.random() < 0.5 and qty * base_cents > 5_000_000:
                    unit_cents = base_cents
                else:
                    unit_cents = int(base_cents * 0.75)    # 25% discount — review
                blocking = []
            else:
                verdict = "block"
                blocking_choices = [
                    ["min_margin"], ["max_discount"], ["region"], ["min_margin", "max_discount"],
                ]
                blocking = rng.choice(blocking_choices)
                if "min_margin" in blocking:
                    unit_cents = max(1, int(floor_cents * 0.9))
                else:
                    unit_cents = int(base_cents * 0.4)  # 60% discount — above ceiling

            total_cents = unit_cents * qty
            currency = product.currency or "USD"
            region = rng.choice(REGIONS)
            agent = rng.choice(DEMO_BUYER_AGENTS)
            client = rng.choice(DEMO_CLIENTS)

            # Spread events across last 7 days with more weight toward recent.
            minutes_ago = int(rng.triangular(5, 7 * 24 * 60, 60))
            ts = now - timedelta(minutes=minutes_ago)

            offer_id = f"ofr_demo_{uuid.uuid4().hex[:12]}"
            doc_id = f"DOC-{next_doc_n}"
            next_doc_n += 1

            line_items_snapshot = [{
                "sku": product.sku, "quantity": qty,
                "unit_price_cents": unit_cents,
                "base_price_cents": base_cents,
                "min_price_floor_cents": floor_cents,
            }]

            # DocumentLog draft with offer_payload so offers/{id}/pdf works
            offer_payload = {
                "offer_id": offer_id,
                "doc_id": doc_id,
                "tenant_id": "default",
                "issued_at": ts.isoformat(),
                "valid_until": (ts + timedelta(days=30)).isoformat(),
                "client_name": client,
                "deal_name": f"Q{(ts.month - 1) // 3 + 1} Renewal",
                "region": region,
                "contact_email": "",
                "line_items": [{
                    "sku": product.sku, "product_id": product.id,
                    "product_name": product.name, "description": product.description or "",
                    "quantity": qty,
                    "unit_price": round(unit_cents / 100, 2),
                    "line_total": round((unit_cents * qty) / 100, 2),
                    "unit": product.unit,
                }],
                "pricing": {
                    "subtotal": round((unit_cents * qty) / 100, 2),
                    "discount": round(max(0, (base_cents - unit_cents) * qty) / 100, 2),
                    "discount_details": [],
                    "tax": 0.0,
                    "tax_details": [],
                    "total": round((unit_cents * qty) / 100, 2),
                    "total_cents": total_cents,
                    "currency": currency,
                },
            }
            doc_status = (
                "draft" if verdict == "block"
                else ("pending_approval" if verdict == "review" else "committed")
            )
            doc = DocumentLog(
                doc_id=doc_id,
                deal_id="",
                client=client,
                deal_name=offer_payload["deal_name"],
                type="Quote",
                format="JSON",
                status=doc_status,
                delivery_status="pending",
                file_path="",
                amount=total_cents / 100,
                generation_time=rng.uniform(1.5, 4.5),
                valid_until=ts + timedelta(days=30),
                metadata_json=json.dumps({
                    "tenant_slug": "default",
                    "mcp_principal": agent,
                    "offer_id": offer_id,
                    "offer_signature": f"demo_sig_{uuid.uuid4().hex[:24]}",
                    "offer_payload": offer_payload,
                    "source": "agent_gateway",
                    "product_ids": [product.id],
                    "demo_synthetic": True,
                }),
                user_id=None,
                user_name=f"mcp:{agent}",
                generated_at=ts,
            )
            db.add(doc)

            # Guardrail replay event
            db.add(ReplayEvent(
                tenant_id=tenant.id,
                event_type=EVENT_GUARDRAIL_EVALUATION,
                offer_id=offer_id,
                document_log_id=None,
                principal_id=agent,
                payload=json.dumps(_evaluation_payload(
                    verdict=verdict, blocking=blocking,
                    region=region, currency=currency,
                    line_items_snapshot=line_items_snapshot,
                    total_cents=total_cents,
                ), default=str),
                created_at=ts,
            ))

            # For a fraction of events, add negotiation_attempt chain
            if verdict != "block" and rng.random() < 0.4:
                # Emit 1-2 attempt rows — if >1 then first attempt was blocked retry.
                chain_len = rng.choice([1, 1, 2, 3])
                for idx in range(1, chain_len + 1):
                    att_verdict = verdict if idx == chain_len else "block"
                    att_block = ["min_margin"] if att_verdict == "block" else []
                    att_price = int(floor_cents * 0.95) if att_verdict == "block" else unit_cents
                    att = _FakeAttempt(
                        attempt_number=idx, verdict=att_verdict,
                        proposed_unit_price_cents=att_price,
                        blocking=att_block,
                        latency_ms=int(rng.uniform(200, 1400)),
                        rationale=("reconsidered after prior block"
                                   if idx > 1 else "initial proposal"),
                    )
                    db.add(ReplayEvent(
                        tenant_id=tenant.id,
                        event_type=EVENT_NEGOTIATION_ATTEMPT,
                        offer_id=offer_id,
                        document_log_id=None,
                        principal_id=agent,
                        payload=json.dumps(_negotiation_attempt_payload(att, product.sku), default=str),
                        created_at=ts + timedelta(seconds=idx * 2),
                    ))

            # A few accept/reject / committed AuditLog rows so the feed shows
            # closure events, not just evaluations.
            if verdict == "pass" and rng.random() < 0.6:
                db.add(AuditLog(
                    user_id=None,
                    user_name=f"mcp:{agent}",
                    action="offer_committed",
                    entity_type="offer",
                    entity_id=offer_id,
                    details=f"doc={doc_id} tenant=default total={total_cents/100:.2f} {currency} via=agent_gateway",
                    timestamp=ts + timedelta(seconds=8),
                ))
            elif verdict == "review" and rng.random() < 0.4:
                db.add(AuditLog(
                    user_id=None,
                    user_name=f"mcp:{agent}",
                    action="offer_queued_for_approval",
                    entity_type="offer",
                    entity_id=offer_id,
                    details=f"doc={doc_id} tenant=default total={total_cents/100:.2f} {currency}",
                    timestamp=ts + timedelta(seconds=4),
                ))

            total_generated += 1

        await db.commit()
        logger.info("demo_seed: wrote %d synthetic events", total_generated)
