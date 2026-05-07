"""
Enhanced Training Data Generator
==================================
Leverages the REAL 78,428 client records to build high-quality training data.

Instead of pure synthesis, this script:
  1. Reads real deal patterns from client CSV data
  2. Extracts: client names, products, pricing, deal types, industries
  3. Generates realistic proposal sections grounded in these patterns
  4. Produces diverse, non-duplicate training samples

Output: Rich, varied training data that teaches the model to write like
the patterns seen in real business proposals.
"""
import json
import random
import hashlib
from pathlib import Path
from collections import defaultdict, Counter

OUTPUT_DIR = Path(__file__).parent
random.seed(42)


# ═══════════════════════════════════════════════════════════════════
#  LOAD REAL CLIENT PATTERNS
# ═══════════════════════════════════════════════════════════════════

def load_real_patterns():
    """Extract patterns from the 78k real Salesforce records."""
    raw_path = OUTPUT_DIR / "client_real_proposals.jsonl"
    if not raw_path.exists():
        print(f"   ⚠️  {raw_path.name} not found — using defaults")
        return None

    records = []
    with open(raw_path) as f:
        for line in f:
            records.append(json.loads(line))

    # Extract unique patterns
    patterns = {
        "clients": Counter(),
        "products": Counter(),
        "deal_types": Counter(),
        "deal_name_patterns": Counter(),
        "price_tiers": {"small": [], "medium": [], "large": [], "enterprise": []},
        "won_deals": [],
        "line_item_examples": [],
    }

    for r in records:
        client = r["client"]["name"]
        if client and client != "Unknown Account":
            patterns["clients"][client] += 1

        for item in r.get("line_items", []):
            patterns["products"][item["product"]] += 1
            if item["unit_price"] > 0:
                patterns["line_item_examples"].append({
                    "product": item["product"],
                    "quantity": int(item["quantity"]),
                    "unit_price": item["unit_price"],
                })

        if r.get("deal_type"):
            patterns["deal_types"][r["deal_type"]] += 1

        amount = r["deal_amount"]
        if amount > 0:
            if amount < 10000: patterns["price_tiers"]["small"].append(amount)
            elif amount < 50000: patterns["price_tiers"]["medium"].append(amount)
            elif amount < 200000: patterns["price_tiers"]["large"].append(amount)
            else: patterns["price_tiers"]["enterprise"].append(amount)

        if r.get("is_won"):
            patterns["won_deals"].append(r)

    return patterns


# ═══════════════════════════════════════════════════════════════════
#  DIVERSE SECTION GENERATORS
# ═══════════════════════════════════════════════════════════════════

# Multiple variations for each section to prevent duplicates

COVER_LETTER_TEMPLATES = [
    "Dear {client} Team,\n\nWe are pleased to present this {deal_type_lower} proposal for {deal_name}. "
    "After reviewing your requirements in the {industry} sector, we have crafted a solution that directly "
    "addresses your operational needs while adhering to {compliance} standards.\n\n"
    "This engagement represents a total investment of ${total}, carefully structured to deliver measurable "
    "value within your target timeline. Our team brings {years} years of experience working with "
    "{size}-class organizations across {region}.\n\n"
    "Key highlights of this proposal:\n{highlights}\n\n"
    "We look forward to discussing the details and answering any questions your stakeholders may have.\n\n"
    "Best regards,\nThe QuoteForge Team",

    "Dear {contact_salutation},\n\nThank you for the opportunity to submit this proposal for {deal_name}. "
    "{client}'s commitment to {industry_adjective} excellence aligns perfectly with our capabilities, "
    "and we are confident in our ability to deliver exceptional results.\n\n"
    "Our proposed solution, valued at ${total}, encompasses {product_summary}. Every component has been "
    "validated against {compliance} requirements to ensure full regulatory alignment.\n\n"
    "We have structured this engagement to provide {client} with:\n{highlights}\n\n"
    "Our team is available to begin immediately upon your approval. We appreciate your consideration and "
    "look forward to a productive partnership.\n\n"
    "Warm regards,\nQuoteForge Solutions",

    "To the Leadership at {client},\n\nAt QuoteForge, we understand that {industry} organizations operating "
    "in {region} face unique challenges requiring both technical excellence and regulatory compliance. "
    "This proposal for {deal_name} has been designed with these factors as primary considerations.\n\n"
    "Investment: ${total}\nDuration: {timeline}\nCompliance: {compliance}\n\n"
    "{opening_paragraph}\n\n"
    "We welcome the opportunity to present this proposal in person and answer any questions your team may have. "
    "Our technical leads are available for detailed discussions at your convenience.\n\n"
    "Sincerely,\nThe Engagement Team, QuoteForge",

    "Subject: Proposal — {deal_name}\n\nDear {client},\n\n"
    "Following our recent discussions regarding your {industry} requirements, we are pleased to submit this "
    "formal proposal. This engagement addresses the specific scope outlined during our initial consultations, "
    "with the total investment set at ${total}.\n\n"
    "{closing_value_statement}\n\n"
    "We thank you for considering QuoteForge for this important initiative and look forward to advancing "
    "this opportunity together.\n\n"
    "Respectfully,\nQuoteForge Engagement Team",
]

