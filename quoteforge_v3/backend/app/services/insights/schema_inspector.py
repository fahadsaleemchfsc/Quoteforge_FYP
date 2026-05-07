"""
Salesforce schema inspection + rule-based auto-mapping.

The Mapping Wizard calls inspect_salesforce_schema(tenant_id) to discover what
fields exist in the customer's Opportunity object, then suggest_mapping(schema)
to pick sensible defaults. The admin reviews and optionally edits those before
saving via POST /api/insights/mapping.

If no Salesforce connection is configured, inspect_salesforce_schema returns
a "stock" schema built from standard Opportunity fields so the wizard still
renders during dev + demo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.salesforce_connector import get_salesforce_client

logger = logging.getLogger(__name__)


# Stock Opportunity fields used when SF isn't connected — mirrors the standard
# Dev Edition schema. Keeps the wizard functional end-to-end without requiring
# a live org on first run.
STOCK_OPPORTUNITY_FIELDS: list[dict[str, str]] = [
    {"api_name": "Amount",          "label": "Amount",          "type": "currency"},
    {"api_name": "StageName",       "label": "Stage",           "type": "picklist"},
    {"api_name": "CloseDate",       "label": "Close Date",      "type": "date"},
    {"api_name": "CreatedDate",     "label": "Created Date",    "type": "datetime"},
    {"api_name": "IsClosed",        "label": "Closed",          "type": "boolean"},
    {"api_name": "IsWon",           "label": "Won",             "type": "boolean"},
    {"api_name": "LeadSource",      "label": "Lead Source",     "type": "picklist"},
    {"api_name": "OwnerId",         "label": "Owner ID",        "type": "reference"},
    {"api_name": "RecordTypeId",    "label": "Record Type ID",  "type": "reference"},
    {"api_name": "Probability",     "label": "Probability (%)", "type": "percent"},
    {"api_name": "Type",            "label": "Opportunity Type","type": "picklist"},
    {"api_name": "ForecastCategory","label": "Forecast Category","type": "picklist"},
    {"api_name": "NextStep",        "label": "Next Step",       "type": "string"},
    {"api_name": "AccountId",       "label": "Account ID",      "type": "reference"},
    {"api_name": "Name",            "label": "Opportunity Name","type": "string"},
    # Account-side relation fields — reachable via dot notation in SOQL.
    {"api_name": "Account.Industry","label": "Account Industry","type": "picklist"},
    {"api_name": "Account.Type",    "label": "Account Type",    "type": "picklist"},
]


# ─── Inspection ────────────────────────────────────────────────────

async def inspect_salesforce_schema(
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Query SF describe + counts. Falls back to stock schema if no connection.

    Returns:
        {
          "opportunity_fields": [{"api_name","label","type"}],
          "custom_fields":      [...custom-only subset...],
          "record_types":       [{"id","name"}],
          "detected_activity_types": ["Task","Event"],
          "opportunity_count":  int,
          "connected":          bool,
        }
    """
    sf = await get_salesforce_client(db, tenant_id)
    if sf is None:
        logger.info("insights: no SF connection, returning stock schema (tenant=%s)", tenant_id)
        return _stock_schema()

    try:
        describe = await sf._get("/sobjects/Opportunity/describe")
    except Exception as e:
        logger.warning("insights: Opportunity describe failed (%s), falling back to stock", e)
        return _stock_schema()

    fields_raw = describe.get("fields", [])
    opportunity_fields: list[dict[str, str]] = [
        {
            "api_name": f["name"],
            "label": f.get("label") or f["name"],
            "type": f.get("type") or "string",
        }
        for f in fields_raw
        if _keep_field_for_mapping(f)
    ]

    # Add Account relation fields — they're not in Opportunity.describe but are
    # reachable via SOQL dot notation. Offering them in the wizard lets admins
    # pick industry / account type without extra describe calls.
    opportunity_fields.extend([
        {"api_name": "Account.Industry","label": "Account Industry","type": "picklist"},
        {"api_name": "Account.Type",    "label": "Account Type",    "type": "picklist"},
    ])

    custom_fields = [f for f in opportunity_fields if f["api_name"].endswith("__c")]

    # Record types — best-effort SOQL. If the user lacks permission, silently
    # return empty list; the wizard handles that gracefully.
    record_types: list[dict[str, str]] = []
    try:
        rt_rows = await sf._query(
            "SELECT Id, Name FROM RecordType WHERE SObjectType='Opportunity'"
        )
        record_types = [
            {"id": r.get("Id", ""), "name": r.get("Name", "")}
            for r in rt_rows
            if r.get("Id")
        ]
    except Exception as e:
        logger.info("insights: record type query failed (%s) — proceeding without", e)

    # Opportunity count for the "Found X Opportunities" summary header.
    opp_count = 0
    try:
        # COUNT() returns [{totalSize: N}]; using COUNT(Id) for portability.
        count_rows = await sf._query("SELECT COUNT(Id) c FROM Opportunity")
        if count_rows:
            opp_count = int(count_rows[0].get("c") or 0)
    except Exception as e:
        logger.info("insights: opp count failed (%s)", e)

    # Activity types: Task + Event are standard SF activity objects. We don't
    # probe per-Opp here — activity_count is computed at training time.
    activity_types = ["Task", "Event"]

    return {
        "opportunity_fields": opportunity_fields,
        "custom_fields": custom_fields,
        "record_types": record_types,
        "detected_activity_types": activity_types,
        "opportunity_count": opp_count,
        "connected": True,
    }


