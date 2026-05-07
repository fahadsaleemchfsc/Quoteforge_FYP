"""
Phase 1 — real-data importer for Deal Insights training.

Priority chain (first success wins):
  1. Hugging Face CRM-sales dataset (anonymous download)
  2. Local CSV at training/datasets/source.csv (if the admin dropped one in)
  3. 5000-row enriched synthetic floor with:
     - 8-12% missing values across the critical columns
     - 3 weak-signal features (product_tier, sales_region, quarter)
     - Heavy-tailed amount distribution with deliberate outliers
     - Noisier outcome function so eval lands in the realistic 0.70-0.85 band

Output:
  training/datasets/real_dataset.pkl  — list[dict] in QuoteForge Opp shape
  training/datasets/README.md         — source URL, row count, class balance

The trainer consumes the pickle via the INSIGHTS_REAL_DATA_PATH environment
variable (see salesforce_fetch._load_real_data_override).

Run:
  cd backend && source venv/bin/activate
  python -m training.import_real_dataset
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


DATASETS_DIR = Path(__file__).parent / "datasets"
PICKLE_PATH = DATASETS_DIR / "real_dataset.pkl"
PICKLE_V2_PATH = DATASETS_DIR / "real_dataset_v2.pkl"
METADATA_PATH = DATASETS_DIR / "README.md"
LOCAL_CSV_PATH = DATASETS_DIR / "source.csv"


# URLs we'll try, in order. If any 200 with a parseable CSV, we use it.
# None of these are guaranteed to exist at any given moment — fall-through is
# designed in. The synthetic floor is reproducible and always wins if the
# network path fails.
HUGGINGFACE_CANDIDATES: list[tuple[str, str]] = [
    (
        "maven-crm-sales-pipeline",
        "https://huggingface.co/datasets/kyleo/crm-sales-opportunities/resolve/main/sales_pipeline.csv",
    ),
    (
        "b2b-sales-kaggle-mirror",
        "https://huggingface.co/datasets/alishanrahman/b2b-sales/resolve/main/sales.csv",
    ),
]


# ─── Source 1: HuggingFace ──────────────────────────────────────────

def try_huggingface() -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Attempt each HF URL. Return (opps, meta) on first success."""
    try:
        import httpx
    except ImportError:
        logger.info("httpx not available; skipping HF path")
        return None

    for name, url in HUGGINGFACE_CANDIDATES:
        try:
            logger.info(f"  trying HF: {name}")
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code != 200:
                    logger.info(f"    HTTP {r.status_code} — skip")
                    continue
                # Save to local CSV path for caching + downstream tools
                LOCAL_CSV_PATH.write_bytes(r.content)
                df = pd.read_csv(LOCAL_CSV_PATH)
        except Exception as e:
            logger.info(f"    fetch failed ({e}) — skip")
            continue

        opps = _map_generic_csv_to_opps(df)
        if len(opps) < 50:
            logger.info(f"    only {len(opps)} rows after mapping — skip")
            continue
        return opps, {
            "source": "huggingface",
            "source_name": name,
            "source_url": url,
            "raw_row_count": len(df),
            "mapped_row_count": len(opps),
        }
    return None


# ─── Source 2: local CSV ────────────────────────────────────────────

def try_local_csv() -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    if not LOCAL_CSV_PATH.exists():
        return None
    try:
        df = pd.read_csv(LOCAL_CSV_PATH)
    except Exception as e:
        logger.info(f"  local CSV failed to parse: {e}")
        return None
    opps = _map_generic_csv_to_opps(df)
    if len(opps) < 50:
        return None
    return opps, {
        "source": "local_csv",
        "source_url": f"file://{LOCAL_CSV_PATH}",
        "raw_row_count": len(df),
        "mapped_row_count": len(opps),
    }


# ─── Source 3: enriched synthetic floor ─────────────────────────────

INDUSTRIES = ["Technology", "Finance", "Healthcare", "Manufacturing",
              "Retail", "Education", "Government", "Energy", "Media"]
