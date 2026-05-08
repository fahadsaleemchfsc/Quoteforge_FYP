"""
SOQL helpers for Deal Insights training + inference.

Two fetch paths:

  fetch_closed_opportunities  — historical training data
  fetch_opportunity_by_id     — a single Opp for live prediction
  fetch_activities_for_opportunities — Task + Event rows joined by WhatId

Dev-fallback: if no live SF connection exists, a synthetic generator produces
300 plausible closed Opportunities spanning 24 months with a clear signal
pattern (larger amounts × more activities → higher win rate). This is what
lets the end-to-end trainer demo run on a Dev Edition org that doesn't yet
have enough closed deals.
"""
from __future__ import annotations

import logging
import os
import pickle
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.database import async_session
from app.services.insights.features import MappingBundle
from app.services.salesforce_connector import get_salesforce_client

logger = logging.getLogger(__name__)


SOQL_BATCH_LIMIT = 200

# When INSIGHTS_REAL_DATA_PATH points at a pickle produced by
# training.import_real_dataset, the trainer pulls from that file instead of
# generating synthetic opps. Highest priority after live SF, so a dev setup
# with SF connected still wins — but unit-demo training uses the real/
# enriched pickle without any code swaps.
_REAL_DATA_ENV = "INSIGHTS_REAL_DATA_PATH"

# Per-opp activity-count hint populated by _synthetic_closed_opportunities so
# that fetch_activities_for_opportunities can return an activity list that
# matches the latent score used to generate the label. Keeps training signal
# coherent across Opp and Activity records.
_SYN_ACTIVITY_HINTS: dict[str, int] = {}


def _synthetic_activity_count_for(rnd: random.Random, latent: float) -> int:
    """Activity count is signal-driven with tight σ so it's discriminative."""
    base_mean = max(0.5, 1.5 + 2.5 * latent)
    return max(0, int(rnd.gauss(base_mean, 1.0)))


