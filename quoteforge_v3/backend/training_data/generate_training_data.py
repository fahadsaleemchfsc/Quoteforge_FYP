"""
Training Data Generator for QuoteForge Fine-Tuning
===================================================
Generates JSONL datasets for fine-tuning LLMs on professional proposal generation.

Two output formats:
1. OpenAI fine-tuning format (chat completions JSONL)
2. Hugging Face format (instruction-response pairs)

The training data covers all 6 proposal sections:
- Cover Letter, Executive Summary, Scope of Work,
- Pricing Notes, Deliverables, Terms & Conditions
"""

import json
import random
import os
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent
SECTIONS = ["Cover Letter", "Scope", "Pricing", "Deliverables", "Terms", "Summary"]

# ─── Realistic Company and Deal Data ─────────────────────────────

COMPANIES = [
    {"name": "Acme Corporation", "industry": "Manufacturing", "region": "US", "size": "Enterprise"},
    {"name": "TechStart Inc", "industry": "SaaS Technology", "region": "US", "size": "Mid-Market"},
    {"name": "Global Traders LLC", "industry": "Import/Export", "region": "EU", "size": "SMB"},
    {"name": "Pakistan Federal Ministry of IT", "industry": "Government", "region": "PK", "size": "Government"},
    {"name": "Nexus Systems", "industry": "Cloud Infrastructure", "region": "US", "size": "Enterprise"},
    {"name": "Pinnacle Health Solutions", "industry": "Healthcare", "region": "US", "size": "Mid-Market"},
    {"name": "Vertex Financial Group", "industry": "Financial Services", "region": "EU", "size": "Enterprise"},
    {"name": "Lahore Development Authority", "industry": "Government", "region": "PK", "size": "Government"},
    {"name": "Atlas Digital Agency", "industry": "Marketing", "region": "US", "size": "SMB"},
    {"name": "Pacific Logistics Corp", "industry": "Supply Chain", "region": "US", "size": "Enterprise"},
    {"name": "MedTech Innovations", "industry": "Medical Devices", "region": "EU", "size": "Mid-Market"},
    {"name": "Karachi Chamber of Commerce", "industry": "Trade Association", "region": "PK", "size": "Government"},
    {"name": "SkyBridge Analytics", "industry": "Data Analytics", "region": "US", "size": "SMB"},
    {"name": "Continental Insurance", "industry": "Insurance", "region": "EU", "size": "Enterprise"},
    {"name": "EduTech Pakistan", "industry": "Education Technology", "region": "PK", "size": "SMB"},
    {"name": "Meridian Consulting Group", "industry": "Management Consulting", "region": "US", "size": "Mid-Market"},
    {"name": "Aurora Biotech", "industry": "Biotechnology", "region": "EU", "size": "Enterprise"},
    {"name": "Punjab IT Board", "industry": "Government IT", "region": "PK", "size": "Government"},
    {"name": "RedLine Security", "industry": "Cybersecurity", "region": "US", "size": "SMB"},
    {"name": "Oasis Retail Group", "industry": "Retail", "region": "EU", "size": "Mid-Market"},
]

