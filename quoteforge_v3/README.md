# QuoteForge — AI-Powered Quote & Proposal Generation Tool

> **Final Year Project** — Department of Computer Science, Forman Christian College University
>
> Team: Agha Zain Nadir · Faraz Ali · Fahad Saleem · Saad Khalid
> Advisor: Dr Nazim Ashraf | Co-Advisor: Faizad Ullah

---

## Overview

QuoteForge is a CRM-integrated automation system that generates professional, compliant, and brand-consistent sales quotes and proposals using AI (RAG + LLM). It integrates with Salesforce and HubSpot via OAuth 2.0, applies configurable pricing and compliance rules (SOC 2, GDPR, PPRA), and renders documents in PDF/DOCX formats.

## Tech Stack

| Layer       | Technology                          |
| ----------- | ----------------------------------- |
| Frontend    | React 18 + Vite + Tailwind CSS     |
| Backend     | FastAPI / Django REST Framework     |
| Database    | PostgreSQL                          |
| AI          | GPT-class LLM with RAG pipeline    |
| Documents   | ReportLab / python-docx             |
| Integration | Salesforce & HubSpot REST APIs      |
| Deployment  | Docker on AWS EC2                   |

## Project Structure

```
quoteforge/
├── public/                  # Static assets
├── src/
│   ├── assets/              # Images, fonts
│   ├── components/
│   │   ├── layout/          # Sidebar, TopBar
│   │   ├── ui/              # StatusBadge, MetricCard, etc.
│   │   └── charts/          # Chart wrapper components
│   ├── constants/           # Navigation config, mock data
│   ├── context/             # React context (Auth, Theme)
│   ├── hooks/               # Custom hooks (useApi, useDebounce)
│   ├── pages/               # Page-level components
│   │   ├── Dashboard.jsx
│   │   ├── Templates.jsx
│   │   ├── Pricing.jsx
│   │   ├── Prompts.jsx
│   │   ├── CRM.jsx
│   │   ├── Documents.jsx
│   │   ├── Users.jsx
│   │   └── Settings.jsx
│   ├── services/            # API client & service modules
│   ├── styles/              # Global CSS + Tailwind
│   ├── utils/               # Helper functions
│   ├── App.jsx              # Root component with routing
│   └── main.jsx             # Entry point
├── .env.example             # Environment template
├── index.html               # HTML shell
├── package.json
├── tailwind.config.js
├── vite.config.js
└── README.md
```

## Getting Started

### Prerequisites

- **Node.js** ≥ 18
- **npm** or **yarn**

### Installation

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd quoteforge

# 2. Install dependencies
npm install

# 3. Copy environment template
cp .env.example .env.local