def _stock_schema() -> dict[str, Any]:
    custom = [f for f in STOCK_OPPORTUNITY_FIELDS if f["api_name"].endswith("__c")]
    return {
        "opportunity_fields": list(STOCK_OPPORTUNITY_FIELDS),
        "custom_fields": custom,
        "record_types": [],
        "detected_activity_types": ["Task", "Event"],
        "opportunity_count": 0,
        "connected": False,
    }


def _keep_field_for_mapping(f: dict[str, Any]) -> bool:
    """Drop non-usable fields — blobs, compound addresses, geolocation, etc."""
    ftype = (f.get("type") or "").lower()
    if ftype in {"base64", "address", "location", "encryptedstring"}:
        return False
    # Compound fields (e.g. `BillingAddress`) — they're surfaced as their
    # components separately. Skip the aggregate.
    if f.get("compoundFieldName"):
        return False
    return True


# ─── Auto-mapping ───────────────────────────────────────────────────

@dataclass
class MappingSuggestion:
    """A single field's suggested mapping with a confidence + rationale."""
    field_name: str              # logical name, e.g. "amount_field"
    sf_field: str | None         # resolved SF API name, or None if nothing matched
    confidence: float            # 0.0 - 1.0
    reason: str                  # human-readable rationale for the suggestion


@dataclass
class DealInsightMappingDraft:
    """Draft mapping emitted by suggest_mapping().

    The wizard pre-fills its form from this; admin reviews and submits.
    """
    amount_field: str = "Amount"
    stage_field: str = "StageName"
    close_date_field: str = "CloseDate"
    created_date_field: str = "CreatedDate"
    is_closed_field: str = "IsClosed"
    is_won_field: str = "IsWon"
    industry_field: str | None = "Account.Industry"
    lead_source_field: str | None = "LeadSource"
    owner_field: str | None = "OwnerId"
    record_type_field: str | None = "RecordTypeId"
    excluded_record_types: list[str] = field(default_factory=list)
    custom_fields: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[MappingSuggestion] = field(default_factory=list)

    def to_response(self) -> dict[str, Any]:
        return {
            "amount_field": self.amount_field,
            "stage_field": self.stage_field,
            "close_date_field": self.close_date_field,
            "created_date_field": self.created_date_field,
            "is_closed_field": self.is_closed_field,
            "is_won_field": self.is_won_field,
            "industry_field": self.industry_field,
            "lead_source_field": self.lead_source_field,
            "owner_field": self.owner_field,
            "record_type_field": self.record_type_field,
            "excluded_record_types": list(self.excluded_record_types),
            "custom_fields": list(self.custom_fields),
            "suggestions": [
                {"field": s.field_name, "sf_field": s.sf_field,
                 "confidence": s.confidence, "reason": s.reason}
                for s in self.suggestions
            ],
        }