DEALS = [
    {"name": "Enterprise License Agreement", "products": [
        {"product": "Enterprise Platform License", "quantity": 1, "unit_price": 50000},
        {"product": "Implementation Services", "quantity": 1, "unit_price": 15000},
        {"product": "Annual Support & Maintenance", "quantity": 1, "unit_price": 10000},
    ]},
    {"name": "SaaS Platform Migration", "products": [
        {"product": "Cloud Migration Services", "quantity": 1, "unit_price": 45000},
        {"product": "SaaS Platform License (3yr)", "quantity": 1, "unit_price": 63000},
        {"product": "Training Program", "quantity": 20, "unit_price": 1000},
    ]},
    {"name": "Data Analytics Suite", "products": [
        {"product": "Analytics Dashboard", "quantity": 1, "unit_price": 12500},
        {"product": "Data Integration Service", "quantity": 1, "unit_price": 7500},
        {"product": "Monthly Support Contract", "quantity": 12, "unit_price": 500},
    ]},
    {"name": "Cybersecurity Assessment", "products": [
        {"product": "Vulnerability Assessment", "quantity": 1, "unit_price": 25000},
        {"product": "Penetration Testing", "quantity": 1, "unit_price": 35000},
        {"product": "Security Training Workshop", "quantity": 5, "unit_price": 3000},
    ]},
    {"name": "Document Management System", "products": [
        {"product": "DMS Platform License", "quantity": 1, "unit_price": 30000},
        {"product": "Compliance Module", "quantity": 1, "unit_price": 10000},
        {"product": "Training & Deployment", "quantity": 1, "unit_price": 5000},
    ]},
    {"name": "ERP Integration Project", "products": [
        {"product": "ERP Connector Development", "quantity": 1, "unit_price": 40000},
        {"product": "Data Migration", "quantity": 1, "unit_price": 20000},
        {"product": "UAT & Go-Live Support", "quantity": 1, "unit_price": 15000},
    ]},
    {"name": "Marketing Automation Platform", "products": [
        {"product": "Platform License (Annual)", "quantity": 1, "unit_price": 18000},
        {"product": "Campaign Setup & Configuration", "quantity": 1, "unit_price": 8000},
        {"product": "Content Strategy Workshop", "quantity": 1, "unit_price": 5000},
    ]},
    {"name": "Infrastructure Modernization", "products": [
        {"product": "Infrastructure Assessment", "quantity": 1, "unit_price": 15000},
        {"product": "Cloud Architecture Design", "quantity": 1, "unit_price": 25000},
        {"product": "Migration Execution", "quantity": 1, "unit_price": 35000},
        {"product": "Post-Migration Support (6mo)", "quantity": 1, "unit_price": 14000},
    ]},
    {"name": "AI-Powered Customer Service", "products": [
        {"product": "AI Chatbot Platform", "quantity": 1, "unit_price": 35000},
        {"product": "NLP Model Training", "quantity": 1, "unit_price": 20000},
        {"product": "Integration Services", "quantity": 1, "unit_price": 12000},
        {"product": "12-Month Support Plan", "quantity": 1, "unit_price": 8000},
    ]},
    {"name": "Procurement Management System", "products": [
        {"product": "Procurement Platform License", "quantity": 1, "unit_price": 25000},
        {"product": "PPRA Compliance Module", "quantity": 1, "unit_price": 15000},
        {"product": "Vendor Portal Setup", "quantity": 1, "unit_price": 10000},
        {"product": "Training & Onboarding", "quantity": 1, "unit_price": 5000},
    ]},
]

COMPLIANCE = {
    "US": {"framework": "SOC 2, GDPR", "clauses": "This engagement adheres to SOC 2 Type II security standards and GDPR data protection requirements. All data processing occurs within certified environments with full encryption at rest and in transit."},
    "EU": {"framework": "GDPR", "clauses": "Processing of personal data complies with GDPR (EU) 2016/679. A Data Processing Agreement (DPA) is included. Data subjects retain all rights including erasure, portability, and access."},
    "PK": {"framework": "PPRA", "clauses": "This proposal complies with PPRA Rules 2004 of Pakistan. Transparent pricing, competitive documentation, and procurement audit trails are provided as required by the Public Procurement Regulatory Authority."},
}


# ─── Section Content Generators ──────────────────────────────────

def gen_cover_letter(company, deal, amount, region, compliance):
    variants = [
        f"""Dear {company['name']} Team,

We are delighted to present this proposal for the {deal['name']} engagement. At QuoteForge Solutions, we understand that {company['industry'].lower()} organizations like yours require solutions that are not only technologically advanced but also compliant with {compliance['framework']} standards.

Our proposed solution, valued at ${amount:,.2f}, has been carefully designed to address your specific operational requirements while ensuring full regulatory compliance. We have successfully delivered similar solutions to over 200 {company['size'].lower()}-level organizations across the {region} region.

We look forward to discussing this proposal in detail and demonstrating how our solution can drive measurable value for {company['name']}. Our team is available for a follow-up call at your earliest convenience.

Warm regards,
The QuoteForge Solutions Team""",

        f"""Dear Valued Partners at {company['name']},

Thank you for the opportunity to submit this proposal for the {deal['name']}. We have invested significant effort in understanding your organization's unique challenges in the {company['industry'].lower()} sector and have tailored this solution accordingly.

This engagement represents a total investment of ${amount:,.2f}, reflecting our commitment to delivering enterprise-grade capabilities at competitive pricing. Every component of this proposal has been validated against {compliance['framework']} compliance requirements to ensure seamless alignment with your regulatory obligations.

We are confident that this partnership will yield substantial returns in operational efficiency and compliance assurance. We welcome the opportunity to present this proposal and address any questions your team may have.

Best regards,
QuoteForge Solutions""",

        f"""To the Leadership Team at {company['name']},

We are pleased to present our comprehensive proposal for the {deal['name']}. Having worked extensively with {company['industry'].lower()} organizations across the {region} market, we bring deep domain expertise and a proven track record of successful delivery.

The proposed solution totals ${amount:,.2f} and encompasses end-to-end implementation, training, and ongoing support. Our approach prioritizes minimal disruption to your existing operations while maximizing the value delivered from day one.

{compliance['clauses']}

We are eager to begin this partnership and remain available to discuss any aspect of this proposal at your convenience.

Sincerely,
QuoteForge Solutions Team""",
    ]
    return random.choice(variants)