SCOPE_TEMPLATES = [
    """Scope of Work — {deal_name}

1. ENGAGEMENT OBJECTIVES
This engagement delivers {deal_name} to {client}, focusing on measurable outcomes aligned with {industry} industry best practices.

2. KEY DELIVERABLES
{line_items}

3. PROJECT PHASES
  Phase 1 (Weeks 1-2): Discovery, requirements finalization, stakeholder alignment
  Phase 2 (Weeks 3-6): Solution design, architecture review, compliance mapping
  Phase 3 (Weeks 7-10): Implementation, configuration, integration testing
  Phase 4 (Weeks 11-12): UAT, training, production cutover, handover

4. SUCCESS CRITERIA
  - All deliverables accepted by {client} stakeholders
  - {compliance} compliance validated
  - System operational with 99.5% availability
  - End-user training completed with 90%+ satisfaction

5. GOVERNANCE
Weekly status updates with designated project managers from both parties.
Monthly steering committee reviews to ensure strategic alignment.""",

    """SCOPE OF WORK

Project: {deal_name}
Client: {client}
Deal Type: {deal_type}

OVERVIEW
{client} has engaged QuoteForge to provide the following scope of services:

{line_items}

DELIVERY APPROACH
Our delivery methodology emphasizes:
  • Phased execution with clear milestone gates
  • Continuous stakeholder engagement through weekly reviews
  • Risk-based prioritization of critical path activities
  • Comprehensive documentation and knowledge transfer

TIMELINE
Engagement commences within 5 business days of contract execution.
Standard delivery timeline: 8-12 weeks depending on scope complexity.
Final handover includes complete documentation and 30-day warranty support.

ACCEPTANCE CRITERIA
Each deliverable undergoes QuoteForge internal QA before submission.
{client} review period: 5 business days per deliverable.
Formal sign-off required for milestone completion.""",
]

PRICING_TEMPLATES = [
    """Pricing Summary — {deal_name}

INVESTMENT BREAKDOWN
{line_items_detailed}

SUMMARY
  Subtotal:                     ${subtotal}
  Volume Discount:             -${discount}
  Applicable Tax ({tax_rate}%): ${tax}
  ═══════════════════════════════════════
  TOTAL INVESTMENT:             ${total}

PAYMENT SCHEDULE
  30% upon contract execution:    ${payment_1}
  40% upon milestone delivery:    ${payment_2}
  30% upon final acceptance:      ${payment_3}

TERMS
  - Net 30 payment terms
  - Pricing valid for 30 days from proposal date
  - All amounts in USD, exclusive of unstated taxes
  - {compliance} compliance included in base pricing""",

    """FINANCIAL PROPOSAL — {deal_name}

{client} Investment Summary:

{line_items_detailed}

──────────────────────────────
  Line Item Total:     ${subtotal}
  Discount Applied:   (${discount})
  Tax ({tax_rate}%):     ${tax}
──────────────────────────────
  GRAND TOTAL:         ${total}
──────────────────────────────

PAYMENT TERMS
Milestone-based billing with Net 30 payment terms from invoice date.
Early payment discount (2%) available for payment within 10 days.

This pricing reflects our {deal_type_lower} pricing structure and remains valid for 30 days from the proposal date. All applicable compliance certifications ({compliance}) are included without additional cost.""",
]

