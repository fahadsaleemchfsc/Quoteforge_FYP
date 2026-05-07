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

**Reading the metrics:** Accuracy looks higher on the real-org model than the synthetic one, but that's class-imbalance illusion — a model that always predicts "lost" would score 0.789 on the real-org data just from the base rate. The signal is in the **AUC of 0.82 and recall of 0.70** — the model is catching ~70% of actual wins despite being trained on data where wins are the minority class. The lower precision (0.47) is a deliberate trade: in B2B sales, missing a winnable deal costs more than reviewing a marginal one, so the model is tuned to favor recall.

### v2 (in progress)

Two issues found during v1 review are being addressed for v2:

1. **Row cap removed.** v1 trained on the first 5,000 closed Opps due to a hardcoded `LIMIT 5000` in the training fetcher. v2 removes the cap; the live customer org has ~17,378 closed Opps available, so v2 trains on ~3.5× the data.
2. **Activity enrichment for training.** v1's training fetcher didn't populate `_contact_activities` / `_account_activities`, so three engagement-derived features (`activity_count`, `contact_activity_count`, `account_activity_count_365d`) were zero-variance during training and contributed no learned signal. v2 adds bulk-chunked SOQL queries (~5 calls per chunk of 500 Opps) to populate these features at training time, matching the prediction-time feature distribution.

Expected v2 lift: AUC into the **0.83–0.87** range, with recall improvement from the activity features.

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
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in SF_CLIENT_ID, SF_CLIENT_SECRET, etc.
uvicorn app.main:app --reload --port 8000

# Admin portal (separate terminal)
cd ../admin
npm install
npm run dev   # runs on :3000

# Salesforce LWC deployment
cd ../salesforce
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
│   │   ├── app/
│   │   │   ├── api/                    ← FastAPI routers
│   │   │   ├── services/
│   │   │   │   ├── salesforce_connector.py
│   │   │   │   └── insights/
│   │   │   │       ├── salesforce_fetch.py     ← SF data fetcher (training + predict)
│   │   │   │       ├── features.py             ← 41-feature engineer
│   │   │   │       ├── trainer.py              ← LightGBM training pipeline
│   │   │   │       ├── predictor.py            ← prediction + bootstrap CI
│   │   │   │       └── training_log.py
│   │   │   └── main.py
│   │   ├── storage/insights_models/    ← per-tenant .pkl files (gitignored)
│   │   └── quoteforge.db               ← SQLite (gitignored)
│   ├── admin/                          ← React admin portal
│   └── salesforce/                     ← LWC + Apex
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
| ✅ | v1 model on real customer data (AUC 0.818) |
| 🔄 | v2: full dataset + activity feature enrichment |
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