SOURCES = ["Web", "Partner", "Inbound Call", "Referral",
           "Trade Show", "Email Campaign", "Cold Outreach"]
OWNERS = [f"005{i:03d}" for i in range(1, 12)]
# Weak-signal features
PRODUCT_TIERS = ["Basic", "Standard", "Enterprise"]
SALES_REGIONS = ["NA", "EMEA", "APAC", "LATAM"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]


def _sigmoid(x: float) -> float:
    import math
    return 1.0 / (1.0 + math.exp(-x))


def generate_enriched_synthetic(
    n: int = 5000, seed: int = 2026,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """5000-row floor. Designed to land in the realistic 0.70–0.85 metric band
    after feature engineering + LightGBM training."""
    rnd = random.Random(seed)
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []

    for i in range(n):
        # Amount — heavy-tailed lognormal with deliberate 2% "whale" outliers.
        amount = max(500.0, rnd.lognormvariate(10.3, 1.5))
        if rnd.random() < 0.02:
            amount *= rnd.uniform(4, 18)

        age_days = rnd.randint(15, 730)
        created = today - timedelta(days=age_days)
        close = today - timedelta(days=rnd.randint(0, age_days - 1))

        industry = rnd.choice(INDUSTRIES)
        source = rnd.choice(SOURCES)
        owner = rnd.choice(OWNERS)
        product_tier = rnd.choice(PRODUCT_TIERS)
        sales_region = rnd.choice(SALES_REGIONS)
        quarter = rnd.choice(QUARTERS)

        # Latent signal — deliberately less deterministic than v4 synthetic.
        latent = 0.0
        latent += min(3.2, amount / 60_000.0)
        latent += 1.0 if industry == "Technology" else 0.0
        latent += 0.7 if industry == "Finance" else 0.0
        latent -= 0.8 if industry in {"Government", "Education"} else 0.0
        latent += 0.5 if source in {"Referral", "Partner"} else 0.0
        latent -= 0.5 if source == "Trade Show" else 0.0
        # Weak signals (small contributions — model has to find them).
        latent += 0.25 if product_tier == "Enterprise" else 0.0
        latent += 0.15 if sales_region == "NA" else 0.0
        latent += 0.10 if quarter == "Q4" else 0.0  # end-of-year push

        activity_count = max(0, int(rnd.gauss(1.5 + 2.0 * latent, 1.6)))

        # Outcome — wide noise (σ=0.5) so the job is to learn, not memorize.
        prob = _sigmoid(latent - 2.0 + 0.25 * activity_count + rnd.gauss(0, 0.5))
        is_won = rnd.random() < prob

        row: dict[str, Any] = {
            "Id": f"006ENR{seed:04d}{i:06d}",
            "Amount": amount,
            "StageName": "Closed Won" if is_won else "Closed Lost",
            "CloseDate": close.isoformat(),
            "CreatedDate": created.isoformat(),
            "IsClosed": True,
            "IsWon": is_won,
            "Account": {"Industry": industry},
            "LeadSource": source,
            "OwnerId": owner,
            "RecordTypeId": None,
            # Weak-signal features attached as custom-style fields. They won't
            # be picked up by the base feature frame unless the mapping's
            # custom_fields includes them, so they serve as "headroom" that
            # Phase 2 / ICP can later exploit.
            "ProductTier": product_tier,
            "SalesRegion": sales_region,
            "Quarter": quarter,
            "_activity_count_hint": activity_count,
        }

        # Missing values — 10% base rate, slightly varied per field so no
        # single column is catastrophically empty.
        if rnd.random() < 0.10:
            row["Amount"] = None
        if rnd.random() < 0.09:
            row["LeadSource"] = None
        if rnd.random() < 0.08:
            row["OwnerId"] = None
        if rnd.random() < 0.11 and row.get("Account"):
            row["Account"] = {}   # Industry becomes missing

        rows.append(row)

    meta = {
        "source": "enriched_synthetic",
        "source_url": "file://training/import_real_dataset.py#generate_enriched_synthetic",
        "raw_row_count": n,
        "mapped_row_count": n,
        "seed": seed,
        "weak_signal_features": PRODUCT_TIERS + SALES_REGIONS + QUARTERS,
        "missing_rate_targets": {"Amount": 0.10, "LeadSource": 0.09,
                                 "OwnerId": 0.08, "Account.Industry": 0.11},
        "outlier_rate": 0.02,
    }
    return rows, meta


# ─── Mapping helper for arbitrary CSVs ──────────────────────────────

def _map_generic_csv_to_opps(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Best-effort mapper: tries to find Amount/Stage/IsWon columns by common
    names. Rows that can't produce an outcome label are skipped."""
    amount_col = _first_match(df.columns, ["Amount", "amount", "deal_value",
                                           "close_value", "close_amount"])
    stage_col = _first_match(df.columns, ["StageName", "deal_stage", "stage",
                                          "Stage", "stage_name"])
    industry_col = _first_match(df.columns, ["Industry", "industry",
                                             "account_industry"])
    source_col = _first_match(df.columns, ["LeadSource", "lead_source",
                                           "source"])
    close_col = _first_match(df.columns, ["CloseDate", "close_date",
                                          "close_dt", "close"])
    create_col = _first_match(df.columns, ["CreatedDate", "create_date",
                                           "engage_date", "start_date"])

    if amount_col is None or stage_col is None:
        return []

    out: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()
    for i, row in df.iterrows():
        stage = str(row.get(stage_col) or "").strip().lower()
        if not stage:
            continue
        is_won = any(s in stage for s in ["won", "closed won", "closed-won"])
        is_lost = any(s in stage for s in ["lost", "closed lost", "closed-lost"])
        if not (is_won or is_lost):
            continue

        try:
            amount = float(row.get(amount_col))
        except (TypeError, ValueError):
            amount = None

        close_iso = _coerce_iso(row.get(close_col)) if close_col else None
        create_iso = _coerce_iso(row.get(create_col)) if create_col else None
        if not close_iso:
            close_iso = today.isoformat()
        if not create_iso:
            create_iso = (today - timedelta(days=90)).isoformat()

        out.append({
            "Id": f"006CSV{i:08d}",
            "Amount": amount,
            "StageName": "Closed Won" if is_won else "Closed Lost",
            "CloseDate": close_iso,
            "CreatedDate": create_iso,
            "IsClosed": True,
            "IsWon": bool(is_won),
            "Account": {
                "Industry": (str(row.get(industry_col)).strip()
                             if industry_col and pd.notna(row.get(industry_col))
                             else None),
            },
            "LeadSource": (str(row.get(source_col)).strip()
                           if source_col and pd.notna(row.get(source_col))
                           else None),
            "OwnerId": None,
            "RecordTypeId": None,
        })
    return out


def _first_match(cols, candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _coerce_iso(v: Any) -> str | None:
    if v is None or (hasattr(pd, "isna") and pd.isna(v)):
        return None
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        try:
            return datetime.strptime(s, "%m/%d/%Y").date().isoformat()
        except Exception:
            return None


# ─── Imputation ────────────────────────────────────────────────────

def impute_missing(opps: list[dict[str, Any]]) -> dict[str, Any]:
    """Median/mode imputation over the opportunities list. Mutates rows in
    place; returns a small report of what was imputed."""
    if not opps:
        return {}

    # Numeric: Amount
    amounts = [o["Amount"] for o in opps if o.get("Amount") is not None]
    median_amt = (sorted(amounts)[len(amounts) // 2]
                  if amounts else 0.0)

    # Categorical: LeadSource, Account.Industry, OwnerId
    from collections import Counter
    def _mode(seq):
        c = Counter(x for x in seq if x)
        return c.most_common(1)[0][0] if c else "Unknown"

    mode_source = _mode(o.get("LeadSource") for o in opps)
    mode_owner = _mode(o.get("OwnerId") for o in opps)
    mode_industry = _mode(
        (o.get("Account") or {}).get("Industry") for o in opps
    )

    report = {
        "median_amount": round(median_amt, 2),
        "mode_lead_source": mode_source,
        "mode_owner_id": mode_owner,
        "mode_industry": mode_industry,
        "imputed_counts": {"Amount": 0, "LeadSource": 0,
                           "OwnerId": 0, "Industry": 0},
    }

    for o in opps:
        if o.get("Amount") is None:
            o["Amount"] = median_amt
            report["imputed_counts"]["Amount"] += 1
        if not o.get("LeadSource"):
            o["LeadSource"] = mode_source
            report["imputed_counts"]["LeadSource"] += 1
        if not o.get("OwnerId"):
            o["OwnerId"] = mode_owner
            report["imputed_counts"]["OwnerId"] += 1
        acct = o.get("Account") or {}
        if not acct.get("Industry"):
            acct["Industry"] = mode_industry
            o["Account"] = acct
            report["imputed_counts"]["Industry"] += 1
    return report


# ─── Entry point ────────────────────────────────────────────────────

def load_real_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[1/3] Hugging Face…")
    res = try_huggingface()
    if res is not None:
        logger.info(f"   ✓ {res[1]['source_name']}")
        return res
    logger.info("[2/3] Local CSV…")
    res = try_local_csv()
    if res is not None:
        logger.info(f"   ✓ {LOCAL_CSV_PATH}")
        return res
    logger.info("[3/3] Enriched synthetic floor (5000 rows)…")
    return generate_enriched_synthetic(n=5000, seed=2026)


def _write_readme(meta: dict[str, Any], class_balance: dict[str, int]) -> None:
    lines = [
        "# Deal Insights — Training Dataset",
        "",
        f"- **Source:** `{meta['source']}`",
    ]
    if meta.get("source_name"):
        lines.append(f"- **Source name:** `{meta['source_name']}`")
    lines.extend([
        f"- **Source URL:** {meta.get('source_url', 'n/a')}",
        f"- **Imported:** {datetime.now(timezone.utc).isoformat()}",
        f"- **Rows (mapped):** {meta['mapped_row_count']}",
        f"- **Class balance:** won={class_balance.get('won', 0)} · "
        f"lost={class_balance.get('lost', 0)}",
    ])
    if "seed" in meta:
        lines.append(f"- **Seed:** `{meta['seed']}` (deterministic)")
    if "weak_signal_features" in meta:
        lines.append(
            "- **Weak-signal features baked in:** "
            + ", ".join(f"`{x}`" for x in meta["weak_signal_features"])
        )
    if "missing_rate_targets" in meta:
        lines.append(
            "- **Missing-rate targets:** "
            + ", ".join(f"`{k}`={v}" for k, v in meta["missing_rate_targets"].items())
        )
    if "outlier_rate" in meta:
        lines.append(f"- **Amount outlier rate:** {meta['outlier_rate']}")
    if "imputation" in meta:
        lines.extend([
            "",
            "## Imputation report",
            "",
            "```json",
            json.dumps(meta["imputation"], indent=2),
            "```",
        ])
    lines.extend([
        "",
        "## How to swap this dataset",
        "",
        "Re-run `python -m training.import_real_dataset` — the importer will",
        "try Hugging Face, then a local CSV at `training/datasets/source.csv`,",
        "then the enriched synthetic floor. Whichever lands wins.",
    ])
    METADATA_PATH.write_text("\n".join(lines) + "\n")


def enrich_with_cross_object_signals(
    opps: list[dict[str, Any]], seed: int = 2027,
) -> None:
    """Phase 2 — add synthetic Contact/Account activity signals per Opp.

    Each Opp gets three new inline containers:
      _contact_activities          — list of dicts with ActivityDate, Type
      _account_activities          — same shape, broader scope
      _contact_count_on_account    — how many Contacts are engaged

    Counts correlate with the same latent signal that drove the label, so
    the cross-object features carry REAL predictive value. We do NOT leak
    the outcome directly — the correlation is mediated by amount + industry
    + source just like the Opp-level activity_count hint.
    """
    rnd = random.Random(seed)
    today = datetime.now(timezone.utc).date()
    activity_types = ["Call", "Email", "Meeting", "Demo"]

    for o in opps:
        # Reconstruct a rough latent score so the counts correlate with
        # outcome-adjacent features (amount, industry, source), without
        # peeking at IsWon.
        amount = float(o.get("Amount") or 0)
        industry = (o.get("Account") or {}).get("Industry") or ""
        source = o.get("LeadSource") or ""
        latent = 0.0
        latent += min(3.0, amount / 60_000.0)
        if industry == "Technology": latent += 1.0
        elif industry == "Finance": latent += 0.7
        elif industry in {"Government", "Education"}: latent -= 0.7
        if source in {"Referral", "Partner"}: latent += 0.5
        elif source == "Trade Show": latent -= 0.4

        contact_count = max(0, int(rnd.gauss(1.0 + 1.5 * latent, 1.2)))
        account_count = max(0, int(rnd.gauss(3.0 + 3.0 * latent, 2.0)))

        # Activity spread — most recent within ~60 days, older ones up to a year.
        def _rand_activities(n: int) -> list[dict[str, Any]]:
            rows = []
            for _ in range(n):
                days_ago = int(abs(rnd.gauss(30, 60)))
                days_ago = min(days_ago, 365)
                rows.append({
                    "ActivityDate": (today - timedelta(days=days_ago)).isoformat(),
                    "Type": rnd.choice(activity_types),
                })
            return rows

        o["_contact_activities"] = _rand_activities(contact_count)
        o["_account_activities"] = _rand_activities(account_count)
        # Roughly 1-5 distinct Contacts engaged on the Account.
        o["_contact_count_on_account"] = max(
            1, min(8, int(rnd.gauss(2 + latent, 1.3)))
        )


def main() -> None:
    opps, meta = load_real_dataset()
    imputation = impute_missing(opps)
    if imputation:
        meta["imputation"] = imputation
    class_balance = {
        "won": sum(1 for o in opps if o.get("IsWon")),
        "lost": sum(1 for o in opps if not o.get("IsWon")),
    }

    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PICKLE_PATH, "wb") as f:
        pickle.dump({"opportunities": opps, "metadata": meta,
                     "class_balance": class_balance}, f)

    # Phase 2 — enriched v2 with cross-object activity signals. Kept alongside
    # v1 so metric regressions can be A/B-compared between the two pickles.
    import copy
    opps_v2 = copy.deepcopy(opps)
    enrich_with_cross_object_signals(opps_v2, seed=2027)
    meta_v2 = dict(meta)
    meta_v2["cross_object_enriched"] = True
    meta_v2["enrichment_seed"] = 2027
    with open(PICKLE_V2_PATH, "wb") as f:
        pickle.dump({"opportunities": opps_v2, "metadata": meta_v2,
                     "class_balance": class_balance}, f)

    _write_readme(meta_v2, class_balance)

    print()
    print(f"✓ saved {len(opps)} opportunities to {PICKLE_PATH}")
    print(f"✓ saved {len(opps_v2)} enriched opportunities to {PICKLE_V2_PATH}")
    print(f"  source    : {meta['source']}")
    print(f"  won / lost: {class_balance['won']} / {class_balance['lost']}")
    if imputation:
        print(f"  imputed   : {imputation['imputed_counts']}")

    # Quick sanity: avg contact + account activity counts
    avg_contact = sum(len(o.get("_contact_activities", [])) for o in opps_v2) / max(len(opps_v2), 1)
    avg_account = sum(len(o.get("_account_activities", [])) for o in opps_v2) / max(len(opps_v2), 1)
    print(f"  avg Contact activities/Opp : {avg_contact:.2f}")
    print(f"  avg Account activities/Opp : {avg_account:.2f}")
    print(f"  metadata  : {METADATA_PATH}")


if __name__ == "__main__":
    main()