TERMS_TEMPLATES = {
    "US": """Terms and Conditions — {deal_name}

1. AGREEMENT
This proposal, upon acceptance by {client}, constitutes a binding engagement under the laws of the State of Delaware, USA.

2. PAYMENT
Net 30 days from invoice date. Late payments subject to 1.5% monthly interest.

3. WARRANTY & SUPPORT
12-month warranty on all deliverables. Functional defects remedied at no additional cost during warranty period.

4. INTELLECTUAL PROPERTY
Pre-existing IP remains with respective owners. Custom deliverables become {client} property upon full payment.

5. CONFIDENTIALITY
Both parties maintain strict confidentiality of proprietary information. Obligation survives agreement termination.

6. LIMITATION OF LIABILITY
Aggregate liability capped at total contract value. No liability for indirect or consequential damages.

7. COMPLIANCE
This engagement adheres to SOC 2 Type II trust criteria and GDPR data protection requirements where applicable. A Data Processing Agreement (DPA) is provided as Appendix A.

8. TERMINATION
Either party may terminate with 30 days written notice. {client} shall compensate for work completed to date.""",

    "PK": """Terms and Conditions — {deal_name}

1. AGREEMENT
This proposal, upon acceptance by {client}, constitutes a binding engagement under the laws of the Islamic Republic of Pakistan.

2. PPRA COMPLIANCE
This engagement complies with PPRA Rules 2004 of Pakistan. Transparent pricing documentation and audit trails are maintained.

3. TAX OBLIGATIONS
GST of 17% applies on goods and services per FBR regulations. Withholding tax provisions per Income Tax Ordinance 2001.

4. PAYMENT
Payment terms: Net 30 days from certified invoice. Requires NTN and STRN documentation.

5. WARRANTY
12-month warranty on all deliverables per PPRA procurement standards.

6. DISPUTE RESOLUTION
Jurisdiction of courts in Lahore, Pakistan. Disputes first addressed through good-faith negotiation.

7. INTELLECTUAL PROPERTY
IP ownership transfers to {client} upon full payment.

8. CONFIDENTIALITY
Per PPRA procurement rules, all confidential bid information is protected.

9. TERMINATION
30 days written notice required. Provisions of PPRA Rules 2004 apply.""",

    "EU": """Terms and Conditions — {deal_name}

1. AGREEMENT
This proposal, upon acceptance by {client}, constitutes a binding engagement under EU law.

2. GDPR COMPLIANCE
Processing of personal data complies with Regulation (EU) 2016/679. A Data Processing Agreement is included. Data subjects retain all rights under GDPR.

3. PAYMENT
Net 30 days from invoice. Currency as specified in the commercial section.

4. WARRANTY
12-month warranty on all deliverables per EU Directive 1999/44/EC.

5. DATA PROTECTION
All data processing occurs within EU/EEA jurisdictions or countries with adequacy decisions. Cross-border transfers use Standard Contractual Clauses.

6. INTELLECTUAL PROPERTY
IP provisions follow EU copyright and trade secret directives.

7. TERMINATION
Reasonable notice period applies per EU consumer protection standards.

8. JURISDICTION
Disputes subject to jurisdiction of competent EU member state courts.""",
}

