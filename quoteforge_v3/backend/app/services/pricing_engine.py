"""
Rules & Pricing Engine — applies discount thresholds, tax calculations,
and region-specific compliance clause selection.
"""
import json
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.pricing_rule import PricingRule


# Compliance clause text
COMPLIANCE_CLAUSES = {
    "SOC 2": (
        "This engagement is subject to SOC 2 Type II compliance requirements. "
        "All data handling will adhere to the Trust Services Criteria for Security, "
        "Availability, Processing Integrity, Confidentiality, and Privacy."
    ),
    "GDPR": (
        "Processing of personal data under this agreement shall comply with the "
        "General Data Protection Regulation (EU) 2016/679. A Data Processing "
        "Agreement (DPA) is included as an addendum."
    ),
    "PPRA": (
        "This proposal complies with the Public Procurement Regulatory Authority "
        "(PPRA) Rules, 2004 of Pakistan. Transparent pricing and competitive "
        "bidding documentation are provided as required."
    ),
}


def _parse_amount_condition(condition: str) -> float:
    """Extract dollar amount from conditions like 'Deal > $50K'."""
    match = re.search(r'\$?([\d,.]+)\s*[kK]?', condition)
    if match:
        val = float(match.group(1).replace(",", ""))
        if "k" in condition.lower() or "K" in condition:
            val *= 1000
        return val
    return 0


def _parse_qty_condition(condition: str) -> int:
    """Extract quantity from conditions like 'Qty > 100'."""
    match = re.search(r'(\d+)', condition)
    return int(match.group(1)) if match else 0


def _parse_percentage(value: str) -> float:
    """Extract percentage from strings like '10%' or '17%'."""
    match = re.search(r'([\d.]+)%', value)
    return float(match.group(1)) / 100 if match else 0


async def apply_pricing_rules(
    db: AsyncSession,
    deal_amount: float,
    region: str,
    line_items: list,
) -> dict:
    """
    Apply all active pricing rules to compute final pricing.
    Returns: {subtotal, discount, discount_details, tax, tax_details, compliance_clauses, total}
    """
    result = await db.execute(
        select(PricingRule).where(PricingRule.status == "active")
    )
    rules = result.scalars().all()

    total_qty = sum(item.get("quantity", 1) if isinstance(item, dict) else 1 for item in line_items)
    subtotal = deal_amount

    discount = 0.0
    discount_details = []
    tax = 0.0
    tax_details = []
    compliance_clauses = []

    for rule in rules:
        rule_region = rule.region.upper() if rule.region else "GLOBAL"
        deal_region = region.upper()

        # Check region match
        region_match = (
            rule_region == "GLOBAL"
            or deal_region in rule_region
            or rule_region in deal_region
        )

        if rule.type == "Discount" and region_match:
            apply = False
            cond = rule.condition.lower()

            if "qty" in cond or "quantity" in cond:
                threshold = _parse_qty_condition(rule.condition)
                apply = total_qty > threshold
            elif "deal" in cond or "$" in cond:
                threshold = _parse_amount_condition(rule.condition)
                apply = subtotal > threshold
            else:
                apply = True  # unconditional discount

            if apply:
                pct = _parse_percentage(rule.value)
                disc_amount = subtotal * pct
                discount += disc_amount
                discount_details.append({
                    "rule": rule.name,
                    "percentage": rule.value,
                    "amount": disc_amount,
                })

        elif rule.type == "Tax" and region_match:
            if rule.value.lower() == "variable":
                # Default US sales tax estimate
                tax_rate = 0.075
            else:
                tax_rate = _parse_percentage(rule.value)

            taxable = subtotal - discount
            tax_amount = taxable * tax_rate
            tax += tax_amount
            tax_details.append({
                "rule": rule.name,
                "rate": f"{tax_rate*100:.1f}%",
                "amount": tax_amount,
            })

        elif rule.type == "Compliance" and region_match:
            cond = rule.condition.lower()
            if "always" in cond or deal_region in cond.upper() or "region" in cond:
                clause_text = COMPLIANCE_CLAUSES.get(rule.name.split()[0], rule.name)
                compliance_clauses.append({
                    "rule": rule.name,
                    "clause": clause_text,
                })

    total = subtotal - discount + tax

    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "discount_details": discount_details,
        "tax": round(tax, 2),
        "tax_details": tax_details,
        "compliance_clauses": compliance_clauses,
        "compliance_framework": ", ".join(c["rule"] for c in compliance_clauses),
        "total": round(total, 2),
    }
