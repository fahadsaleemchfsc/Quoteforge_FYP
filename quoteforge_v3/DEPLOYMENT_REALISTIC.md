# QuoteForge — Realistic Deployment & Pricing

## The Honest Truth About Costs

You're right — enterprise cloud costs are overkill for most customers. Here's what actually makes sense.

## The Insight: Most Customers Don't Need a GPU

**Look at what QuoteForge actually does:**
- Pricing engine: Pure Python math — runs on a $5 VPS
- Document rendering: ReportLab + python-docx — runs on a $5 VPS
- CRM integration: HTTP calls to Salesforce — runs on a $5 VPS
- LLM generation: **The only part that needs beefy hardware**

**If we're smart about the LLM, we can run everything cheap:**
- **Fallback templates** (what we have now): **Zero compute needed**, 0.3s generation
- **Quantized small model** (Llama 3.2 1B Q4): Runs on any laptop CPU, 30-60s generation
- **Optional AI boost**: Only pay for GPU when customer wants faster/better quality

---

## The Realistic Pricing Tiers

### Tier 1: QuoteForge Starter — **FREE**
**Who:** Freelancers, single-person shops, evaluation
**Where runs:** Customer's existing laptop/desktop
**Hardware needed:** Any computer with 4GB RAM

```
Setup cost:         $0 (they already have a laptop)
Monthly cost:       $0 (runs on their machine)
Our license fee:    $0 (free tier)
Generation quality: Template-based (professional, not personalized)
Generation speed:   0.3 seconds per proposal
```

**What they get:**
- Basic template proposals
- PDF generation
- CRM integration
- 50 proposals/month free

---

### Tier 2: QuoteForge Pro — **$5/user/month**
**Who:** Pakistani SMBs, freelancer teams, consultants
**Where runs:** $5 DigitalOcean droplet (shared)
**Hardware:** 1 CPU, 1GB RAM VPS — handles 20+ customers

```
Our infrastructure cost:  $5/month DO droplet (shared across 20 customers)
                          = $0.25/customer/month
Per-customer cost:        $0.25
Our license fee:          $5/user/mo
Profit margin:            $4.75/user/mo (95%)

Customer pays:            $5/user/month
vs Salesforce CPQ:        $75/user/month (93% cheaper)
```

**What they get:**
- Everything in Starter
- Cloud-hosted (no install needed)
- Shared AI model (trained on all Pro customers aggregated)
- Fine-tuned proposals in their industry
- Unlimited proposals
- Email delivery

---

### Tier 3: QuoteForge Business — **$15/user/month**
**Who:** Mid-sized companies, 50-500 employees
**Where runs:** Dedicated $20/mo VPS per customer (2 CPU, 4GB RAM)

```
Our infrastructure cost:  $20/mo dedicated droplet
Customer has dedicated instance
Their own model (fine-tuned on their data)

Total cost for 50 users:  $20 infra + $750 license = $770/mo
vs Salesforce CPQ:        $3,750/mo (79% cheaper)
```

**What they get:**
- Everything in Pro
- **Their own fine-tuned model** (trained on their proposals)
- **Data never mixed** with other customers
- **Continuous learning** from their approved proposals
- Priority support
- Custom templates + branding

---

### Tier 4: QuoteForge Enterprise — **$25/user/month**
**Who:** Large companies, regulated industries
**Where runs:** Customer's own cloud account (BYOC)

```
Customer's infrastructure:  ~$100/mo (small VPS + GPU when needed)
Our license fee:            $25/user/mo

Total for 200 users:        $100 + $5,000 = $5,100/mo
vs Salesforce CPQ:          $15,000/mo (66% cheaper)
```

**What they get:**
- Everything in Business
- **BYOC deployment** — data stays in their AWS
- HIPAA/SOC2/PPRA compliance
- Dedicated support
- Air-gap capable

---

## GPU Strategy — Use On-Demand, Not 24/7

**The trick:** Don't keep a GPU running 24/7 (expensive). Only spin one up **when actually needed**.

