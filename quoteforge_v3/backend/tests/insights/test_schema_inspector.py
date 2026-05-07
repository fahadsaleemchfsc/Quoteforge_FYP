"""Unit tests for the schema inspector + auto-mapping rules. Pure-data — no
SF I/O, no DB — so this file runs in milliseconds.

Run:
    cd backend && ./venv/bin/pytest tests/insights/test_schema_inspector.py -v
"""
from __future__ import annotations

from app.services.insights.schema_inspector import (
    STOCK_OPPORTUNITY_FIELDS,
    _stock_schema,
    suggest_mapping,
)


def test_stock_schema_includes_canonical_fields():
    schema = _stock_schema()
    api_names = {f["api_name"] for f in schema["opportunity_fields"]}
    for required in ("Amount", "StageName", "CloseDate", "IsClosed", "IsWon"):
        assert required in api_names, f"stock schema missing {required}"


def test_suggest_mapping_on_canonical_schema_hits_all_defaults():
    schema = _stock_schema()
    draft = suggest_mapping(schema)
    assert draft.amount_field == "Amount"
    assert draft.stage_field == "StageName"
    assert draft.close_date_field == "CloseDate"
    assert draft.is_closed_field == "IsClosed"
    assert draft.is_won_field == "IsWon"
    assert draft.industry_field == "Account.Industry"


def test_suggest_mapping_records_confidence_1_for_canonical_fields():
    schema = _stock_schema()
    draft = suggest_mapping(schema)
    by_name = {s.field_name: s for s in draft.suggestions}
    assert by_name["amount_field"].confidence == 1.0
    assert by_name["stage_field"].confidence == 1.0
    assert by_name["is_won_field"].confidence == 1.0


def test_suggest_mapping_without_record_types_drops_record_type_field():
    schema = _stock_schema()
    schema["record_types"] = []  # no record types enabled
    draft = suggest_mapping(schema)
    assert draft.record_type_field is None
    by_name = {s.field_name: s for s in draft.suggestions}
    assert by_name["record_type_field"].confidence == 0.0


def test_suggest_mapping_without_industry_gracefully_degrades():
    schema = {
        "opportunity_fields": [
            {"api_name": "Amount", "label": "Amount", "type": "currency"},
            {"api_name": "StageName", "label": "Stage", "type": "picklist"},
            {"api_name": "CloseDate", "label": "Close", "type": "date"},
            {"api_name": "CreatedDate", "label": "Created", "type": "datetime"},
            {"api_name": "IsClosed", "label": "Closed", "type": "boolean"},
            {"api_name": "IsWon", "label": "Won", "type": "boolean"},
        ],
        "record_types": [],
        "custom_fields": [],
        "detected_activity_types": ["Task", "Event"],
        "opportunity_count": 0,
        "connected": True,
    }
    draft = suggest_mapping(schema)
    assert draft.industry_field is None
    assert draft.lead_source_field is None


def test_suggest_mapping_finds_fuzzy_amount_when_no_canonical():
    """If no `Amount` field exists, the matcher falls back to a currency-typed
    field whose name contains 'amount' / 'value' / 'revenue'."""
    schema = {
        "opportunity_fields": [
            {"api_name": "Deal_Value__c", "label": "Deal Value",
             "type": "currency"},
            {"api_name": "StageName", "label": "Stage", "type": "picklist"},
            {"api_name": "CloseDate", "label": "Close", "type": "date"},
            {"api_name": "CreatedDate", "label": "Created", "type": "datetime"},
            {"api_name": "IsClosed", "label": "Closed", "type": "boolean"},
            {"api_name": "IsWon", "label": "Won", "type": "boolean"},
        ],
        "record_types": [],
        "custom_fields": [],
        "detected_activity_types": ["Task"],
        "opportunity_count": 0,
        "connected": True,
    }
    draft = suggest_mapping(schema)
    assert draft.amount_field == "Deal_Value__c"
    by_name = {s.field_name: s for s in draft.suggestions}
    assert by_name["amount_field"].confidence == 0.7


def test_to_response_preserves_custom_fields_and_exclusions():
    schema = _stock_schema()
    draft = suggest_mapping(schema)
    draft.custom_fields = [
        {"sf_field": "Priority__c", "feature_name": "priority", "type": "categorical"}
    ]
    draft.excluded_record_types = ["012000000000ABC"]
    payload = draft.to_response()
    assert payload["custom_fields"][0]["feature_name"] == "priority"
    assert payload["excluded_record_types"] == ["012000000000ABC"]
    assert len(payload["suggestions"]) > 0
