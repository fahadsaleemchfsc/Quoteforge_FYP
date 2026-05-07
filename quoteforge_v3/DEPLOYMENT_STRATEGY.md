# QuoteForge Deployment Strategy

## The Honest Reality

**Question:** "Where does the LLM actually run?"

**Answer:** There's no single answer. Different customers need different deployment models based on their data sensitivity, budget, and technical capabilities.

---

## Four Deployment Models

### Model 1: BYOC (Bring Your Own Cloud) — Enterprise & Regulated
**Who:** Enterprise, government, healthcare, financial services
**Data location:** Customer's AWS/Azure/GCP account

```
┌────────────────────────────────────────────────┐
│  CUSTOMER'S AWS ACCOUNT                         │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  VPC: QuoteForge-customer-prod            │  │
│  │                                            │  │
│  │  • EC2 g5.xlarge (A10G GPU)     $730/mo   │  │
│  │  • RDS PostgreSQL                $50/mo   │  │
│  │  • S3 (document storage)         $10/mo   │  │
│  │  • Secrets Manager (OAuth)       $1/mo    │  │
│  │                                            │  │
│  │  QuoteForge Software License: $15-25/user/mo │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘

Total cost for 50 users: ~$1,550/mo infra + $1,250/mo license = $2,800/mo
vs Salesforce CPQ ($75/user × 50 = $3,750/mo)
```

**How it's set up:**
```bash
# Customer runs (one-time):
terraform apply -var customer_name="acme-corp" \
                -var aws_account_id="xxx"

# This creates:
# - VPC with private subnets
# - EC2 with GPU, Docker, QuoteForge image
# - RDS instance
# - OAuth credentials in Secrets Manager
# - Application Load Balancer
# - Auto-scaling policies
```