def suggest_mapping(schema: dict[str, Any]) -> DealInsightMappingDraft:
    """Rule-based matcher. Emits a draft mapping with suggestion rationales.

    Rules are deliberately conservative — when there's a canonical SF field
    name (Amount, StageName, CloseDate, …), use it. For optional feature
    fields (industry, lead source), only populate when the field is actually
    present in the schema.
    """
    fields = schema.get("opportunity_fields", [])
    api_names = {f["api_name"] for f in fields}
    by_name: dict[str, dict[str, str]] = {f["api_name"]: f for f in fields}

    draft = DealInsightMappingDraft()
    sugg: list[MappingSuggestion] = []

    def _apply(field_name: str, suggestion: MappingSuggestion) -> None:
        """Record the suggestion and apply the matched sf_field to the draft
        when one was found. Keeps the default when no match, so the admin
        still sees the canonical name pre-filled in the wizard."""
        sugg.append(suggestion)
        if suggestion.sf_field and suggestion.confidence >= 0.7:
            setattr(draft, field_name, suggestion.sf_field)

    # ── Required fields — canonical SF Opportunity schema ────────────
    _apply("amount_field", _match_canonical(
        "amount_field", "Amount", api_names, by_name,
        type_preference=("currency", "double"),
        fuzzy_contains=("amount", "value", "revenue"),
    ))
    _apply("stage_field", _match_canonical(
        "stage_field", "StageName", api_names, by_name,
        fuzzy_contains=("stage",),
    ))
    _apply("close_date_field", _match_canonical(
        "close_date_field", "CloseDate", api_names, by_name,
        type_preference=("date",),
        fuzzy_contains=("close",),
    ))
    _apply("created_date_field", _match_canonical(
        "created_date_field", "CreatedDate", api_names, by_name,
        type_preference=("datetime",),
        fuzzy_contains=("created",),
    ))
    _apply("is_closed_field", _match_canonical(
        "is_closed_field", "IsClosed", api_names, by_name,
        type_preference=("boolean",),
    ))
    _apply("is_won_field", _match_canonical(
        "is_won_field", "IsWon", api_names, by_name,
        type_preference=("boolean",),
    ))

    # ── Optional feature fields ──────────────────────────────────────
    if "Account.Industry" in api_names:
        draft.industry_field = "Account.Industry"
        sugg.append(MappingSuggestion("industry_field", "Account.Industry", 1.0,
                                      "Found standard Account.Industry relation field."))
    else:
        draft.industry_field = None
        sugg.append(MappingSuggestion("industry_field", None, 0.0,
                                      "No Account.Industry relation available."))

    draft.lead_source_field = "LeadSource" if "LeadSource" in api_names else None
    sugg.append(MappingSuggestion(
        "lead_source_field", draft.lead_source_field,
        1.0 if draft.lead_source_field else 0.0,
        "Standard LeadSource picklist." if draft.lead_source_field
        else "No LeadSource field in the Opportunity schema.",
    ))

    draft.owner_field = "OwnerId" if "OwnerId" in api_names else None
    sugg.append(MappingSuggestion(
        "owner_field", draft.owner_field, 1.0 if draft.owner_field else 0.0,
        "Standard OwnerId reference." if draft.owner_field else "No OwnerId found.",
    ))

    has_record_types = bool(schema.get("record_types"))
    if has_record_types and "RecordTypeId" in api_names:
        draft.record_type_field = "RecordTypeId"
        sugg.append(MappingSuggestion(
            "record_type_field", "RecordTypeId", 1.0,
            f"Record types enabled ({len(schema['record_types'])} found).",
        ))
    else:
        draft.record_type_field = None
        sugg.append(MappingSuggestion(
            "record_type_field", None, 0.0,
            "Record types not enabled on this Opportunity object.",
        ))

    draft.excluded_record_types = []
    draft.custom_fields = []
    draft.suggestions = sugg
    return draft


def _match_canonical(
    field_name: str,
    canonical_api: str,
    api_names: set[str],
    by_name: dict[str, dict[str, str]],
    *,
    type_preference: tuple[str, ...] = (),
    fuzzy_contains: tuple[str, ...] = (),
) -> MappingSuggestion:
    """Pick the SF field for a given logical role.

    Priority:
      1. Exact canonical name present → confidence 1.0.
      2. Field whose api_name/label contains one of `fuzzy_contains` AND
         matches `type_preference` → confidence 0.7.
      3. Nothing → confidence 0.0 (caller leaves the default).
    """
    if canonical_api in api_names:
        return MappingSuggestion(
            field_name, canonical_api, 1.0,
            f"Standard Salesforce field `{canonical_api}` found.",
        )

    # Fuzzy fallback: first field whose type matches AND whose name/label
    # contains any of the fuzzy tokens.
    if fuzzy_contains:
        for api, info in by_name.items():
            ftype = (info.get("type") or "").lower()
            name_lc = api.lower()
            label_lc = (info.get("label") or "").lower()
            if type_preference and ftype not in type_preference:
                continue
            if any(tok in name_lc or tok in label_lc for tok in fuzzy_contains):
                return MappingSuggestion(
                    field_name, api, 0.7,
                    f"No `{canonical_api}`; best fuzzy match by "
                    f"type={ftype} and name contains one of {list(fuzzy_contains)}.",
                )

    return MappingSuggestion(
        field_name, canonical_api, 0.0,
        f"No `{canonical_api}` in schema; defaulting — admin must confirm.",
    )
