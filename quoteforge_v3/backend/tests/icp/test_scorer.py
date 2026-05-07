"""Phase 3 — ICP scorer unit tests.

Pure-data, no DB, no network. Exercises hard filters, soft signals,
weight variations, and edge cases (empty ICP, missing fields, etc.).
"""
from __future__ import annotations

from app.services.icp.scorer import (
    ICPDefinition,
    score_opportunity_against_icp,
)


def _strong_tech_icp(**overrides) -> ICPDefinition:
    base = dict(
        id="icp-1", tenant_id="t1", name="Enterprise Tech",
        included_industries=["Technology", "Finance"],
        required_lead_sources=["Referral", "Partner"],
        min_amount=50_000.0,
        weight_industry_match=1.0,
        weight_region_match=0.8,
        weight_amount_fit=1.0,
        weight_engagement=1.2,
        weight_lead_source=0.7,
    )
    base.update(overrides)
    return ICPDefinition(**base)


def _healthy_opp(**overrides) -> dict:
    o = {
        "Amount": 120_000,
        "Account": {"Industry": "Technology", "BillingCountry": "United States"},
        "SalesRegion": "NA",
        "LeadSource": "Referral",
        "_contact_activities": [{}] * 5,
        "_account_activities": [{}] * 11,
    }
    o.update(overrides)
    return o


# ── Hard filters ────────────────────────────────────────────────

def test_industry_not_in_include_list_zeros_the_score():
    icp = _strong_tech_icp()
    opp = _healthy_opp(Account={"Industry": "Government"})
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0
    statuses = {x["factor"]: x["status"] for x in r.match_reasons}
    assert statuses["industry"] == "mismatch"


def test_amount_below_min_zeros_the_score():
    icp = _strong_tech_icp(min_amount=100_000)
    opp = _healthy_opp(Amount=50_000)
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0


def test_amount_above_max_zeros_the_score():
    icp = _strong_tech_icp(max_amount=200_000)
    opp = _healthy_opp(Amount=500_000)
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0


def test_region_filter_zeros_when_mismatched():
    icp = _strong_tech_icp(included_regions=["NA", "EMEA"])
    opp = _healthy_opp(SalesRegion="LATAM")
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0


def test_employee_count_hard_filter():
    icp = _strong_tech_icp(min_employee_count=100, max_employee_count=10000)
    opp = _healthy_opp(NumberOfEmployees=50)
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0


def test_empty_included_industries_allows_all():
    """No hard filter on industry = every industry passes."""
    icp = _strong_tech_icp(included_industries=[])
    opp = _healthy_opp(Account={"Industry": "Government"})
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score > 0  # not hard-filtered out


# ── Soft signals ────────────────────────────────────────────────

def test_perfect_match_yields_1_0():
    icp = _strong_tech_icp()
    opp = _healthy_opp()   # 16 activities = engagement score 1.0 (capped)
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 1.0
    # Match reasons should include industry + engagement + lead_source as matches.
    matches = [x for x in r.match_reasons if x["status"] == "match"]
    assert len(matches) >= 3


def test_partial_match_when_lead_source_is_off_list():
    icp = _strong_tech_icp()
    opp = _healthy_opp(LeadSource="Web")   # not in Referral/Partner
    r = score_opportunity_against_icp(opp, icp)
    assert 0 < r.match_score < 1
    ls = [x for x in r.match_reasons if x["factor"] == "lead_source"]
    assert ls and ls[0]["status"] == "partial"


def test_engagement_below_threshold_zeros_score():
    icp = _strong_tech_icp(min_engagement_score=0.8)
    opp = _healthy_opp(_contact_activities=[], _account_activities=[])
    r = score_opportunity_against_icp(opp, icp)
    assert r.match_score == 0.0


def test_zero_weights_do_not_participate_in_average():
    """If the admin zeros out engagement weight, that factor shouldn't
    affect the score even if engagement is low."""
    icp = _strong_tech_icp(weight_engagement=0.0)
    opp_low_eng = _healthy_opp(_contact_activities=[], _account_activities=[])
    r = score_opportunity_against_icp(opp_low_eng, icp)
    # Industry + amount + lead_source still perfect → score should stay high
    assert r.match_score >= 0.9


# ── Edge cases ──────────────────────────────────────────────────

def test_completely_empty_icp_scores_zero():
    """Empty ICP (no hard filters, no signals) has total_weight=0 → 0."""
    icp = ICPDefinition(
        id="e", tenant_id="t", name="empty",
        weight_industry_match=0, weight_region_match=0,
        weight_amount_fit=0, weight_engagement=0, weight_lead_source=0,
    )
    r = score_opportunity_against_icp(_healthy_opp(), icp)
    assert r.match_score == 0.0


def test_missing_fields_do_not_crash_scorer():
    icp = _strong_tech_icp()
    # Opp missing Account entirely
    opp = {"Amount": 100_000, "LeadSource": "Referral"}
    r = score_opportunity_against_icp(opp, icp)
    # Industry is required → should hard-filter to 0 with a mismatch reason.
    assert r.match_score == 0.0


def test_match_reasons_are_human_readable():
    icp = _strong_tech_icp()
    r = score_opportunity_against_icp(_healthy_opp(), icp)
    for reason in r.match_reasons:
        assert "factor" in reason
        assert "status" in reason
        assert "detail" in reason
        # Detail should be a proper sentence, not a raw enum value
        assert len(reason["detail"]) > 10


def test_weight_changes_shift_score_predictably():
    """Upweighting engagement should increase score for high-engagement opp."""
    opp = _healthy_opp(LeadSource="Web")  # lead_source mismatch
    low_eng_weight = _strong_tech_icp(weight_engagement=0.5)
    high_eng_weight = _strong_tech_icp(weight_engagement=2.0)
    r_low = score_opportunity_against_icp(opp, low_eng_weight)
    r_high = score_opportunity_against_icp(opp, high_eng_weight)
    assert r_high.match_score > r_low.match_score