DELIVERABLES_TEMPLATES = [
    """Deliverables — {deal_name}

{line_items_as_deliverables}

DELIVERY STANDARDS
  ✓ Each deliverable includes full documentation
  ✓ Acceptance criteria defined before work commences
  ✓ Five business days review window per deliverable
  ✓ Revisions addressed within three business days

ACCEPTANCE PROCESS
1. QuoteForge submits deliverable with completion notice
2. {client} conducts review against acceptance criteria
3. Feedback provided in writing within review window
4. Minor revisions addressed, final sign-off obtained
5. Milestone invoice issued upon acceptance""",

    """DELIVERABLES REGISTER

{line_items_as_deliverables}

QUALITY ASSURANCE
Each deliverable undergoes three-stage internal review:
  Stage 1: Technical validation
  Stage 2: Compliance review ({compliance})
  Stage 3: Client-ready formatting

HANDOVER PACKAGE
Final delivery includes:
  • All artifacts in agreed formats
  • Technical documentation
  • Training materials
  • 30-day post-delivery support window
  • Transition to steady-state support""",
]

SUMMARY_TEMPLATES = [
    """EXECUTIVE SUMMARY

{client} is seeking a comprehensive solution for {deal_name} that addresses their operational requirements in the {industry} sector while maintaining compliance with {compliance} standards.

Our proposal delivers:
{highlights}

Investment: ${total}
Timeline: {timeline}
Outcome: Measurable business impact within the first {value_months} months post-implementation.

This engagement represents a strategic partnership between {client} and QuoteForge, built on our proven methodology and {industry}-specific expertise. We are confident in our ability to deliver exceptional value and look forward to the opportunity to serve {client}'s evolving needs.""",

    """Executive Summary — {deal_name}

OPPORTUNITY
{client} requires a {deal_type_lower} solution to strengthen operations within the {industry} market. Key priorities include operational efficiency, regulatory compliance ({compliance}), and measurable ROI.

OUR SOLUTION
QuoteForge proposes a ${total} engagement comprising {product_summary}. Our approach leverages proven methodologies refined across {precedent_count}+ similar engagements with {size}-class organizations.

VALUE PROPOSITION
  • Accelerated time-to-value through phased delivery
  • Risk mitigation via proven implementation frameworks
  • Scalable architecture supporting {client}'s growth
  • Full regulatory alignment ({compliance}) built-in

We are committed to delivering exceptional value and building a long-term partnership.""",
]


# ═══════════════════════════════════════════════════════════════════
#  SAMPLE GENERATION
# ═══════════════════════════════════════════════════════════════════

def pick_from_patterns(patterns, key, default):
    """Pick a random item from real patterns, fall back to default."""
    if patterns and patterns.get(key):
        items = list(patterns[key].keys()) if hasattr(patterns[key], "keys") else patterns[key]
        return random.choice(items) if items else random.choice(default)
    return random.choice(default)


