# QuoteForge V3

**AI-powered, multi-tenant Salesforce revenue intelligence platform.**

QuoteForge V3 generates sales proposals from Salesforce Opportunity data and predicts deal outcomes using a per-tenant LightGBM model trained on each customer's own historical CRM data. Built as a Final Year Project at **Forman Christian College**, Lahore.

> **Author:** Fahad Saleem &nbsp;·&nbsp; **GitHub:** [@fahadsaleemchfsc](https://github.com/fahadsaleemchfsc)
> **Supervisor:** Sir Nazim Ashraf
> **Institution:** Forman Christian College (FCCU), Lahore

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Why It Matters](#why-it-matters)
3. [Architecture](#architecture)
4. [Tech Stack](#tech-stack)
5. [Key Features](#key-features)
6. [Model Performance](#model-performance)
7. [Multi-Tenant Isolation](#multi-tenant-isolation)
8. [Running Locally](#running-locally)
9. [Project Structure](#project-structure)
10. [Documentation](#documentation)
11. [Roadmap](#roadmap)

---

## What It Does

QuoteForge V3 is two things in one platform:

1. **A proposal generator** — pulls Opportunity, Account, and OpportunityLineItem data live from Salesforce and produces formatted sales proposals via a Lightning Web Component embedded in the Opportunity record page.
2. **A deal-outcome predictor** — for any open Opportunity, returns a `win_probability`, a confidence interval (computed from 20 bootstrap-resampled models), and the top feature-level drivers behind the prediction. The model is trained per-tenant on the customer's own closed-deal history, so predictions reflect that organization's actual sales patterns rather than a generic baseline.

Both surfaces live inside Salesforce. Sales reps don't switch tools — they open an Opportunity and see the proposal generator and the Deal Insights panel side by side.

## Why It Matters

Most CPQ tools generate documents and stop there. The interesting question — *will this deal actually close?* — is left to gut feel. QuoteForge V3 closes that loop by training a customer-specific model on the patterns inside their own org and surfacing the answer in the same record where the rep is already working.

Multi-tenancy is treated as a first-class architectural concern: each customer org gets isolated data, isolated model artifacts on disk, and isolated predictions. Cross-tenant leakage is structurally impossible, not just policy-prevented.

## Architecture

```
┌──────────────────────────────────┐
│     Salesforce Org (per tenant)  │
│  ┌────────────────────────────┐  │
│  │  Opportunity Record Page   │  │
│  │  ├─ Proposal Generator LWC │  │
│  │  └─ Deal Insights LWC      │  │
│  └─────────────┬──────────────┘  │
└────────────────┼─────────────────┘
                 │ OAuth + REST
                 ▼
┌──────────────────────────────────┐
│   FastAPI Backend (uvicorn)      │
│  ┌────────────────────────────┐  │
│  │  Auth / Tenant Resolver    │  │
│  ├────────────────────────────┤  │
│  │  Insights Service          │  │
│  │  ├─ Salesforce Fetcher     │  │
│  │  ├─ Feature Engineering    │  │
│  │  ├─ LightGBM Trainer       │  │
│  │  └─ Predictor              │  │
│  ├────────────────────────────┤  │
│  │  Proposal Generator        │  │
│  └────────────────────────────┘  │
└────────┬───────────────┬─────────┘
         │               │
         ▼               ▼
   SQLite DB     Per-tenant model
  (tenants,     storage on disk
   models,      (.pkl + bootstrap)
   metrics)
         ▲
         │
┌────────┴─────────────────────────┐
│   React Admin Portal (:3000)     │
│   Training wizard, metrics, logs │
└──────────────────────────────────┘
```

> 📌 *Detailed architecture diagram lives in `/docs/architecture.png` — embed once added.*

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, uvicorn, async httpx |
| Database | SQLite (multi-tenant via tenant UUID partitioning) |
| ML | LightGBM with `is_unbalance=True`, 20-model bootstrap ensemble for CI estimation |
| Salesforce Integration | Custom REST client over OAuth 2.0 (Connected App), with `nextRecordsUrl` pagination |
| Frontend (in-Salesforce) | Lightning Web Components (LWC) |
| Frontend (admin portal) | React |
| Dev Tools | VS Code, Salesforce CLI, Workbench |

## Key Features

### 🎯 Per-Tenant Deal Insights Model
Every customer org gets its own LightGBM classifier trained on their closed Opportunities. 41 features spanning deal economics (Amount, Stage progression), temporal signals (age, days-since-update), engagement signals (Task/Event volume on the primary Contact and Account), and account-level context (contact density on the Account).

### 🔒 Multi-Tenant Isolation
Tenant identity is resolved at every API boundary. Models are stored under `storage/insights_models/<tenant_uuid>/v<n>.pkl`. The default tenant and a live customer tenant (`client-sandbox`) coexist with zero cross-contamination — verified by training both with the same code path and confirming neither's predictions shifted.

### 📊 Confidence Intervals via Bootstrap Ensembling
On every prediction, the 20 bootstrap models each cast a probability vote. The spread becomes the confidence interval shown in the LWC, giving reps an honest read on prediction certainty rather than a single false-precise number.

### 📈 Class Imbalance Handling
Real B2B sales data is roughly 20% won / 80% lost. LightGBM's `is_unbalance=True` flag rebalances loss weighting at training time, trading raw accuracy (which is misleading on imbalanced data) for higher recall on the won-class — which is the metric that actually matters for sales teams.

### 🧙 Training Wizard
Admin UI (React, port 3000) walks through field-mapping, data-quality assessment, training, and activation. Live tail of the training log shows boost iterations and holdout metrics in real time.

## Model Performance

Trained against two distinct datasets to validate the pipeline under different conditions:

| Tenant | Version | Rows | Won / Lost | Class Balance | Accuracy | Precision | Recall | AUC |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| `default` (synthetic benchmark) | v12 | 5,000 | 2,457 / 2,543 | 49 / 51 | 0.717 | 0.736 | 0.660 | 0.802 |
| `client-sandbox` (real org) | v1 | 5,000 | 1,057 / 3,943 | 21 / 79 | 0.772 | 0.473 | 0.697 | **0.818** |

**Reading the metrics:** v1's training sample of 5,000 closed Opps was drawn from a customer org with 15,686 total closed Opportunities (verified via direct SOQL count) — the LIMIT 5000 cap meant only ~32% of the available labeled data was used. Class balance in the full org is 17/83 (2,710 won / 12,976 lost), even more skewed than the 21/79 sample seen at training time. Accuracy looks higher on the real-org model than the synthetic one, but that's class-imbalance illusion — a model that always predicts "lost" would score 0.789 on the real-org data just from the base rate. The signal is in the **AUC of 0.82 and recall of 0.70** — the model is catching ~70% of actual wins despite being trained on data where wins are the minority class. The lower precision (0.47) is a deliberate trade: in B2B sales, missing a winnable deal costs more than reviewing a marginal one, so the model is tuned to favor recall.

### v2 (in progress)

Two issues found during v1 review are being addressed for v2:

1. **Row cap removed.** v1 trained on the first 5,000 closed Opps due to a hardcoded `LIMIT 5000` in the training fetcher — about 32% of the 15,686 closed Opps available in the partner org. v2 removes the cap so the trainer uses the full closed-deal dataset (~3.1× more training rows) instead of a head-of-list slice.
2. **Activity enrichment for training.** v1's training fetcher didn't populate `_contact_activities` / `_account_activities`, so three engagement-derived features (`activity_count`, `contact_activity_count`, `account_activity_count_365d`) were zero-variance during training and contributed no learned signal. v2 adds bulk-chunked SOQL queries (~5 calls per chunk of 500 Opps) to populate these features at training time, matching the prediction-time feature distribution.

Expected v2 lift: AUC into the **0.83–0.87** range, with recall improvement from the activity features.

## Known Limitations / Data Quality

Honest documentation of what v1 does and does not handle well, observed during live testing against the partner UAT sandbox:

**Training data is the source of truth, not the live pipeline.** The v1 model was trained on 5,000 closed Opportunities sampled from the customer org. Those rows have realistic deal-cycle ages (created → closed within reasonable B2B timelines). The model learned, correctly, that deals which sit open for *much* longer than the cycle distribution it saw in training are unlikely to win.

**Stale open Opportunities cluster low.** The current open Opps in the partner UAT sandbox have CloseDates roughly a year past today's date — they are zombie sandbox records left behind after manual testing rather than active deals. When the LWC predicts on these, the model's `age_days` feature (today − CreatedDate) lands far above anything in the training distribution, so predictions cluster heavily in the 1–10% range. **This is the model behaving correctly:** it's flagging that these records do not look like the closed deals it learned from. It is *not* a sign that the LightGBM classifier is broken.

The visible consequence in the LWC: across the 20 most-recent Opps in the UAT sandbox, 19 land below 20% win probability and only 1 sits above 60%. The "moderate confidence" 20–60% band is sparsely populated. On a freshly-maintained production Opportunity pipeline (CloseDates within the next 30–90 days, active engagement), prediction distribution is expected to be smoother.

**v2 will surface this as a customer-facing signal.** The next iteration adds a data-hygiene report alongside each prediction — open-Opp staleness (days past CloseDate), missing-contact rate, no-recent-activity rate — so reps and admins can see whether a low prediction reflects deal weakness or pipeline staleness, and act accordingly.

**Other v1 caveats:**
- `age_days` is computed as `today − CreatedDate` (`features.py:203`). Five additional features fall back to `age_days` when their specific signal is missing (e.g. no stage-change date, no activities), so old open deals see a multiplied effect. v2 candidates: cap age at the training-set 95th percentile, or switch to age-at-current-stage.
- Each prediction triggers ~9 sequential SOQL round-trips against the customer org (1 main + 6 enrichment + 2 activity batches), so latency on a remote sandbox can reach 5–10 seconds. Batching enrichment queries via `asyncio.gather` and dropping the redundant ICP-refresh fetch on cache hits are easy wins for v2.
- The OAuth `reauth` flow has a known state-handling bug (see `notes/challenges.md`) where re-authenticating an existing connection creates a new connection row instead of updating in-place. Dev environments use the `scripts/provision_sf_connection.py` bootstrap as a workaround. Refresh tokens are not stored in this path, so dev connections need to be re-bootstrapped every 2–4 hours. Production fix is roadmapped.

## Multi-Tenant Isolation

The single highest-leverage architectural decision in the project. Every database table that holds tenant data has a `tenant_id` foreign key. Every API request resolves a tenant from the auth token before any query runs. Model files are filesystem-isolated:

```
backend/storage/insights_models/
├── 0130cb77-.../    ← default tenant
│   ├── v1.pkl ... v12.pkl
│   ├── bootstrap/
│   └── training_log.txt
└── 18b220b1-.../    ← client-sandbox tenant
    ├── v1.pkl
    ├── bootstrap/
    └── training_log.txt
```

A bug discovered mid-development was silently re-routing every authenticated user's predict request to the default tenant's model. This was fixed and verified by training both tenants on identical code and confirming each tenant's predictions only ever come from their own model artifacts.

## Running Locally

### Prerequisites
- Python 3.12+
- Node.js 18+ (for the React admin)
- A Salesforce Developer Edition or Sandbox org
- A Connected App configured for OAuth (client_id + client_secret)

### Setup

```bash
# Clone
git clone https://github.com/fahadsaleemchfsc/quoteforge-v3.git
cd quoteforge-v3

# Backend
cd quoteforge_v3/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in SALESFORCE_CLIENT_ID, ANTHROPIC_API_KEY, etc.
uvicorn main:app --reload --port 8000

# Admin portal (separate terminal — React app lives at quoteforge_v3/)
cd ../
npm install
npm run dev   # runs on :3000

# Salesforce LWC deployment
cd salesforce_package
sf project deploy start --target-org <your-org-alias>
```

### First-Time Tenant Setup

1. Log into the admin portal at `http://localhost:3000`
2. Connect a Salesforce org via the OAuth flow
3. Run the training wizard — it will fetch closed Opportunities, engineer features, train, and activate the model
4. Open any Opportunity in Salesforce — the Deal Insights LWC will render a live prediction

## Project Structure

```
final_year_project/
├── quoteforge_v3/            ← active project root
│   ├── backend/
│   │   ├── main.py                     ← FastAPI entrypoint (uvicorn main:app)
│   │   ├── app/
│   │   │   ├── routers/                ← FastAPI routers
│   │   │   ├── core/                   ← config, database, security
│   │   │   ├── models/                 ← SQLAlchemy models
│   │   │   ├── schemas/                ← Pydantic schemas
│   │   │   ├── services/
│   │   │   │   ├── salesforce_connector.py
│   │   │   │   └── insights/
│   │   │   │       ├── salesforce_fetch.py     ← SF data fetcher (training + predict)
│   │   │   │       ├── features.py             ← 41-feature engineer
│   │   │   │       ├── trainer.py              ← LightGBM training pipeline
│   │   │   │       ├── predictor.py            ← prediction + bootstrap CI
│   │   │   │       └── training_log.py
│   │   │   └── seed.py
│   │   ├── storage/insights_models/    ← per-tenant .pkl files (gitignored)
│   │   └── quoteforge.db               ← SQLite (gitignored)
│   ├── src/                            ← React admin portal (Vite, runs on :3000)
│   └── salesforce_package/             ← LWC + Apex (sf project deploy)
├── scripts/
│   └── deploy_metadata.sh              ← substitutes secret placeholders into SF metadata
├── docs/                               ← FYP deliverables
│   ├── proposal.docx
│   ├── srs.docx
│   └── progress_report.docx
└── README.md
```

## Documentation

- 📄 **FYP Proposal** — `docs/proposal.docx`
- 📄 **Software Requirements Specification (SRS)** — `docs/srs.docx`
- 📄 **Progress Report** — `docs/progress_report.docx`

## Roadmap

| Status | Item |
|---|---|
| ✅ | Multi-tenant data isolation |
| ✅ | Salesforce OAuth + REST integration with pagination |
| ✅ | LWC: proposal generator |
| ✅ | LWC: Deal Insights with confidence intervals |
| ✅ | Admin portal: training wizard |
| ✅ | v1 model on real customer data — AUC 0.818, recall 0.70, trained on 5,000 of 15,686 available closed Opps |
| 🔄 | v2: full dataset + activity feature enrichment |
| ✅ | LWC: proposal generator wired end-to-end (SF lookup → AI generation → Salesforce write-back) |
| ✅ | tenant-resolution fix across 4 quote-generation call sites |
| 🔄 | OAuth callback reauth state handling (replace dev bootstrap workaround) |
| 📋 | v3: time-aware activity windowing (avoid post-close leakage) |
| 📋 | Drift detection: alert when prediction distribution shifts |
| 📋 | Per-feature SHAP values surfaced in the LWC |

---

## Screenshots

> 📌 *Add screenshots here before defense:*
> - `/docs/screenshots/lwc_prediction.png` — Deal Insights LWC on a real Opp
> - `/docs/screenshots/training_wizard.png` — Admin training flow
> - `/docs/screenshots/architecture.png` — Architecture diagram

---

## Acknowledgments

Supervised by **Sir Nazim Ashraf**, Department of Computer Science, Forman Christian College.

Real-world testing data provided by a partner organization's Salesforce UAT environment, anonymized at the predict-time interface.

---

*Built as a Final Year Project, 2025–2026.*
