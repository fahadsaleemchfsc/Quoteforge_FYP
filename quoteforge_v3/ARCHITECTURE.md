# QuoteForge Product Architecture

## What QuoteForge Actually Does

QuoteForge is an **AI-powered quote and proposal generation system** that lives inside the customer's own infrastructure. It:

1. **Reads deal data from CRM** (Salesforce, HubSpot, etc.)
2. **Generates professional proposals** using a customer-specific fine-tuned LLM
3. **Applies deterministic pricing rules** (discounts, tax, compliance)
4. **Renders branded PDF/DOCX documents**
5. **Uploads back to CRM** as attached Files with metadata
6. **Continuously learns** from approved proposals to get smarter over time

---

## The Three Product Principles

### 1. Simplest Possible Trigger
```
Sales rep types: "Quote for Acme Corp"
            OR:  "006gL00000KlPp7QAF" (Salesforce ID)
            OR:  "Dickenson Mobile Generators"

Everything else happens automatically.
```

No forms. No wizards. Just one input → PDF in Salesforce.

### 2. Zero Data Egress
Customer data **never leaves the customer's infrastructure**.

```
┌─────────────────────────────────────────────────────┐
│  CUSTOMER A's CLOUD (AWS / Azure / On-Prem)          │
│                                                      │
│  ┌─────────────┐   ┌─────────────────────────────┐  │
│  │ Salesforce  │───│   QuoteForge Instance       │  │
│  │ (CRM Data)  │   │                             │  │
│  └─────────────┘   │  ┌──────────────────────┐   │  │
│                    │  │ Fine-tuned LLM       │   │  │
│                    │  │ (customer-specific)  │   │  │
│                    │  └──────────────────────┘   │  │
│                    │  ┌──────────────────────┐   │  │
│                    │  │ Pricing Engine       │   │  │
│                    │  │ (deterministic)      │   │  │
│                    │  └──────────────────────┘   │  │
│                    │  ┌──────────────────────┐   │  │
│                    │  │ Document Engine      │   │  │
│                    │  │ (PDF/DOCX render)    │   │  │
│                    │  └──────────────────────┘   │  │
│                    └─────────────────────────────┘  │
│                                                      │
│  No data flows outside this perimeter.              │
│  No third-party API calls. No cloud AI services.    │
└─────────────────────────────────────────────────────┘
```

### 3. Continuous Learning Per Customer
Each customer's model silently gets smarter:

```
Day 1:  Base Mistral-7B + QuoteForge synthetic data → "Model v1"
Day 30: + 50 approved proposals from Customer A → "Customer A Model v2"
Day 60: + 100 approved proposals                → "Customer A Model v3"
Day 90: Customer A's model writes proposals in THEIR VOICE

Meanwhile, Customer B has a completely different v3,
  trained only on Customer B's proposals.
  Their models never mix.
```

---

## Deployment Models

QuoteForge supports **four deployment tiers** — customers choose based on their data sensitivity, budget, and IT maturity. See [DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md) for details.

| Tier | Where It Runs | Price | Best For |
|------|---------------|-------|----------|
| **Multi-Tenant SaaS** | QuoteForge shared GPU cluster | $25/user/mo | SMBs, startups |
| **Single-Tenant Managed** | Dedicated VM in QuoteForge cloud | $500-1500/mo + license | Mid-market |
| **BYOC (Bring Your Own Cloud)** | Customer's AWS/Azure/GCP | ~$1500/mo infra + license | Enterprise, regulated |
| **On-Premise Air-Gapped** | Customer's data center | ~$50K one-time + support | Government, defense |

### Cost Comparison (50 users)
| Tier | Monthly Cost | vs Salesforce CPQ ($75/user) |
|------|--------------|------------------------------|
| Multi-Tenant | $1,250 | Saves $2,500/mo |
| Single-Tenant | $2,000 | Saves $1,750/mo |
| BYOC | $2,800 | Saves $950/mo |
| On-Premise | Varies | Long-term: cheapest |

---

## The End-to-End Flow