**Pros:**
- ✅ Zero data egress (data never leaves customer's AWS)
- ✅ Customer owns all infrastructure
- ✅ Full compliance control (SOC 2, HIPAA, FedRAMP)
- ✅ Customer can audit everything

**Cons:**
- ❌ Customer needs DevOps team
- ❌ Customer pays infrastructure costs
- ❌ Setup takes 2-4 hours

---

### Model 2: Single-Tenant Managed — Mid-Market
**Who:** Mid-market companies (100-1000 employees)
**Data location:** Dedicated QuoteForge-managed VPC per customer

```
┌─────────────────────────────────────────────────────┐
│  QUOTEFORGE CLOUD (we manage)                        │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│  │ Customer A   │  │ Customer B   │  │ Customer C ││
│  │ VPC (isolated)│  │ VPC (isolated)│  │ VPC       ││
│  │              │  │              │  │            ││
│  │ • Own GPU   │  │ • Own GPU   │  │ • Own GPU ││
│  │ • Own DB    │  │ • Own DB    │  │ • Own DB  ││
│  │ • Own model │  │ • Own model │  │ • Own model││
│  └──────────────┘  └──────────────┘  └────────────┘│
│                                                      │
│  Hardware shared, data/models isolated per customer │
└─────────────────────────────────────────────────────┘

Price to customer: $500-1500/mo all-in (50 users)
```

**Pros:**
- ✅ No customer IT team needed
- ✅ Data logically isolated
- ✅ Model still unique per customer
- ✅ QuoteForge handles ops

**Cons:**
- ⚠️ Data technically in our infrastructure (but encrypted, isolated)
- ⚠️ Not for regulated industries

---

### Model 3: Multi-Tenant SaaS — SMB
**Who:** Small businesses, startups, self-serve customers
**Data location:** Shared QuoteForge infrastructure

```
┌────────────────────────────────────────────────────────┐
│  QUOTEFORGE MULTI-TENANT CLOUD                          │
│                                                         │
│  ┌────────────────────────────────────────────────┐   │
│  │  Shared GPU cluster                             │   │
│  │  • Generation happens in shared inference pool  │   │
│  │  • Each request isolated, no cross-contamination│   │
│  │  • Data encrypted with customer-specific keys   │   │
│  │                                                  │   │
│  │  Shared PostgreSQL (tenant-isolated via RLS)    │   │
│  └────────────────────────────────────────────────┘   │
│                                                         │
│  Price to customer: $25/user/mo (self-serve)           │
└────────────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Cheapest
- ✅ Fastest to onboard (5 min signup)
- ✅ Always up-to-date
- ✅ Shared model (trained on anonymized aggregate data)

**Cons:**
- ❌ No per-customer fine-tuning
- ❌ Data in shared infrastructure
- ⚠️ Not suitable for regulated industries

---

### Model 4: On-Premise — Government & Defense
**Who:** Pakistani government (PPRA), defense, classified
**Data location:** Customer's own data center, air-gapped

```
┌──────────────────────────────────────────────────┐
│  CUSTOMER'S ON-PREMISE DATA CENTER (AIR-GAPPED)   │
│                                                   │
│  Physical Servers:                                │
│  • Dell R750 with NVIDIA A100 GPU (~$25K hardware)│
│  • Storage SAN                                    │
│  • Internal network only — no internet access     │
│                                                   │
│  QuoteForge Software:                             │
│  • Licensed perpetual (~$50K one-time + support)  │
│  • Delivered as OVF/ISO                           │
│  • Zero phone-home telemetry                      │
└──────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Ultimate privacy
- ✅ Works offline
- ✅ No cloud dependency

**Cons:**
- ❌ Expensive upfront
- ❌ Manual updates
- ❌ Customer owns hardware maintenance

---

## Which Model Fits Your Customer?

| Your Customer | Recommended Model | Why |
|---------------|-------------------|-----|
| **Pakistani government (PPRA)** | On-Premise or BYOC | Data sovereignty required |
| **US Healthcare (HIPAA)** | BYOC | Compliance requirement |
| **US Fortune 500** | BYOC or Single-Tenant | IT maturity, budget |
| **European SMB** | Single-Tenant | GDPR comfort, mid-budget |
| **Startups** | Multi-Tenant SaaS | Cheapest, fastest |

---

## Technical Implementation

### BYOC — Terraform Template
```hcl
# terraform/main.tf
module "quoteforge" {
  source = "quoteforge/aws/terraform"

  customer_name    = "acme-corp"
  deployment_tier  = "enterprise"  # enterprise | mid | small
  gpu_type         = "g5.xlarge"   # a10g for 7B model, p4d for 70B
  backup_retention = 30

  # Compliance
  compliance_mode  = "hipaa"       # hipaa | gdpr | ppra | soc2
  encryption_kms   = true
  audit_logging    = "cloudtrail"
}
```

### Single-Tenant — Kubernetes
```yaml
# k8s per-customer namespace
apiVersion: v1
kind: Namespace
metadata:
  name: customer-acme-corp
  labels:
    tenant: acme-corp
    tier: enterprise
---
# Dedicated GPU node for this customer
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quoteforge-llm
  namespace: customer-acme-corp
spec:
  replicas: 1
  template:
    spec:
      nodeSelector:
        tenant: acme-corp  # Pinned to customer's dedicated node
      containers:
      - name: vllm
        image: quoteforge/llm:v2
        resources:
          limits:
            nvidia.com/gpu: 1
```

### Multi-Tenant — Row-Level Security
```sql
-- Every query auto-filtered by tenant
CREATE POLICY tenant_isolation ON documents
  USING (tenant_id = current_setting('app.current_tenant')::uuid);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
```

---

## For the FYP Demo

**What we have right now:** Local dev setup on your Mac (Multi-Tenant pattern)

**What enterprise customers would get:** BYOC with Terraform deployment

**The pitch:**
> "QuoteForge offers four deployment tiers. SMBs can start on our managed SaaS ($25/user). Enterprises can deploy to their own AWS account via Terraform, keeping all data in their VPC. Governments and high-compliance industries can run fully air-gapped on their own hardware. **The software is the same; only the hosting location changes.**"

---

## Honest Answer to "Where Does the LLM Run?"

**Depends on the deployment tier:**

| Tier | LLM Location | Customer Data |
|------|--------------|---------------|
| **BYOC** | Customer's AWS EC2 with GPU | Customer's account |
| **Single-Tenant** | QuoteForge's GPU (dedicated VM) | Isolated in our infra |
| **Multi-Tenant** | QuoteForge's shared GPU cluster | Encrypted in shared DB |
| **On-Premise** | Customer's physical server | Customer's data center |

**The promise we CAN make to every tier:**
- ✅ Data is encrypted at rest and in transit
- ✅ No third-party LLM API calls (OpenAI, Anthropic, etc.)
- ✅ Each tier has appropriate compliance attestation

**The stronger promise for BYOC + On-Premise:**
- ✅ Data literally never crosses customer's network perimeter
- ✅ Air-gap possible (on-premise)