def gen_scope(company, deal, products, region):
    items_text = "\n".join(f"  - {p['product']} (Quantity: {p['quantity']})" for p in products)
    variants = [
        f"""Scope of Work — {deal['name']}

1. PROJECT OBJECTIVES
The objective of this engagement is to deliver a complete {deal['name'].lower()} solution for {company['name']}, enabling improved operational efficiency, regulatory compliance, and measurable business outcomes within the {company['industry'].lower()} sector.

2. DELIVERABLES
The following deliverables are included in this engagement:
{items_text}

3. TIMELINE & MILESTONES
  - Week 1-2: Discovery & Requirements Gathering
  - Week 3-4: Solution Design & Architecture
  - Week 5-8: Implementation & Configuration
  - Week 9-10: Testing & Quality Assurance
  - Week 11-12: Training, UAT & Go-Live

4. SUCCESS CRITERIA
  - All deliverables accepted by {company['name']} stakeholders
  - System operational with 99.5% uptime within 30 days of go-live
  - All compliance requirements ({COMPLIANCE[region]['framework']}) validated
  - End-user training completed with satisfaction score above 4.0/5.0

5. ASSUMPTIONS & DEPENDENCIES
  - {company['name']} will provide timely access to required systems and personnel
  - Existing infrastructure meets minimum technical requirements
  - Project governance will include bi-weekly steering committee meetings
  - Change requests beyond this scope will be documented and priced separately""",

        f"""Scope of Work — {deal['name']} for {company['name']}

OVERVIEW
This document defines the scope of work for the {deal['name']} project. The engagement covers design, implementation, testing, and deployment of the following solution components:

SOLUTION COMPONENTS
{items_text}

PROJECT PHASES

Phase 1: Assessment & Planning (Weeks 1-2)
  - Current state analysis and gap assessment
  - Detailed project plan and resource allocation
  - Stakeholder alignment workshops

Phase 2: Build & Configure (Weeks 3-6)
  - Core platform deployment and configuration
  - Custom integrations and data migration
  - Security hardening and compliance validation

Phase 3: Test & Validate (Weeks 7-8)
  - Functional testing and user acceptance testing
  - Performance benchmarking
  - Compliance audit against {COMPLIANCE[region]['framework']}

Phase 4: Launch & Transition (Weeks 9-10)
  - Production deployment and cutover
  - End-user training program delivery
  - Operational handover and support activation

GOVERNANCE
  - Dedicated project manager assigned from both parties
  - Weekly status reports and monthly executive reviews
  - Risk register maintained and reviewed bi-weekly""",
    ]
    return random.choice(variants)