```
Customer generates proposal
    ↓
  Is it urgent/high-quality needed?
    ├─ NO → Use templates (0.3s, $0 cost)
    └─ YES → Spin up spot GPU for 60 seconds
              RunPod Spot: $0.15/hour = $0.0025 per generation
              Customer pays $0.50 for premium generation
              Our margin: 99%
```

**Real cost math:**
- 100 premium generations/day × $0.0025 GPU cost = $0.25/day = **$7.50/month GPU cost**
- We charge $0.50 per premium = $50/day revenue = **$1500/month**
- GPU margin: **99.5%**

---

## Even Better: Use Cheap Batch Training

**For fine-tuning, not real-time inference:**

```
Customer has 50 approved proposals to learn from
    ↓
  Queue them for overnight batch training
    ↓
  Rent 1 RunPod spot GPU at 2am for 2 hours
    ↓
  Cost: $0.30 total per customer per month
    ↓
  Deploy new adapter in the morning
```

**This is how we keep per-customer fine-tuning profitable at $15/user/month.**

---

## The Actual Cost Structure (Honest)

### If You Have 10 Pro Customers (100 total users):
```
Revenue:
  10 customers × 10 users × $5/mo = $500/month

Costs:
  DigitalOcean shared VPS:         $20/mo
  Domain + SSL:                    $2/mo
  Database backups (Tigris):       $5/mo
  GPU batch training (weekly):     $3/mo
  ─────────────────────────────────────
  Total infra:                     $30/month

Profit:                            $470/month (94% margin)
```

### If You Have 100 Pro + 5 Business Customers (1300 users):
```
Revenue:
  Pro:      100 × 10 × $5  = $5,000/mo
  Business: 5 × 50 × $15   = $3,750/mo
  Total:                     $8,750/month

Costs:
  VPS pool (5 droplets):     $100/mo
  Dedicated droplets (5):    $100/mo
  GPU training hours:        $30/mo
  Support tooling:           $50/mo
  ─────────────────────────────────
  Total infra:               $280/month

Profit:                      $8,470/month (97% margin)
```

**That's a real bootstrappable business.**

---

## For Your FYP Demo

The deployment story to tell:

```
┌─────────────────────────────────────────────────────┐
│ QuoteForge runs anywhere:                            │
│                                                      │
│ • On the laptop you already own     → FREE           │
│ • On a $5/mo cloud server           → $5/user        │
│ • Fine-tuned per customer           → $15/user       │
│ • In the customer's own AWS         → $25/user       │
│                                                      │
│ Compare to Salesforce CPQ: $75/user — always         │
└─────────────────────────────────────────────────────┘
```

---

## What We Already Have That Proves This Works

**Right now, on your Mac M3:**
- ✅ Backend running in < 200MB RAM
- ✅ Proposal generation in **0.3 seconds** with templates
- ✅ AI-powered generation in **30 seconds** with fine-tuned model
- ✅ Zero cloud costs
- ✅ Full Salesforce integration

**Your FYP already proves:** You can run a full CPQ product on a consumer laptop. That's a powerful statement about cost-efficiency that enterprise vendors can't match.

---

## The Honest Value Prop

"QuoteForge is **90% cheaper** than Salesforce CPQ because:
1. We run on commodity hardware (not specialized CPQ servers)
2. We use open-source LLMs (no per-token OpenAI fees)
3. GPU is pay-per-use (not 24/7)
4. We pass savings to customers"

**Pricing table to show in your pitch:**

| Users | Salesforce CPQ | QuoteForge Pro | Savings |
|-------|----------------|----------------|---------|
| 10 | $750/mo | $50/mo | $700/mo |
| 50 | $3,750/mo | $250/mo | $3,500/mo |
| 100 | $7,500/mo | $500/mo | $7,000/mo |
| 500 | $37,500/mo | $2,500/mo | $35,000/mo |

A Pakistani company with 50 users saves **$42,000/year**. That's real money.
