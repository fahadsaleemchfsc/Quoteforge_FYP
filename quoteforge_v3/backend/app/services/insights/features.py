"""
Feature engineering — the same pipeline runs at training and prediction time.

Consistency between train/predict is what makes the LightGBM prediction valid.
Both paths call `build_feature_frame` over raw Opportunity+Activity records
(dicts produced from SOQL), producing a pandas DataFrame whose columns must
match the trained model's feature_names.

Numeric features (v6):
  amount                      — the mapped currency field
  age_days                    — (today - created_date)
  activity_count              — count of related Task/Event rows on the Opp
  days_since_last_activity    — max(today - last activity date on the Opp)
  days_in_current_stage       — time in current stage; proxied by age_days
                                when stage change history isn't available
  activity_velocity           — activity_count / max(age_days, 1)
  expected_close_distance     — (close_date - today); negative = overdue
                                (Replaces v5's `days_to_close` — the name is
                                 clearer about the sign semantics; known
                                 limitation: training only sees closed deals
                                 where this is ≤ 0, so inference-time positive
                                 values sit out of the training distribution.
                                 Documented, not mitigated at this phase.)
  contact_activity_count              — activities on primary Contact
  contact_days_since_last_activity    — recency on primary Contact
  account_activity_count_365d         — activities on Account in past year
  account_engagement_diversity        — distinct activity types on Account
  days_since_account_last_activity    — recency at Account level
  contact_count_on_account            — Contacts engaged on the Account

Categorical features (one-hot at train time, aligned to training columns
at inference):
  industry, lead_source, record_type, owner_id
  product_tier, sales_region, quarter

Custom fields carry their declared type (numeric | categorical | boolean).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


# ── Numeric feature set (v6) ─────────────────────────────────────────
# `days_to_close` was removed in Phase 2 because of a training-vs-inference
# distribution mismatch: all training rows are closed deals with past
# close_date (value ≤ 0), but live inference fires on open deals where the
# value is almost always positive. `expected_close_distance` keeps the same
# computation but a clearer name — the mismatch is noted but not yet
# mitigated (Phase 2 scope prioritized adding signal over fixing this).
NUMERIC_BASE_COLS = [
    "amount",
    "age_days",
    "activity_count",
    "days_since_last_activity",
    "days_in_current_stage",
    "activity_velocity",
    "expected_close_distance",
    "contact_activity_count",
    "contact_days_since_last_activity",
    "account_activity_count_365d",
    "account_engagement_diversity",
    "days_since_account_last_activity",
    "contact_count_on_account",
]

CATEGORICAL_BASE_COLS = [
    "industry",
    "lead_source",
    "record_type",
    "owner_id",
    "product_tier",
    "sales_region",
    "quarter",
]


# Small country→sales-region mapping used for the sales_region derivation
# on live SF predictions (where Account.BillingCountry is the natural source).
# Training data already has SalesRegion set directly so this is live-only.
_COUNTRY_TO_REGION: dict[str, str] = {
    "united states": "NA", "usa": "NA", "us": "NA", "canada": "NA", "mexico": "NA",
    "germany": "EMEA", "france": "EMEA", "united kingdom": "EMEA", "uk": "EMEA",
    "spain": "EMEA", "italy": "EMEA", "netherlands": "EMEA", "ireland": "EMEA",
    "switzerland": "EMEA", "sweden": "EMEA", "poland": "EMEA",
    "japan": "APAC", "china": "APAC", "india": "APAC", "australia": "APAC",
    "singapore": "APAC", "south korea": "APAC", "pakistan": "APAC",
    "brazil": "LATAM", "argentina": "LATAM", "chile": "LATAM", "colombia": "LATAM",
}


def _country_to_region(country: str | None) -> str:
    if not country:
        return "UNKNOWN"
    return _COUNTRY_TO_REGION.get(str(country).strip().lower(), "UNKNOWN")


def _quarter_from_date(d: date | None) -> str:
    if d is None:
        return "UNKNOWN"
    return f"Q{(d.month - 1) // 3 + 1}"


@dataclass
class MappingBundle:
    """Plain shape of the DealInsightMapping row fed into feature engineering.

    Unpacking the SQLAlchemy row into a dataclass keeps the feature pipeline
    testable without a DB session.
    """
    amount_field: str
    stage_field: str
    close_date_field: str
    created_date_field: str
    is_closed_field: str
    is_won_field: str
    industry_field: str | None
    lead_source_field: str | None
    owner_field: str | None
    record_type_field: str | None
    custom_fields: list[dict[str, Any]]
    # Phase 2 — optional mappings for weak-signal fields. None = feature falls
    # back to derivation (e.g., sales_region from Account.BillingCountry) or
    # is marked UNKNOWN for the one-hot alignment.
    product_tier_field: str | None = None
    billing_country_field: str | None = "Account.BillingCountry"
    # Contact / Account activity containers (populated by the enriched fetch
    # path or the synthetic v2 dataset). Not used directly in the mapping
    # itself — but keeping the field here keeps the dataclass the single
    # source of truth for feature inputs.
    stage_change_date_field: str | None = None


def _get_nested(record: dict[str, Any], path: str) -> Any:
    """Pull `Account.Industry` from a SOQL result where `Account` is itself
    a nested dict under the parent record. Returns None if any segment is
    missing."""
    if not path:
        return None
    cur: Any = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        s = str(value)
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def build_feature_frame(
    opportunities: list[dict[str, Any]],
    activities_by_opp: dict[str, list[dict[str, Any]]],
    mapping: MappingBundle,
    *,
    reference_date: date | None = None,
) -> pd.DataFrame:
    """Turn raw Opp+Activity records into a pandas DataFrame ready for LightGBM.

    Args:
        opportunities: one dict per Opp — SOQL result shape.
        activities_by_opp: {opp_id: [Task/Event records]}.
        mapping: tenant's field mapping.
        reference_date: "today" — overridable for deterministic tests.
    """
    today = reference_date or _today()
    rows: list[dict[str, Any]] = []

    for opp in opportunities:
        opp_id = opp.get("Id") or opp.get("id") or ""

        amount = opp.get(mapping.amount_field)
        try:
            amount_f = float(amount) if amount is not None else 0.0
        except (TypeError, ValueError):
            amount_f = 0.0

        close_dt = _parse_date(opp.get(mapping.close_date_field))
        created_dt = _parse_date(opp.get(mapping.created_date_field))

        age_days = (today - created_dt).days if created_dt else 0
        # expected_close_distance: positive = future close, negative = past.
        # Intentionally *not* clamped — negative values are a real signal.
        expected_close_distance = (close_dt - today).days if close_dt else 0

        # Stage-change proxy: real SF integration would read the latest
        # OpportunityHistory row; for now we honor a mapped stage_change_date
        # field if the admin supplied one, else fall back to age_days.
        stage_change_dt = None
        if mapping.stage_change_date_field:
            stage_change_dt = _parse_date(opp.get(mapping.stage_change_date_field))
        days_in_current_stage = (
            (today - stage_change_dt).days if stage_change_dt else age_days
        )

        acts = activities_by_opp.get(opp_id, [])
        activity_count = len(acts)
        last_act: date | None = None
        for a in acts:
            d = _parse_date(a.get("ActivityDate") or a.get("CreatedDate"))
            if d and (last_act is None or d > last_act):
                last_act = d
        days_since_last_activity = (today - last_act).days if last_act else age_days

        activity_velocity = activity_count / max(age_days, 1)

        # ── Cross-object features (populated by enriched fetch path /
        # synthetic v2 dataset). Missing keys default to 0/UNKNOWN — the
        # model treats "no signal" as a legitimate input.
        contact_acts = opp.get("_contact_activities") or []
        account_acts = opp.get("_account_activities") or []
        contact_activity_count = len(contact_acts)
        account_activity_count_365d = len(account_acts)

        contact_last = None
        for a in contact_acts:
            d = _parse_date(a.get("ActivityDate") or a.get("CreatedDate"))
            if d and (contact_last is None or d > contact_last):
                contact_last = d
        contact_days_since_last_activity = (
            (today - contact_last).days if contact_last else age_days
        )

        account_last = None
        for a in account_acts:
            d = _parse_date(a.get("ActivityDate") or a.get("CreatedDate"))
            if d and (account_last is None or d > account_last):
                account_last = d
        days_since_account_last_activity = (
            (today - account_last).days if account_last else age_days
        )

        account_engagement_diversity = len({
            (a.get("Type") or a.get("ActivityType") or "Task")
            for a in account_acts
        }) if account_acts else 0
        contact_count_on_account = int(opp.get("_contact_count_on_account") or 0)

        row: dict[str, Any] = {
            "opp_id": opp_id,
            "amount": amount_f,
            "age_days": age_days,
            "activity_count": activity_count,
            "days_since_last_activity": days_since_last_activity,
            "days_in_current_stage": days_in_current_stage,
            "activity_velocity": activity_velocity,
            "expected_close_distance": expected_close_distance,
            "contact_activity_count": contact_activity_count,
            "contact_days_since_last_activity": contact_days_since_last_activity,
            "account_activity_count_365d": account_activity_count_365d,
            "account_engagement_diversity": account_engagement_diversity,
            "days_since_account_last_activity": days_since_account_last_activity,
            "contact_count_on_account": contact_count_on_account,
        }

        # Categoricals — null becomes "UNKNOWN" so one-hot encoding has a
        # stable column for missing values. str(None) would yield the literal
        # "None" which would silently create a bogus category.
        def _cat(raw: Any) -> str:
            return str(raw) if raw not in (None, "") else "UNKNOWN"

        row["industry"] = _cat(_get_nested(opp, mapping.industry_field)) \
            if mapping.industry_field else "UNKNOWN"
        row["lead_source"] = _cat(opp.get(mapping.lead_source_field)) \
            if mapping.lead_source_field else "UNKNOWN"
        row["record_type"] = _cat(opp.get(mapping.record_type_field)) \
            if mapping.record_type_field else "UNKNOWN"
        row["owner_id"] = _cat(opp.get(mapping.owner_field)) \
            if mapping.owner_field else "UNKNOWN"

        # Weak-signal categoricals.
        # product_tier: prefer mapped SF field, else the training-data key.
        if mapping.product_tier_field:
            row["product_tier"] = _cat(opp.get(mapping.product_tier_field))
        else:
            row["product_tier"] = _cat(opp.get("ProductTier"))
        # sales_region: prefer explicit training field, else derive from
        # Account.BillingCountry for live SF records.
        if opp.get("SalesRegion") is not None:
            row["sales_region"] = _cat(opp.get("SalesRegion"))
        else:
            country = _get_nested(opp, mapping.billing_country_field or "Account.BillingCountry")
            row["sales_region"] = _country_to_region(country)
        # quarter: prefer explicit training value, else derive from CloseDate.
        if opp.get("Quarter") is not None:
            row["quarter"] = _cat(opp.get("Quarter"))
        else:
            row["quarter"] = _quarter_from_date(close_dt)

        # Custom fields per mapping declaration.
        for cf in mapping.custom_fields:
            sf_field = cf.get("sf_field")
            name = cf.get("feature_name") or sf_field
            kind = cf.get("type", "categorical")
            if not sf_field or not name:
                continue
            raw = opp.get(sf_field)
            if kind == "numeric":
                try:
                    row[name] = float(raw) if raw is not None else 0.0
                except (TypeError, ValueError):
                    row[name] = 0.0
            elif kind == "boolean":
                row[name] = int(bool(raw))
            else:
                row[name] = str(raw) if raw is not None else "UNKNOWN"

        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["opp_id"] + NUMERIC_BASE_COLS + CATEGORICAL_BASE_COLS)
    return df


def one_hot_and_align(
    df: pd.DataFrame,
    *,
    categorical_cols: list[str],
    custom_categorical_cols: list[str],
    reference_columns: list[str] | None = None,
) -> pd.DataFrame:
    """One-hot encode categoricals. If `reference_columns` is provided, align
    the output to exactly that column list — adding zeros for missing columns
    and dropping unseen categories. This is what makes prediction-time feature
    vectors match training-time columns."""
    all_cat = [c for c in (categorical_cols + custom_categorical_cols) if c in df.columns]
    if all_cat:
        df_cat = pd.get_dummies(df[all_cat].astype(str), prefix=all_cat, prefix_sep="=")
    else:
        df_cat = pd.DataFrame(index=df.index)

    df_numeric = df.drop(columns=all_cat, errors="ignore")
    # Keep opp_id out of model features; feature_engineer returns it separately.
    df_numeric = df_numeric.drop(columns=["opp_id"], errors="ignore")

    out = pd.concat([df_numeric.reset_index(drop=True), df_cat.reset_index(drop=True)], axis=1)

    if reference_columns is not None:
        for col in reference_columns:
            if col not in out.columns:
                out[col] = 0
        extra = [c for c in out.columns if c not in reference_columns]
        if extra:
            out = out.drop(columns=extra)
        out = out[reference_columns]
    return out


def targets_from_records(
    opportunities: list[dict[str, Any]],
    mapping: MappingBundle,
) -> pd.Series:
    """Binary label: IsWon==True → 1 else 0."""
    labels = [1 if bool(opp.get(mapping.is_won_field)) else 0 for opp in opportunities]
    return pd.Series(labels, name="is_won")
