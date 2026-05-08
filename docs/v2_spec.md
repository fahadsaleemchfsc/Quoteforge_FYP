# v2 Spec — Contact Field Features for Training

**Status:** Spec only — not implemented in v1. Planned post-defense.

**Scope:** This document covers Option A from the May 2026 ICP/contact-mapping conversation. Option B (deterministic ICP rules using Contact.Title / Contact.Department / contact-count) shipped in commit accompanying this spec; that path is *runtime* only and does not affect the trained LightGBM model.

This spec describes the *training-side* work to elevate Contact data from "ICP filter" to "model feature" — turning Contact.Title, Contact.Department, and account-level contact density into signals the model itself learns from rather than rules an admin hand-codes.

---

## 1. Motivation

The v1 model is trained on 41 features, none of them derived from Contact field values. The only contact-adjacent features are activity counts (`contact_activity_count`, `contact_days_since_last_activity`) — and even those were zero-variance during v1 training because the training fetcher didn't populate `_contact_activities`.

In B2B sales, the *identity* of who's responding to outreach is one of the strongest predictors of win/loss:

- A VP-level Contact engaged in a deal closes at notably different rates than an analyst-level Contact.
- Department alignment matters (Procurement Contacts close differently from Engineering Contacts on the same product).
- Multi-stakeholder coverage (more than one Contact actively engaged) correlates with deal complexity and is a known win-rate signal in the literature (Challenger Sale, MEDDIC, etc.).

v1 misses all of this. v2 surfaces it.

## 2. Features to Add

Six new features. Stable across customer orgs because they're derived, not raw.

| Feature | Type | Source | Example values | Rationale |
|---|---|---|---|---|
| `primary_contact_level` | categorical | `Contact.Title` → bucketed via `LEVEL_PATTERNS` map | `IC`, `Manager`, `Director`, `VP`, `C-level`, `Unknown` | Seniority of the buyer-side champion |
| `primary_contact_function` | categorical | `Contact.Department` → bucketed | `Sales`, `Engineering`, `Procurement`, `Finance`, `Operations`, `Other`, `Unknown` | Function alignment with what we're selling |
| `contact_email_domain_matches_account` | boolean | `Contact.Email` domain vs `Account.Website` domain | `True` / `False` | "Real buyer" signal — Contact's email matching the Account's domain rules out personal-email gatekeepers, freelancers, etc. |
| `n_contacts_on_opp` | integer | `COUNT(OpportunityContactRole) WHERE OpportunityId=…` | `1`, `2`, `3+` | Multi-stakeholder coverage. Capped at 5 in feature engineering to avoid outlier blowups. |
| `n_contacts_on_account` | integer | `COUNT(Contact) WHERE AccountId=…` (already exists at predict time as `_contact_count_on_account`) | `0`, `1–4`, `5+` | Account density |
| `primary_contact_age_days` | integer | `today − Contact.CreatedDate` | `45`, `380`, … | New-relationship vs long-standing-relationship signal |

### Bucketing maps (admin-tunable post-implementation, but ship with sensible defaults)

```python
LEVEL_PATTERNS = {
    "C-level": ["chief ", "ceo", "cfo", "cto", "coo", "cmo", "cio", "cso"],
    "VP":      ["vp ", "vice president"],
    "Director": ["director"],
    "Manager":  ["manager"],
    "IC":       ["analyst", "engineer", "specialist", "associate", "consultant",
                 "coordinator", "representative"],
}
# Anything not matched → "Unknown"

DEPARTMENT_PATTERNS = {
    "Sales":       ["sales", "revenue", "biz dev", "business development"],
    "Engineering": ["engineering", "engineer", "technology", "platform", "infra"],
    "Procurement": ["procurement", "purchasing", "vendor"],
    "Finance":     ["finance", "treasury", "accounting"],
    "Operations":  ["operations", "ops"],
    "Marketing":   ["marketing", "growth"],
    "HR":          ["hr", "human resources", "people"],
}
# Anything not matched → "Other" (never null — null collapses to a separate "Unknown" cat)
```

`LEVEL_PATTERNS` and `DEPARTMENT_PATTERNS` ship as module-level constants. Customer-specific overrides (e.g. an org that titles Directors as "Lead") go in a per-tenant `tenant_configs.contact_pattern_overrides_json` field — same approach the existing `field_mappings` uses. Out of scope for the first v2 cut.

## 3. SOQL Pattern (training-time fetch)

The current training fetcher (`salesforce_fetch.fetch_closed_opportunities`) issues one SOQL: `SELECT … FROM Opportunity WHERE IsClosed=TRUE … LIMIT N`. v2 adds a chunked enrichment pass.