def build_sample(patterns=None, section="cover_letter", idx=0):
    """Build a single diverse training sample."""

    # Choose real data when possible
    default_clients = ["Acme Corporation", "TechStart Inc", "Global Solutions LLC", "Vertex Systems",
                       "Nexus Technologies", "Pinnacle Services", "Quantum Dynamics", "Apex Holdings"]
    default_products = ["Enterprise Platform License", "Implementation Services", "Support & Maintenance",
                        "Professional Services", "SaaS Subscription", "Cloud Migration", "Training Program"]
    default_deal_types = ["New Business", "Renewal", "Existing Client - Additional Opportunity",
                          "New Business Expansion", "Renewal and Increase"]

    client = pick_from_patterns(patterns, "clients", default_clients)
    deal_type = pick_from_patterns(patterns, "deal_types", default_deal_types)

    # Industries & regions
    industries = ["Manufacturing", "SaaS Technology", "Healthcare", "Financial Services",
                  "Government", "Retail", "Logistics", "Education Technology", "Biotechnology"]
    industry = random.choice(industries)
    region = random.choices(["US", "EU", "PK"], weights=[50, 30, 20])[0]
    size = random.choice(["Enterprise", "Mid-Market", "SMB"])

    # Compliance by region
    compliance_map = {"US": "SOC 2, GDPR", "EU": "GDPR", "PK": "PPRA"}
    compliance = compliance_map[region]

    # Line items — use real patterns when available
    num_items = random.randint(2, 5)
    line_items = []
    if patterns and patterns.get("line_item_examples"):
        sampled = random.sample(
            patterns["line_item_examples"],
            min(num_items, len(patterns["line_item_examples"]))
        )
        line_items = [{"product": s["product"], "quantity": s["quantity"],
                       "unit_price": s["unit_price"]} for s in sampled]
    else:
        # Fallback
        for _ in range(num_items):
            line_items.append({
                "product": random.choice(default_products),
                "quantity": random.randint(1, 10),
                "unit_price": random.choice([5000, 10000, 15000, 25000, 50000, 100000]),
            })

    # Pricing calculations
    subtotal = sum(li["quantity"] * li["unit_price"] for li in line_items)
    discount_rate = 0.15 if subtotal > 50000 else 0.10 if subtotal > 25000 else 0.05
    discount = subtotal * discount_rate
    tax_rates = {"US": 0.075, "EU": 0.20, "PK": 0.17}
    tax_rate = tax_rates[region]
    tax = (subtotal - discount) * tax_rate
    total = subtotal - discount + tax

    # Deal name
    deal_name = f"{client} {random.choice(['Platform', 'Services', 'Engagement', 'Initiative', 'Partnership'])} - {deal_type}"

    # Format line items text in multiple ways
    line_items_text = "\n".join(
        f"  • {li['product']}: Qty {li['quantity']} × ${li['unit_price']:,.2f} = ${li['quantity']*li['unit_price']:,.2f}"
        for li in line_items
    )
    line_items_detailed = "\n".join(
        f"  {li['product']:.<60} {li['quantity']:>3} × ${li['unit_price']:>10,.2f}  ${li['quantity']*li['unit_price']:>12,.2f}"
        for li in line_items
    )
    line_items_as_deliverables = "\n\n".join(
        f"{i+1}. {li['product']}\n   Quantity: {li['quantity']}\n   Value: ${li['quantity']*li['unit_price']:,.2f}\n"
        f"   Acceptance: Functional validation and stakeholder sign-off required"
        for i, li in enumerate(line_items)
    )
    product_summary = ", ".join(li["product"] for li in line_items[:3])

    highlights = "\n".join(
        f"  • {h}" for h in random.sample([
            f"Delivery within {random.randint(8,16)} weeks",
            f"{compliance} compliance built-in",
            f"Dedicated project management",
            f"12-month warranty on deliverables",
            f"Post-implementation support",
            f"Quarterly business reviews",
            f"Risk-based phased approach",
        ], 4)
    )

    # Common context
    ctx = {
        "client": client,
        "deal_name": deal_name,
        "deal_type": deal_type,
        "deal_type_lower": deal_type.lower(),
        "industry": industry,
        "industry_adjective": random.choice(["operational", "strategic", "digital", "technical"]),
        "region": region,
        "size": size,
        "compliance": compliance,
        "total": f"{total:,.2f}",
        "subtotal": f"{subtotal:,.2f}",
        "discount": f"{discount:,.2f}",
        "tax": f"{tax:,.2f}",
        "tax_rate": f"{tax_rate*100:.1f}",
        "payment_1": f"{total*0.3:,.2f}",
        "payment_2": f"{total*0.4:,.2f}",
        "payment_3": f"{total*0.3:,.2f}",
        "line_items": line_items_text,
        "line_items_detailed": line_items_detailed,
        "line_items_as_deliverables": line_items_as_deliverables,
        "product_summary": product_summary,
        "highlights": highlights,
        "timeline": f"{random.randint(8,16)} weeks",
        "years": random.choice([5, 7, 10, 12, 15]),
        "contact_salutation": random.choice(["Sir/Madam", f"{client} Leadership Team", "Team"]),
        "opening_paragraph": f"Our solution delivers measurable value through proven methodologies refined across hundreds of engagements.",
        "closing_value_statement": f"We are confident this proposal reflects the depth of analysis and care that {client} deserves.",
        "value_months": random.choice([3, 6, 12]),
        "precedent_count": random.choice([100, 150, 200, 250]),
    }

    # Generate instruction (user prompt)
    instruction = (
        f"Generate the {section.replace('_', ' ').title()} section for this proposal.\n\n"
        f"Client: {client}\n"
        f"Industry: {industry}\n"
        f"Region: {region}\n"
        f"Company Size: {size}\n"
        f"Deal: {deal_name}\n"
        f"Deal Type: {deal_type}\n"
        f"Amount: ${total:,.2f}\n"
        f"Line Items:\n{line_items_text}\n"
        f"Compliance: {compliance}"
    )

    # Select template (round-robin to ensure diversity)
    template_map = {
        "cover_letter": COVER_LETTER_TEMPLATES,
        "scope": SCOPE_TEMPLATES,
        "pricing": PRICING_TEMPLATES,
        "terms": [TERMS_TEMPLATES[region]],
        "deliverables": DELIVERABLES_TEMPLATES,
        "summary": SUMMARY_TEMPLATES,
    }

    templates = template_map.get(section, COVER_LETTER_TEMPLATES)
    template = templates[idx % len(templates)]

    try:
        output = template.format(**ctx)
    except KeyError as e:
        output = template  # Skip malformed templates

    return {
        "instruction": instruction,
        "output": output,
        "metadata": {
            "section": section,
            "region": region,
            "industry": industry,
            "size": size,
            "amount": total,
            "has_real_patterns": patterns is not None,
        },
    }