def _load_real_data_override(
    mapping: MappingBundle,
) -> list[dict[str, Any]] | None:
    """Return the real/enriched training dataset if INSIGHTS_REAL_DATA_PATH
    points at a valid pickle; otherwise None.

    The env var can point at the cross-object-enriched v2 pickle (Phase 2+)
    or the v1 pickle. Cross-object fields (`_contact_activities`,
    `_account_activities`, `_contact_count_on_account`) ride through
    unchanged to the feature frame.
    """
    path = os.environ.get(_REAL_DATA_ENV)
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        logger.warning("insights.fetch: %s=%s but file does not exist", _REAL_DATA_ENV, path)
        return None
    try:
        with open(p, "rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        logger.warning("insights.fetch: failed to load %s (%s)", path, e)
        return None
    opps = payload.get("opportunities") or []
    for o in opps:
        hint = o.pop("_activity_count_hint", None)
        if hint is not None:
            _SYN_ACTIVITY_HINTS[o.get("Id")] = int(hint)
    return opps


async def fetch_closed_opportunities(
    *,
    tenant_id: str,
    mapping: MappingBundle,
    excluded_record_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return closed Opps flattened into dicts the feature pipeline can consume.

    Uses SF when connected; falls back to synthetic for dev. The synthetic
    path is deterministic (seeded) so training metrics are reproducible
    during demos.
    """
    async with async_session() as db:
        sf = await get_salesforce_client(db, tenant_id)

    if sf is None:
        real = _load_real_data_override(mapping)
        if real is not None:
            logger.info(
                "insights.fetch: using real-data override (%d rows) from %s",
                len(real), os.environ.get(_REAL_DATA_ENV),
            )
            return real
        logger.info("insights.fetch: no SF connection — using synthetic training set")
        return _synthetic_closed_opportunities(mapping, n=300, seed=42)

    # Live SF path. Request the mapped fields explicitly so the SOQL stays
    # minimal + the trainer never accidentally depends on fields the mapping
    # doesn't know about.
    select_cols = _mapped_select_columns(mapping)
    where_clauses = [f"{mapping.is_closed_field}=TRUE"]
    if excluded_record_types:
        ids = ", ".join(f"'{rt}'" for rt in excluded_record_types)
        where_clauses.append(f"{mapping.record_type_field or 'RecordTypeId'} NOT IN ({ids})")
    where_sql = " AND ".join(where_clauses)

    soql = (
        f"SELECT Id, {select_cols} FROM Opportunity "
        f"WHERE {where_sql} ORDER BY {mapping.close_date_field} DESC LIMIT 5000"
    )
    try:
        records = await sf._query(soql)
    except Exception as e:
        logger.warning("insights.fetch: SOQL failed (%s), falling back to synthetic", e)
        return _synthetic_closed_opportunities(mapping, n=300, seed=42)

    return [_flatten_record(r) for r in records]


async def fetch_opportunity_by_id(
    *,
    tenant_id: str,
    mapping: MappingBundle,
    opportunity_id: str,
) -> dict[str, Any] | None:
    """Fetch Opportunity plus cross-object relations (Contact/Account
    activities). Returns the flattened Opp dict with `_contact_activities`,
    `_account_activities`, `_contact_count_on_account` injected so the
    feature pipeline sees the same shape training does.
    """
    async with async_session() as db:
        sf = await get_salesforce_client(db, tenant_id)
    if sf is None:
        # No live Salesforce client for this tenant — return None so the
        # predictor surfaces a clean 404 to the caller. Previously this path
        # fell back to _synthetic_single_opp, which silently fabricated a
        # prediction from a hardcoded healthy-deal profile. That hid real
        # disconnect/reauth failures from the LWC.
        logger.warning(
            "insights.fetch: no Salesforce client for tenant=%s — "
            "predict path will return 404 for opp %s",
            tenant_id, opportunity_id,
        )
        return None

    select_cols = _mapped_select_columns(mapping)
    soql = (
        f"SELECT Id, AccountId, {select_cols} FROM Opportunity "
        f"WHERE Id='{opportunity_id}' LIMIT 1"
    )
    try:
        rows = await sf._query(soql)
    except Exception as e:
        logger.warning("insights.fetch: opp %s failed (%s)", opportunity_id, e)
        return None
    if not rows:
        return None
    opp = _flatten_record(rows[0])
    await _enrich_opp_with_relations(sf, opp)
    return opp


async def _enrich_opp_with_relations(sf, opp: dict[str, Any]) -> None:
    """Populate `_contact_activities`, `_account_activities`, and
    `_contact_count_on_account` on the flattened Opp. All queries best-effort:
    a permission or API failure leaves the fields at their safe defaults
    (empty lists / 0) and the feature engineer produces UNKNOWN-style inputs.
    """
    opp["_contact_activities"] = []
    opp["_account_activities"] = []
    opp["_contact_count_on_account"] = 0
    # Contact field values consumed by the deterministic ICP scorer (NOT by
    # the LightGBM feature pipeline). features.py does not read these — kept
    # off the model surface so v1's pkl stays valid.
    opp["_primary_contact_title"] = ""
    opp["_primary_contact_department"] = ""

    account_id = opp.get("AccountId")
    one_year_ago = (datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat()

    # Primary Contact via OpportunityContactRole (IsPrimary=TRUE).
    primary_contact_id: str | None = None
    try:
        role_rows = await sf._query(
            f"SELECT ContactId FROM OpportunityContactRole "
            f"WHERE OpportunityId='{opp.get('Id')}' AND IsPrimary=TRUE LIMIT 1"
        )
        if role_rows:
            primary_contact_id = role_rows[0].get("ContactId")
    except Exception as e:
        logger.info("insights.enrich: primary-contact query failed (%s)", e)

    # Pull primary Contact's Title + Department for the ICP scorer's
    # required_contact_levels / required_contact_departments rules. Failure
    # leaves the fields empty strings — the scorer treats empty as "no value"
    # which fails any specified rule (consistent with existing hard filters).
    if primary_contact_id:
        try:
            c_rows = await sf._query(
                f"SELECT Title, Department FROM Contact "
                f"WHERE Id='{primary_contact_id}' LIMIT 1"
            )
            if c_rows:
                opp["_primary_contact_title"] = c_rows[0].get("Title") or ""
                opp["_primary_contact_department"] = c_rows[0].get("Department") or ""
        except Exception as e:
            logger.info("insights.enrich: contact-fields query failed (%s)", e)

    # Activities on the primary Contact (Task + Event via WhoId).
    if primary_contact_id:
        for sobj in ("Task", "Event"):
            try:
                acts = await sf._query(
                    f"SELECT Id, ActivityDate, CreatedDate, Type FROM {sobj} "
                    f"WHERE WhoId='{primary_contact_id}' "
                    f"AND (ActivityDate >= {one_year_ago} OR CreatedDate >= {one_year_ago}T00:00:00Z) "
                    f"LIMIT 200"
                )
                opp["_contact_activities"].extend(acts)
            except Exception as e:
                logger.info("insights.enrich: contact %s query failed (%s)", sobj, e)

    # Account-level: Tasks/Events where WhatId = AccountId + rough Contact count.
    if account_id:
        for sobj in ("Task", "Event"):
            try:
                acts = await sf._query(
                    f"SELECT Id, ActivityDate, CreatedDate, Type FROM {sobj} "
                    f"WHERE WhatId='{account_id}' "
                    f"AND (ActivityDate >= {one_year_ago} OR CreatedDate >= {one_year_ago}T00:00:00Z) "
                    f"LIMIT 500"
                )
                opp["_account_activities"].extend(acts)
            except Exception as e:
                logger.info("insights.enrich: account %s query failed (%s)", sobj, e)
        try:
            contact_rows = await sf._query(
                f"SELECT COUNT(Id) c FROM Contact WHERE AccountId='{account_id}'"
            )
            if contact_rows:
                opp["_contact_count_on_account"] = int(contact_rows[0].get("c") or 0)
        except Exception as e:
            logger.info("insights.enrich: contact-count query failed (%s)", e)


async def fetch_opportunity_with_relations(
    *,
    tenant_id: str,
    mapping: MappingBundle,
    opportunity_id: str,
) -> dict[str, Any] | None:
    """Public alias for fetch_opportunity_by_id — the Phase 2 spec name.
    Kept as a thin wrapper so existing callers continue to work."""
    return await fetch_opportunity_by_id(
        tenant_id=tenant_id, mapping=mapping, opportunity_id=opportunity_id,
    )


async def fetch_activities_for_opportunities(
    *,
    tenant_id: str,
    opportunity_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Pull Task + Event rows for each Opp. Returns {opp_id: [records]}.

    SOQL has a per-query IN list cap — we chunk into batches of 200.
    """
    out: dict[str, list[dict[str, Any]]] = {oid: [] for oid in opportunity_ids}
    if not opportunity_ids:
        return out

    async with async_session() as db:
        sf = await get_salesforce_client(db, tenant_id)
    if sf is None:
        # Synthetic: if we have a hint from the Opp generator, honor it so
        # features line up. Otherwise fall back to a small random count.
        rnd = random.Random(7)
        today = datetime.now(timezone.utc).date()
        for oid in opportunity_ids:
            count = _SYN_ACTIVITY_HINTS.get(oid, rnd.randint(0, 5))
            out[oid] = [
                {"ActivityDate": (today - timedelta(days=rnd.randint(0, 60))).isoformat()}
                for _ in range(count)
            ]
        return out

    for start in range(0, len(opportunity_ids), SOQL_BATCH_LIMIT):
        chunk = opportunity_ids[start:start + SOQL_BATCH_LIMIT]
        ids_sql = ", ".join(f"'{oid}'" for oid in chunk)
        for sobj in ("Task", "Event"):
            soql = (
                f"SELECT Id, WhatId, ActivityDate, CreatedDate FROM {sobj} "
                f"WHERE WhatId IN ({ids_sql})"
            )
            try:
                rows = await sf._query(soql)
            except Exception as e:
                logger.info("insights.fetch: %s query failed (%s) — continuing", sobj, e)
                continue
            for r in rows:
                wid = r.get("WhatId")
                if wid in out:
                    out[wid].append(r)
    return out


# ─── SOQL helpers ──────────────────────────────────────────────────

def _mapped_select_columns(mapping: MappingBundle) -> str:
    """Build the comma-separated select clause from the mapping."""
    cols: list[str] = [
        mapping.amount_field,
        mapping.stage_field,
        mapping.close_date_field,
        mapping.created_date_field,
        mapping.is_closed_field,
        mapping.is_won_field,
    ]
    for optional in (
        mapping.industry_field,
        mapping.lead_source_field,
        mapping.owner_field,
        mapping.record_type_field,
    ):
        if optional:
            cols.append(optional)
    for cf in mapping.custom_fields:
        sf = cf.get("sf_field")
        if sf:
            cols.append(sf)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for c in cols:
        if c and c not in seen and c != "Id":
            ordered.append(c)
            seen.add(c)
    return ", ".join(ordered)


def _flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    """Keep dot-notation nested lookups (Account.Industry) resolvable by the
    feature engineer. `_get_nested` in features.py walks the dict — so we
    leave the nested shape intact."""
    # Strip SOQL `attributes` metadata which pollutes the dict.
    out = {k: v for k, v in record.items() if k != "attributes"}
    if "Account" in out and isinstance(out["Account"], dict):
        out["Account"] = {
            k: v for k, v in out["Account"].items() if k != "attributes"
        }
    return out


# ─── Synthetic dataset for dev/demo ────────────────────────────────

_INDUSTRIES = ["Technology", "Finance", "Healthcare", "Manufacturing",
               "Retail", "Education", "Government", "Energy"]
_SOURCES = ["Web", "Partner", "Inbound Call", "Referral", "Trade Show", "Email Campaign"]
_OWNERS = [f"005{i:03d}" for i in range(1, 9)]   # fake owner IDs
_STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation"]


def _synthetic_closed_opportunities(
    mapping: MappingBundle,
    *,
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Generate a clear-signal synthetic dataset.

    Signal = amount + industry + source + activity_count drive the label.
    The activity count correlates with the latent score (see
    _synthetic_activity_count_for), so training picks up a coherent pattern
    and produces a useful LightGBM model without a live SF connection.
    """
    rnd = random.Random(seed)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []

    for i in range(n):
        amount = max(500.0, rnd.lognormvariate(10.5, 1.2))
        age_days = rnd.randint(15, 720)
        created = today - timedelta(days=age_days)
        close_days_ago = rnd.randint(0, age_days - 1)
        close = today - timedelta(days=close_days_ago)

        industry = rnd.choice(_INDUSTRIES)
        source = rnd.choice(_SOURCES)
        owner = rnd.choice(_OWNERS)

        # Coherent latent — matches the eval harness shape.
        latent = 0.0
        latent += min(4.0, amount / 40_000.0)
        latent += 1.5 if industry == "Technology" else 0.0
        latent += 1.0 if industry == "Finance" else 0.0
        latent -= 1.0 if industry in {"Government", "Education"} else 0.0
        latent += 0.8 if source in {"Referral", "Partner"} else 0.0
        latent -= 0.8 if source == "Trade Show" else 0.0

        activity_count = _synthetic_activity_count_for(rnd, latent)
        score = latent - 2.5 + 0.3 * activity_count + rnd.gauss(0, 0.15)
        is_won = score > 0
        # Stash the activity_count so fetch_activities can mirror it deterministically.
        _SYN_ACTIVITY_HINTS[f"006SYN{i:04d}{seed:04d}"] = activity_count

        rows.append({
            "Id": f"006SYN{i:04d}{seed:04d}",
            mapping.amount_field: amount,
            mapping.stage_field: "Closed Won" if is_won else "Closed Lost",
            mapping.close_date_field: close.isoformat(),
            mapping.created_date_field: created.isoformat(),
            mapping.is_closed_field: True,
            mapping.is_won_field: is_won,
            "Account": {"Industry": industry},
            mapping.lead_source_field or "LeadSource": source,
            mapping.owner_field or "OwnerId": owner,
            mapping.record_type_field or "RecordTypeId": None,
        })
    return rows


def _synthetic_single_opp(mapping: MappingBundle, *, opp_id: str) -> dict[str, Any]:
    """Emit one synthetic open Opportunity so predictor has something to chew
    on when SF isn't connected. Values are picked to yield ~60-80% probability
    (healthy deal profile — big amount, Technology industry, Referral source,
    plenty of activity via the hint).
    """
    today = datetime.now(timezone.utc).date()
    # Seed a reasonable activity count so fetch_activities returns something
    # meaningful for this Opp when SF isn't wired up.
    _SYN_ACTIVITY_HINTS.setdefault(opp_id, 6)

    # Cross-object signals that match a healthy enterprise deal profile.
    contact_acts = [
        {"ActivityDate": (today - timedelta(days=d)).isoformat(), "Type": t}
        for d, t in [(3, "Call"), (9, "Email"), (14, "Demo"),
                     (21, "Meeting"), (35, "Email")]
    ]
    account_acts = contact_acts + [
        {"ActivityDate": (today - timedelta(days=d)).isoformat(), "Type": t}
        for d, t in [(7, "Email"), (18, "Call"), (42, "Meeting"),
                     (60, "Email"), (85, "Call"), (120, "Demo")]
    ]

    return {
        "Id": opp_id,
        mapping.amount_field: 120_000.0,
        mapping.stage_field: "Proposal",
        mapping.close_date_field: (today + timedelta(days=30)).isoformat(),
        mapping.created_date_field: (today - timedelta(days=45)).isoformat(),
        mapping.is_closed_field: False,
        mapping.is_won_field: False,
        "Account": {"Industry": "Technology", "BillingCountry": "United States"},
        mapping.lead_source_field or "LeadSource": "Referral",
        mapping.owner_field or "OwnerId": "005001",
        mapping.record_type_field or "RecordTypeId": None,
        # Weak-signal fields the training data has directly.
        "ProductTier": "Enterprise",
        "SalesRegion": "NA",
        "Quarter": f"Q{(today.month - 1) // 3 + 1}",
        # Cross-object signals (Phase 2).
        "_contact_activities": contact_acts,
        "_account_activities": account_acts,
        "_contact_count_on_account": 4,
    }


def _sigmoid(x: float) -> float:
    # Numerically-stable sigmoid.
    if x >= 0:
        z = pow(2.718281828, -x)
        return 1 / (1 + z)
    z = pow(2.718281828, x)
    return z / (1 + z)