**Per chunk of 500 closed Opps:**

```sql
-- Step 1 — primary Contact ID for each Opp (1 query)
SELECT OpportunityId, ContactId
FROM   OpportunityContactRole
WHERE  IsPrimary = TRUE
   AND OpportunityId IN ('006...', '006...', ... 500 IDs)

-- Step 2 — per-Opp contact count (1 query, GROUP BY)
SELECT OpportunityId, COUNT(Id) cnt
FROM   OpportunityContactRole
WHERE  OpportunityId IN (… 500 IDs)
GROUP BY OpportunityId

-- Step 3 — Contact details for the primary Contact IDs gathered in step 1
SELECT Id, Title, Department, Email, CreatedDate, AccountId
FROM   Contact
WHERE  Id IN (… ≤500 contact IDs)

-- Step 4 — Account-level Contact density (1 query, GROUP BY)
SELECT AccountId, COUNT(Id) cnt
FROM   Contact
WHERE  AccountId IN (… distinct account IDs)
GROUP BY AccountId

-- Step 5 — Account.Website for the email-domain match
SELECT Id, Website
FROM   Account
WHERE  Id IN (… distinct account IDs)
```

5 queries per chunk × ⌈n_opps / 500⌉ chunks. For DMI's full dataset (15,686 closed Opps): ~32 chunks × 5 = 160 SOQLs. At ~1s/round-trip on the UAT sandbox, that's 2–3 min added to v1's existing training time of ~1 min — acceptable.

`OpportunityContactRole.GROUP BY` returns aggregate results SF supports natively; no in-process counting needed.

The `_load_real_data_override` path bakes these results into the `.pkl` payload under new keys `_primary_contact_*` and `n_contacts_*`, mirroring how `_contact_activities` already works. The pkl format version bumps to `v2`.

## 4. Feature Engineering Changes

`features.py` gets ~80 new lines. All localized to `build_feature_frame`:

```python
# After existing engagement-feature block:

primary_contact_title  = opp.get("_primary_contact_title") or ""
primary_contact_dept   = opp.get("_primary_contact_department") or ""
primary_contact_email  = opp.get("_primary_contact_email") or ""
account_website        = _get_nested(opp, "Account.Website") or ""
contact_created_dt     = _parse_date(opp.get("_primary_contact_created_date"))
n_contacts_on_opp      = int(opp.get("_n_contacts_on_opp") or 0)

primary_contact_level     = _bucket_title(primary_contact_title)
primary_contact_function  = _bucket_department(primary_contact_dept)
domain_match              = _email_domain_matches_website(primary_contact_email, account_website)
contact_age_days          = (today - contact_created_dt).days if contact_created_dt else 0

row.update({
    "primary_contact_level":     primary_contact_level,        # categorical → one-hot
    "primary_contact_function":  primary_contact_function,     # categorical → one-hot
    "contact_email_domain_matches_account": int(domain_match),
    "n_contacts_on_opp":         min(5, n_contacts_on_opp),
    "n_contacts_on_account":     min(20, contact_count_on_account),  # cap
    "primary_contact_age_days":  contact_age_days,
})
```

`CATEGORICAL_BASE_COLS` extends to include `primary_contact_level` and `primary_contact_function` so `one_hot_and_align` produces stable column names.

**Feature count:** v1 has 41 features. After categorical one-hot expansion (6 levels for level + 8 for function = ~14 new columns), v2 has ~55 features. LightGBM handles this comfortably.

## 5. Retrain Plan

| Step | Detail |
|---|---|
| 1 | Re-export `real_dataset_v2.pkl` with the 6 new fields (uses the SOQL queries in §3 against the customer org). Bump the pkl `metadata.format_version` to `2`. |
| 2 | Add v2 columns to `CATEGORICAL_BASE_COLS` and `build_feature_frame` (§4). |
| 3 | `python -m training.train_real --tenant client-sandbox --data-version v2` — produces a new `v2.pkl` model file alongside the existing `v1.pkl`. |
| 4 | Hold v1 active until v2 is sanity-checked against a holdout. Activate v2 via `POST /api/insights/models/{id}/activate` once metrics check out. |
| 5 | Predict-time: no code change required (the predictor reads whichever model is `is_active=True`); the existing predict-time enrichment already populates `_primary_contact_title` and `_primary_contact_department` for the ICP scorer, just need to add `_primary_contact_email`, `_primary_contact_created_date`, `_n_contacts_on_opp`, and `Account.Website` to the same enrichment path. |

### Expected metric movement