def gen_pricing(company, deal, products, subtotal, discount, tax, total, region):
    items_text = "\n".join(
        f"  {p['product']:.<50} {p['quantity']:>5} x ${p['unit_price']:>10,.2f} = ${p['quantity']*p['unit_price']:>12,.2f}"
        for p in products
    )
    variants = [
        f"""Pricing Summary — {deal['name']}

The following pricing has been prepared for {company['name']} based on the scope defined in this proposal:

LINE ITEMS
{items_text}

{'─' * 70}
  Subtotal: ${subtotal:>52,.2f}
  Discount Applied: -${discount:>47,.2f}
  Applicable Tax: ${tax:>50,.2f}
  ═══════════════════════════════════════════════════════════════
  TOTAL: ${total:>55,.2f}

PAYMENT TERMS
  - 30% upon contract execution (${total * 0.3:,.2f})
  - 40% upon milestone completion (${total * 0.4:,.2f})
  - 30% upon final acceptance (${total * 0.3:,.2f})
  - Payment due within Net 30 days of invoice date
  - Late payments subject to 1.5% monthly interest

PRICING VALIDITY
This pricing is valid for 30 days from the date of this proposal. Prices are quoted in USD and are exclusive of any taxes not explicitly stated above.

COMPLIANCE NOTE
All pricing complies with {COMPLIANCE[region]['framework']} requirements for transparent pricing documentation and audit trail maintenance.""",

        f"""Investment Summary — {deal['name']}

We have structured this investment to maximize value for {company['name']} while maintaining competitive pricing for the {company['industry'].lower()} market.

DETAILED PRICING
{items_text}

FINANCIAL SUMMARY
  Subtotal: ${subtotal:,.2f}
  Volume/Enterprise Discount: -${discount:,.2f}
  Tax ({region} applicable rates): ${tax:,.2f}
  Total Investment: ${total:,.2f}

This pricing reflects our enterprise-tier rates and includes all implementation, configuration, and initial training costs. No hidden fees or additional charges will be applied.

PAYMENT SCHEDULE
  Milestone 1 — Contract Signing: ${total * 0.3:,.2f} (30%)
  Milestone 2 — Implementation Complete: ${total * 0.4:,.2f} (40%)
  Milestone 3 — Go-Live & Acceptance: ${total * 0.3:,.2f} (30%)

All invoices are payable within Net 30 days. This proposal is valid for 30 calendar days.""",
    ]
    return random.choice(variants)


def gen_deliverables(company, deal, products):
    deliverable_entries = []
    for i, p in enumerate(products, 1):
        deliverable_entries.append(
            f"  {i}. {p['product']}\n"
            f"     Description: {p.get('description', 'As specified in scope of work')}\n"
            f"     Quantity: {p['quantity']}\n"
            f"     Acceptance Criteria: Functional testing complete, stakeholder sign-off obtained\n"
            f"     Timeline: Delivered within project schedule as defined in Scope of Work"
        )

    items_text = "\n\n".join(deliverable_entries)
    return f"""Deliverables — {deal['name']}

The following deliverables will be provided to {company['name']} as part of this engagement:

{items_text}

DELIVERABLE ACCEPTANCE PROCESS
1. Each deliverable will be submitted with a completion notice
2. {company['name']} has 5 business days to review and provide feedback
3. Minor revisions will be addressed within 3 business days
4. Formal acceptance sign-off required for each deliverable
5. Any disputes will be escalated to project steering committee

QUALITY STANDARDS
  - All deliverables undergo internal quality review before submission
  - Code deliverables include documentation and test coverage reports
  - Configuration deliverables include runbooks and maintenance guides
  - Training deliverables include materials, recordings, and assessment tools"""


def gen_terms(company, deal, region, compliance):
    base_terms = f"""Terms and Conditions — {deal['name']}

1. AGREEMENT
This proposal, upon acceptance by {company['name']}, constitutes a binding agreement between the parties. The engagement shall commence upon receipt of the signed Statement of Work and initial payment.

2. PAYMENT TERMS
All invoices are due within thirty (30) days of the invoice date (Net 30). Late payments shall accrue interest at 1.5% per month. {company['name']} shall notify the provider of any disputed charges within ten (10) business days.

3. INTELLECTUAL PROPERTY
All pre-existing intellectual property remains with its respective owner. Custom deliverables created specifically for {company['name']} under this engagement shall become the property of {company['name']} upon full payment.

4. CONFIDENTIALITY
Both parties agree to maintain strict confidentiality of all proprietary information exchanged during this engagement. Confidential information shall not be disclosed to third parties without prior written consent. This obligation survives termination of the agreement.

5. WARRANTY
All deliverables are warranted for a period of twelve (12) months from acceptance. During the warranty period, defects in functionality will be remedied at no additional charge.

6. LIMITATION OF LIABILITY
Total aggregate liability under this agreement shall not exceed the total contract value. Neither party shall be liable for indirect, incidental, or consequential damages.

7. TERMINATION
Either party may terminate this agreement with thirty (30) days written notice. Upon termination, {company['name']} shall pay for all work completed up to the termination date.

8. FORCE MAJEURE
Neither party shall be held liable for delays or failures in performance resulting from circumstances beyond reasonable control, including natural disasters, government actions, or infrastructure failures."""

    compliance_section = f"""
9. REGULATORY COMPLIANCE
{compliance['clauses']}

Compliance Framework: {compliance['framework']}
"""

    if region == "PK":
        compliance_section += """
10. PPRA-SPECIFIC PROVISIONS
  - All pricing is transparent and documented for audit purposes
  - Competitive bidding documentation is maintained
  - Procurement processes comply with PPRA Rules 2004
  - Full audit trail is available for regulatory review
  - Tax compliance includes 17% GST as applicable
"""
    elif region == "EU":
        compliance_section += """
10. GDPR-SPECIFIC PROVISIONS
  - A Data Processing Agreement (DPA) is attached as Appendix A
  - Data subjects retain rights to access, rectification, and erasure
  - Data processing is limited to the minimum necessary for service delivery
  - Cross-border data transfers comply with Standard Contractual Clauses (SCCs)
  - Data breach notification will occur within 72 hours of discovery
"""
    else:
        compliance_section += """
10. SOC 2 & GDPR PROVISIONS
  - Service delivery adheres to SOC 2 Type II trust service criteria
  - Annual SOC 2 audit reports are available upon request
  - GDPR compliance is maintained for any EU data subject information
  - Data encryption standards: AES-256 at rest, TLS 1.3 in transit
  - Access controls follow principle of least privilege
"""

    return base_terms + compliance_section