def main(num_per_section: int = 500):
    print("=" * 70)
    print(" QuoteForge Enhanced Training Data Generator")
    print("=" * 70)

    print("\n[1/3] Loading real patterns from 78,428 client records...")
    patterns = load_real_patterns()
    if patterns:
        print(f"      ✓ Real clients:    {len(patterns['clients']):,}")
        print(f"      ✓ Real products:   {len(patterns['products']):,}")
        print(f"      ✓ Real line items: {len(patterns['line_item_examples']):,}")
        print(f"      ✓ Real deal types: {len(patterns['deal_types']):,}")
        print(f"      ✓ Won deals:       {len(patterns['won_deals']):,}")

    print(f"\n[2/3] Generating {num_per_section} samples per section...")
    sections = ["cover_letter", "scope", "pricing", "deliverables", "terms", "summary"]

    all_samples = []
    for section in sections:
        for i in range(num_per_section):
            sample = build_sample(patterns, section, i)
            all_samples.append(sample)
        print(f"      ✓ {section}: {num_per_section} samples")

    random.shuffle(all_samples)
    print(f"\n      Total samples: {len(all_samples):,}")

    # Split
    n = len(all_samples)
    train = all_samples[: int(n * 0.8)]
    val = all_samples[int(n * 0.8) : int(n * 0.9)]
    test = all_samples[int(n * 0.9):]

    print(f"\n[3/3] Saving splits...")
    for name, data in [("train", train), ("val", val), ("test", test)]:
        path = OUTPUT_DIR / f"hf_{name}_enhanced.jsonl"
        with open(path, "w") as f:
            for sample in data:
                f.write(json.dumps(sample, default=str) + "\n")
        print(f"      ✓ {path.name}: {len(data):,} samples")

    print("\n" + "=" * 70)
    print(" ENHANCED DATASET READY")
    print("=" * 70)
    print(f"\n  Run cleaning:    python training_data/data_cleaning_pipeline.py \\")
    print(f"                          --input training_data/hf_train_enhanced.jsonl \\")
    print(f"                          --output training_data/hf_train_final.jsonl")
    print(f"  Then convert:    python training_data/combine_training_data.py")
    print(f"  Then retrain:    python model_training/scripts/train_mlx.py")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-section", type=int, default=500)
    args = parser.parse_args()
    main(args.samples_per_section)