```
┌──────────────────────────────────────────────────────────┐
│  1. TRIGGER                                               │
│  Sales rep in Salesforce types "Acme Corp" and hits ▶    │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  2. RESOLVE (via Apex callout)                            │
│  QuoteForge finds Opportunity "006..." in SF              │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  3. FETCH (SF REST API)                                   │
│  • Opportunity: Name, Amount, Stage, Close Date           │
│  • Account: Name, Industry, Billing Country               │
│  • Line Items: Products, quantities, prices               │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  4. PRICE (Deterministic Engine)                          │
│  • Apply discount rules (15% if > $50K)                   │
│  • Apply regional tax (7.5% US, 17% PK, 20% EU)           │
│  • Select compliance (SOC 2, GDPR, PPRA)                  │
│  • Never let LLM calculate numbers                        │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  5. GENERATE (Fine-Tuned LLM)                             │
│  For each section (Cover Letter, Scope, Pricing,          │
│  Deliverables, Terms, Summary):                           │
│    → Fill prompt with deal data                           │
│    → Run through customer-specific Llama 3.2              │
│    → Validate output (no price hallucination)             │
│    → Fall back to templates if LLM fails                  │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  6. RENDER (Document Engine)                              │
│  • ReportLab for PDF / python-docx for DOCX               │
│  • Brand colors, logo, headers, footers                   │
│  • Pricing table with line items                          │
│  • Validity date (30 days)                                │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  7. UPLOAD (SF API)                                       │
│  • ContentVersion → PDF file                              │
│  • ContentDocumentLink → links to Opportunity             │
│  • QuoteForge_Document__c → stores metadata               │
│  • Task → logs activity on timeline                       │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  8. LEARN (Background)                                    │
│  When sales rep approves/edits proposal:                  │
│    → Feedback signal saved                                │
│    → After 50 signals, incremental retrain               │
│    → Model gets smarter on THIS customer's style         │
│    → Deployed as new adapter version                     │
└──────────────────────────────────────────────────────────┘
```

---

## What's Different From Competitors

| Feature | QuoteForge | PandaDoc | Salesforce CPQ | DocuSign |
|---------|------------|----------|----------------|----------|
| **AI-native generation** | ✅ | ⚠️ (bolt-on) | ⚠️ (Einstein GPT) | ❌ |
| **Self-hosted** | ✅ | ❌ | ❌ | ❌ |
| **Data never leaves org** | ✅ | ❌ | ❌ | ❌ |
| **Per-customer model** | ✅ | ❌ | ❌ | ❌ |
| **Continuous learning** | ✅ | ❌ | ❌ | ❌ |
| **Open-source LLM** | ✅ | ❌ | ❌ | ❌ |
| **PPRA Pakistan** | ✅ | ❌ | ❌ | ❌ |
| **Price** | $15-25/user | $35-65/user | $75-150/user | $25-60/user |

---

## API Endpoints

### Simple Trigger (the "Just generate it" endpoint)
```bash
POST /api/crm/salesforce/quick-generate
{
  "deal_identifier": "Acme Corp"   # or "006gL00000KlPp7QAF"
}
```

### Prompt-to-Deal (natural language → new Opportunity)
```bash
POST /api/crm/salesforce/create-deal-from-prompt
{
  "prompt": "Proposal for Acme, $50K enterprise license",
  "output_format": "PDF"
}
```

### Feedback Loop (continuous learning)
```bash
POST /api/learning/feedback
{
  "doc_id": "DOC-2421",
  "feedback_type": "approved"   # or "edited" or "rejected"
}
```

### Learning Stats
```bash
GET /api/learning/stats

Response:
{
  "current_model_version": "v2",
  "total_feedback_collected": 47,
  "approved_proposals": 42,
  "new_since_last_training": 35,
  "next_training_when": "50 approved proposals",
  "ready_to_retrain": false
}
```

### Manual Retrain (admin only)
```bash
POST /api/learning/retrain?force=true
```

---

## Security & Compliance

### Data Boundary Map
| Data Type | Where It Lives | Retention |
|-----------|---------------|-----------|
| CRM deal data | Customer's Salesforce (read-only fetch) | Not stored |
| Generated PDFs | Customer's Salesforce (ContentVersion) | Forever |
| Model weights | Customer's infrastructure | Forever |
| Training signals | Customer's DB | 90 days default |
| Audit logs | Customer's DB | 90 days minimum |
| OAuth tokens | Customer's DB (encrypted) | Until revoked |

### What QuoteForge Corp Sees
**Nothing.** The software runs entirely in customer's environment. QuoteForge (the company) only receives:
- License validation pings
- Opt-in telemetry (aggregate feature usage, no content)

### Compliance Frameworks Built In
- **SOC 2 Type II** — security, availability, confidentiality controls
- **GDPR** — data minimization, right to erasure, DPA
- **PPRA (Pakistan)** — transparent pricing, audit trails
- **HIPAA** — (optional add-on for healthcare)
- **PCI DSS** — (never stores payment data)

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend API | FastAPI (async Python) |
| Database | PostgreSQL (production) / SQLite (dev) |
| AI Model | Mistral-7B / Llama-3.2 (fine-tuned, quantized) |
| Inference | MLX (Apple Silicon) / vLLM (GPU) / Ollama |
| Document Engine | ReportLab + python-docx |
| RAG Store | ChromaDB with sentence-transformers |
| Salesforce | LWC + Apex (native package) |
| Orchestration | Docker Compose / Kubernetes |
