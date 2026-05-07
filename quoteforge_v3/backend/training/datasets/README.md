# Deal Insights — Training Dataset

- **Source:** `enriched_synthetic`
- **Source URL:** file://training/import_real_dataset.py#generate_enriched_synthetic
- **Imported:** 2026-04-24T13:33:51.472318+00:00
- **Rows (mapped):** 5000
- **Class balance:** won=2457 · lost=2543
- **Seed:** `2026` (deterministic)
- **Weak-signal features baked in:** `Basic`, `Standard`, `Enterprise`, `NA`, `EMEA`, `APAC`, `LATAM`, `Q1`, `Q2`, `Q3`, `Q4`
- **Missing-rate targets:** `Amount`=0.1, `LeadSource`=0.09, `OwnerId`=0.08, `Account.Industry`=0.11
- **Amount outlier rate:** 0.02

## Imputation report

```json
{
  "median_amount": 29257.62,
  "mode_lead_source": "Referral",
  "mode_owner_id": "005008",
  "mode_industry": "Technology",
  "imputed_counts": {
    "Amount": 520,
    "LeadSource": 440,
    "OwnerId": 369,
    "Industry": 582
  }
}
```

## How to swap this dataset

Re-run `python -m training.import_real_dataset` — the importer will
try Hugging Face, then a local CSV at `training/datasets/source.csv`,
then the enriched synthetic floor. Whichever lands wins.