def gen_summary(company, deal, amount, products, region, compliance):
    product_list = ", ".join(p['product'] for p in products[:3])
    variants = [
        f"""Executive Summary

{company['name']} seeks a comprehensive {deal['name'].lower()} solution to strengthen its {company['industry'].lower()} operations and maintain competitive advantage in the {region} market. This proposal outlines a structured engagement valued at ${amount:,.2f} that addresses your organization's specific requirements.

Our solution encompasses {product_list}, delivered through a proven methodology that minimizes risk and maximizes business value. With extensive experience serving {company['size'].lower()}-level {company['industry'].lower()} organizations, we bring both technical depth and domain expertise to this engagement.

Key benefits of the proposed solution include:
  - Reduced operational overhead through automation and integration
  - Full compliance with {compliance['framework']} regulatory requirements
  - Dedicated project management and 12-month post-delivery support
  - Measurable ROI within the first 6 months of deployment

We are committed to delivering exceptional value and building a long-term partnership with {company['name']}.""",

        f"""Executive Summary

This proposal presents a tailored {deal['name'].lower()} solution for {company['name']}, designed to address the evolving needs of the {company['industry'].lower()} sector while ensuring compliance with {compliance['framework']} standards.

The total investment of ${amount:,.2f} covers {product_list} along with comprehensive implementation, training, and support services. Our approach leverages industry best practices and lessons learned from over 200 successful engagements with {company['size'].lower()}-scale organizations.

Strategic Value:
  - Accelerated time-to-value with phased delivery model
  - Risk mitigation through proven implementation methodology
  - Scalable architecture that grows with {company['name']}'s needs
  - Regulatory compliance built into every component

We look forward to partnering with {company['name']} on this transformative initiative.""",
    ]
    return random.choice(variants)


# ─── Dataset Generation ──────────────────────────────────────────

def generate_sample(company, deal, section_name):
    """Generate a single training sample (prompt + completion) for a section."""
    products = deal["products"]
    subtotal = sum(p["quantity"] * p["unit_price"] for p in products)
    region = company["region"]
    compliance = COMPLIANCE[region]

    # Apply some pricing logic
    discount = subtotal * 0.15 if subtotal > 50000 else subtotal * 0.10 if subtotal > 20000 else 0
    tax_rate = {"US": 0.075, "EU": 0.20, "PK": 0.17}.get(region, 0.075)
    tax = (subtotal - discount) * tax_rate
    total = subtotal - discount + tax
    amount = total

    products_text = "\n".join(f"- {p['product']} (Qty: {p['quantity']}, Unit: ${p['unit_price']:,.2f})" for p in products)

    # System prompt
    system_msg = (
        "You are QuoteForge, a professional B2B proposal writer. Generate accurate, "
        "professional proposal content based on the provided deal data. Never fabricate "
        "prices, quantities, or compliance requirements. Use the exact figures provided."
    )

    # User prompt with deal context
    user_msg = (
        f"Generate the {section_name} section for this proposal.\n\n"
        f"Client: {company['name']}\n"
        f"Industry: {company['industry']}\n"
        f"Region: {region}\n"
        f"Company Size: {company['size']}\n"
        f"Deal: {deal['name']}\n"
        f"Products/Services:\n{products_text}\n"
        f"Subtotal: ${subtotal:,.2f}\n"
        f"Discount: ${discount:,.2f}\n"
        f"Tax: ${tax:,.2f}\n"
        f"Total: ${total:,.2f}\n"
        f"Compliance: {compliance['framework']}\n"
    )

    # Generate the section content
    generators = {
        "Cover Letter": lambda: gen_cover_letter(company, deal, amount, region, compliance),
        "Scope": lambda: gen_scope(company, deal, products, region),
        "Pricing": lambda: gen_pricing(company, deal, products, subtotal, discount, tax, total, region),
        "Deliverables": lambda: gen_deliverables(company, deal, products),
        "Terms": lambda: gen_terms(company, deal, region, compliance),
        "Summary": lambda: gen_summary(company, deal, amount, products, region, compliance),
    }

    content = generators[section_name]()

    return {
        "system": system_msg,
        "user": user_msg,
        "assistant": content,
        "metadata": {
            "section": section_name,
            "company": company["name"],
            "deal": deal["name"],
            "region": region,
            "amount": total,
        }
    }