| Metric | v1 (5,000 sampled) | v2 expected (15,686 full + Contact features) |
|---|---:|---:|
| AUC | 0.818 | **0.84–0.88** |
| Recall (won-class) | 0.697 | **0.74–0.80** |
| Precision (won-class) | 0.473 | 0.48–0.55 (mild improvement, not the focus) |
| Bimodal output distribution | Yes (19/20 in <20%) | Should soften — Contact-level features give the model more axes to score on |

The recall improvement is where most of the practical value lands — the model becomes less inclined to write off old open Opps as automatically lost just because `age_days` is large, because Contact engagement and seniority give it counter-evidence to weigh.

## 6. Risks

### 6.1 Feature explosion across customers

Different orgs use Title differently. DMI's "agent" Contacts don't fit cleanly into IC/Manager/Director — they're all sole-practitioner-style. The pattern map needs per-tenant override capability or it'll bucket everything as "Unknown" for some orgs and the new feature contributes no signal.

Mitigation: ship the override mechanism (`tenant_configs.contact_pattern_overrides_json`) as part of v2, not a follow-up. The first time a customer onboards, the wizard can preview "Here are the top 20 Contact.Title strings in your org — assign each to a level" and persist the override.

### 6.2 Email-domain match needs Account.Website populated

About 40% of SF orgs have spotty Website data on Account. If `Account.Website` is empty, `domain_match` defaults to False, which the model would learn to associate with low-quality deals — but on those orgs *every* deal has False, so the feature contributes no within-org signal and just adds noise.

Mitigation: training-time data-quality check. If <30% of Accounts in the training set have a `Website`, log a warning and *skip* the feature for that tenant. The trainer writes the active feature list into the pkl so predict-time aligns.

### 6.3 Schema variance — Contact.Department isn't always populated

Many SF customer orgs don't use Contact.Department at all (especially smaller orgs running default SF without Contact data hygiene programs). Same null-rate problem as 6.2.

Mitigation: same data-quality gate. The training-time fetcher reports per-feature null rates; features with >70% nulls in training are dropped from the active feature set for that tenant.

### 6.4 Feature leakage from `primary_contact_age_days`

If a Contact is created concurrent with the Opp (common when reps create the deal), `primary_contact_age_days` ≈ `age_days` and the two features become collinear. LightGBM is robust to collinearity but the SHAP attribution muddies — the LWC's "top drivers" panel could end up showing both age features simultaneously, confusing reps.

Mitigation: feature-engineering layer subtracts `min(contact_age_days, age_days)` so the feature represents *how much longer* the relationship pre-existed the deal. Becomes "0" for new contacts, large for established relationships.

### 6.5 Training time

Adding 5 SOQL/chunk × 32 chunks ≈ 160 sequential queries adds 2–3 min to training. For a defense demo path that already takes 1 min, this is 4× slower in absolute terms but still well under the impatience threshold. If it ever becomes a problem, the chunks can be parallelized with `asyncio.gather` (SF allows concurrent queries on a session up to ~25).

## 7. Out of Scope (Defer to v3)

- Activity-derived contact features beyond count + recency: e.g. activity-type histogram per Contact, response-rate-to-outreach. These need joining outbound rep activity to inbound responses, which the SF activity model captures inconsistently across orgs.
- Lead-source quality scoring (Contact.LeadSource × historical close rate per tenant). Useful but requires per-tenant lookup table, not pure feature engineering.
- Account firmographics from third-party enrichment (Clearbit, ZoomInfo). Out of scope for v2 — that's a different procurement decision.

## 8. Acceptance Criteria

v2 ships when:

1. `real_dataset_v2.pkl` (new format) regenerates successfully against the partner UAT and has all 6 new fields populated for ≥80% of rows.
2. `train_real --tenant client-sandbox --data-version v2` produces a `v2.pkl` artifact and writes a row to `deal_insight_models` with version=2.
3. Hold-out AUC ≥ 0.84.
4. Predicting on the demo Opps (`KqcSHIAZ`, `KpfGvIAJ`, `KpKvdIAF`) returns: (a) non-null `top_drivers` that include at least one of the 6 new feature names, and (b) a smoother win-prob distribution across a 20-Opp sample (the "moderate confidence" 20–60% bucket has at least 3 entries).
5. The LWC's `top_drivers` panel renders the new feature names without UI changes (they're just additional rows in the existing list).

---

*Spec author: Fahad Saleem  ·  Drafted as part of the May 2026 ICP/contact-mapping work session.  ·  Pairs with v1 commit that ships Option B (deterministic ICP contact-level rules).*