# 4. Start development server
npm run dev
```

The app will open at **http://localhost:3000**.

### Build for Production

```bash
npm run build     # outputs to dist/
npm run preview   # preview the production build
```

## Modules

| Module             | Description                                           |
| ------------------ | ----------------------------------------------------- |
| **Dashboard**      | KPI metrics, trend charts, integration health, activity feed |
| **Templates**      | Upload, edit, preview quote/proposal templates         |
| **Pricing & Rules**| Discount tiers, tax rules, compliance clauses (SOC 2, GDPR, PPRA) |
| **AI Prompts**     | Manage prompt templates for each document section      |
| **CRM Integrations** | OAuth connections to Salesforce/HubSpot, field mapping |
| **Documents**      | Audit log of generated documents, delivery tracking    |
| **Users & Access** | Role-based access control (Admin, Manager, Rep)        |
| **Settings**       | Organization, AI, email, and security configuration    |

## Deal Insights (Module 6)

Per-tenant win-probability predictor on open Salesforce Opportunities.
Complements the quote-generation loop by telling sellers which deals
deserve attention and what's driving their odds up or down.

### What it is

- **Model:** LightGBM gradient-boosted trees, trained per tenant, stored as
  a pickle file on QuoteForge's own infrastructure. Predictions never leave
  the backend.
- **Explanation:** Claude Haiku generates a 2–3 sentence natural-language
  summary of each prediction's drivers. The prediction itself is
  deterministic and offline — Haiku is only called for the narrative text.
- **Why not an LLM for the prediction?** Tabular classification of small
  datasets (hundreds to thousands of closed Opps per tenant) is exactly
  what gradient-boosted trees are built for. GBMs outperform LLMs here,
  run locally with no API round-trips, and keep customer data on
  QuoteForge's infra — the same data-privacy boundary that defines the
  guardrail engine.

### Mapping wizard (/insights/setup)

1. **Scan** — QuoteForge inspects the Opportunity schema via SF describe
   and reports field counts, record types, Opportunity count.
2. **Map** — auto-suggests canonical fields (Amount, StageName, CloseDate,
   IsClosed, IsWon, Account.Industry, etc). Admin reviews, overrides any
   mapping, and optionally adds custom features from their own schema
   (numeric / categorical / boolean).
3. **Exclude** — uncheck record types to omit from training
   (e.g. internal / demo Opportunities).

Submit → `POST /api/insights/mapping`.

### Training + predictions

- Manual trigger: **Retrain now** button on the Models dashboard
  (`/insights/models`).
- Nightly retrain: APScheduler job runs at 02:00 UTC; retrains any tenant
  whose closed-Opportunity count has grown by ≥ 20 rows since the active
  model was trained. New version supersedes old, stale cached predictions
  are invalidated automatically.
- Minimum training data: 50 closed Opps with at least 10 wins and 10 losses.
  Below that, the trainer raises `InsufficientDataError` with an actionable
  message.

### Where predictions appear

- **Salesforce:** `quoteForgeDealInsights` LWC on the Opportunity record
  page. Shows color-coded win probability, Haiku explanation, and
  expandable top-3-positive / top-3-negative SHAP drivers.
- **Admin dashboard:** `/insights/models` — active model metrics, feature
  importance chart, training history table.

### API endpoints (all require admin auth)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET    | `/api/insights/schema`                 | Inspect SF Opportunity schema |
| GET    | `/api/insights/mapping`                | Current mapping (or auto-suggested draft) |
| POST   | `/api/insights/mapping`                | Save mapping from wizard |
| POST   | `/api/insights/train`                  | Trigger background training, returns job_id |
| GET    | `/api/insights/status`                 | Latest job + active model metrics |
| GET    | `/api/insights/models`                 | Version history, sorted newest-first |
| GET    | `/api/insights/predict/{opp_id}`       | Cached prediction with Haiku explanation |
| POST   | `/api/insights/predict/batch`          | Batch predict (demo-path, sequential) |
| GET    | `/api/insights/accuracy`               | Holdout metrics + calibration for the Model Accuracy tab |

### Data-quality tiers (Session 6.5)

QuoteForge refuses to train on fewer than **100 closed Opportunities** and
classifies each tenant's model into one of four tiers:

| Tier | Closed deals | UI behavior |
|---|---|---|
| insufficient | < 100 | Friendly refusal, no predictions rendered |
| early_stage  | 100–299 | Predictions + **confidence range** via 20× bootstrap-resample models |
| standard     | 300–999 | Predictions + per-tree-variance range |
| mature       | 1000+ | Predictions + per-tree-variance range (tightest) |

When the bootstrap range is wider than 15pp the LWC shows `75–90%` instead
of a point estimate — "limited training data — treat as a range" tooltip
explains why. Tight ranges render as a single percent.

### Customer-facing accuracy view

The new `/api/insights/accuracy` endpoint + `quoteForgeModelAccuracy` LWC
answer the buyer's first question — **"how do I know this model works
on my data?"** — by rendering:

- Holdout metrics (accuracy, precision, recall, AUC) on deals the model never saw
- **Accuracy by confidence bucket** — at 80%+ predictions, what's the actual
  win rate? Lets the rep see calibration directly, not trust ML vocabulary.
- Last 10 closed deals with predicted vs. actual outcome
- "Retrain recommended" callout when deals-since-last-training passes threshold

### Mapping-in-Salesforce

The `quoteForgeMappingConfig` LWC mirrors the QuoteForge admin three-step
setup wizard — schema scan → field mapping + custom features → record-type
exclusions — so admins can configure Deal Insights without leaving the CRM.
The existing React admin at `/insights/setup` still works; both hit the
same `/api/insights/{schema,mapping}` endpoints.

### Defense framing: how a customer with 300 deals verifies this

1. Open the QuoteForge app in App Launcher → **QuoteForge Accuracy** tab.
2. Top-line metrics: "72% accuracy on 1000 holdout deals the model never saw."
3. Accuracy-by-bucket table: "when the model says 80%+, it's right 92% of the
   time. When it says 40-60%, it's genuinely uncertain — treat those as
   'unclear, do the work.'"
4. Recent-deals check: last 10 closed Opps with predicted vs. actual,
   clickable to the record page for spot-checks.
5. Retrain button when 50+ new deals have closed.

### Demo-path disclaimers

The following are implemented as happy-path only, not production-hardened:

- **Nightly scheduled retraining worker** — no retry on failure,
  no cross-tenant lock, no model-quality rollback if a new version is worse.
- **Batch prediction endpoint** — sequential per-Opp iteration with
  per-item error catch. Production would parallelize + add rate limiting.

Phase 2 (post-defense): retry logic, concurrent training locks, model
versioning with rollback, audit logs of retraining triggers, active
learning / feedback loop, SHAP waterfall plots, CSV export of predictions.

### Eval harness

`backend/training/evaluate_insights_module.py` generates a 500-row
synthetic dataset with a clear signal pattern (amount × industry ×
activity count → win rate), runs the full feature pipeline + LightGBM
config through a stratified 80/20 split, and enforces a quality gate:

- Target **accuracy ≥ 0.75**
- Target **ROC AUC ≥ 0.80**

Current result: **accuracy 0.95, AUC 0.98** — passes the gate.

Run:
```bash
cd backend && source venv/bin/activate
python -m training.evaluate_insights_module
```

## Connecting to the Backend

The Vite dev server proxies `/api` → `http://localhost:8000`. The service files in `src/services/` are pre-wired with axios and JWT auth. Replace the mock data in `src/constants/mockData.js` with real API calls as the backend is built.

## License

Academic use only — Forman Christian College University FYP 2025-26.