def generate_openai_format(samples):
    """Convert samples to OpenAI fine-tuning JSONL format."""
    entries = []
    for s in samples:
        entries.append({
            "messages": [
                {"role": "system", "content": s["system"]},
                {"role": "user", "content": s["user"]},
                {"role": "assistant", "content": s["assistant"]},
            ]
        })
    return entries


def generate_huggingface_format(samples):
    """Convert samples to Hugging Face instruction format."""
    entries = []
    for s in samples:
        entries.append({
            "instruction": s["system"] + "\n\n" + s["user"],
            "input": "",
            "output": s["assistant"],
            "metadata": s["metadata"],
        })
    return entries


def main():
    print("=" * 60)
    print("QuoteForge Training Data Generator")
    print("=" * 60)

    all_samples = []

    # Generate samples for every combination
    for company in COMPANIES:
        for deal in DEALS:
            for section in SECTIONS:
                sample = generate_sample(company, deal, section)
                all_samples.append(sample)

    random.shuffle(all_samples)
    total = len(all_samples)
    print(f"\nGenerated {total} training samples")
    print(f"  Companies: {len(COMPANIES)}")
    print(f"  Deals: {len(DEALS)}")
    print(f"  Sections: {len(SECTIONS)}")

    # Split: 80% train, 10% validation, 10% test
    train_end = int(total * 0.8)
    val_end = int(total * 0.9)

    train_samples = all_samples[:train_end]
    val_samples = all_samples[train_end:val_end]
    test_samples = all_samples[val_end:]

    print(f"\nSplit: {len(train_samples)} train / {len(val_samples)} validation / {len(test_samples)} test")

    # ─── OpenAI Format ────────────────────────────────────────
    for name, samples in [("train", train_samples), ("val", val_samples), ("test", test_samples)]:
        openai_data = generate_openai_format(samples)
        path = OUTPUT_DIR / f"openai_{name}.jsonl"
        with open(path, "w") as f:
            for entry in openai_data:
                f.write(json.dumps(entry) + "\n")
        print(f"  Written: {path.name} ({len(openai_data)} samples)")

    # ─── Hugging Face Format ──────────────────────────────────
    for name, samples in [("train", train_samples), ("val", val_samples), ("test", test_samples)]:
        hf_data = generate_huggingface_format(samples)
        path = OUTPUT_DIR / f"hf_{name}.jsonl"
        with open(path, "w") as f:
            for entry in hf_data:
                f.write(json.dumps(entry) + "\n")
        print(f"  Written: {path.name} ({len(hf_data)} samples)")

    # ─── Stats ────────────────────────────────────────────────
    section_counts = {}
    region_counts = {}
    for s in all_samples:
        sec = s["metadata"]["section"]
        reg = s["metadata"]["region"]
        section_counts[sec] = section_counts.get(sec, 0) + 1
        region_counts[reg] = region_counts.get(reg, 0) + 1

    print(f"\nSection distribution:")
    for sec, count in sorted(section_counts.items()):
        print(f"  {sec}: {count}")

    print(f"\nRegion distribution:")
    for reg, count in sorted(region_counts.items()):
        print(f"  {reg}: {count}")

    # Token estimate (rough: ~4 chars per token)
    total_chars = sum(len(s["system"]) + len(s["user"]) + len(s["assistant"]) for s in all_samples)
    est_tokens = total_chars // 4
    print(f"\nEstimated total tokens: ~{est_tokens:,}")
    print(f"Estimated fine-tuning cost (GPT-4o-mini): ~${est_tokens * 0.000008:.2f}")

    print(f"\nDone! Files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
