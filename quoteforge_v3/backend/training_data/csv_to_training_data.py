"""
Convert Salesforce CSV Report exports into QuoteForge training data.

Usage:
  python csv_to_training_data.py --input report.csv --output client_proposals.jsonl
  python csv_to_training_data.py --input report.csv --anonymize
"""
import argparse
import csv
import json
import re
import hashlib
from pathlib import Path
from collections import defaultdict

OUTPUT_DIR = Path(__file__).parent


def anonymize_value(val: str, prefix: str = "ENTITY") -> str:
    """Replace a value with a hash-based placeholder."""
    if not val:
        return val
    h = hashlib.md5(val.encode()).hexdigest()[:6].upper()
    return f"[{prefix}_{h}]"


def clean_number(val: str) -> float:
    """Parse a number from CSV (handles $, commas, etc.)."""
    if not val:
        return 0.0
    cleaned = re.sub(r'[^\d.\-]', '', val.replace(',', ''))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def determine_region(country: str) -> str:
    if not country:
        return "US"
    c = country.upper().strip()
    if c in ("PAKISTAN", "PK"):
        return "PK"
    eu_countries = {"GERMANY", "FRANCE", "ITALY", "SPAIN", "UK", "UNITED KINGDOM",
                    "NETHERLANDS", "BELGIUM", "SWEDEN", "POLAND", "GB", "DE", "FR"}
    if c in eu_countries:
        return "EU"
    return "US"


def determine_size(revenue: float, employees: int) -> str:
    if revenue > 100_000_000 or employees > 1000:
        return "Enterprise"
    if revenue > 10_000_000 or employees > 100:
        return "Mid-Market"
    return "SMB"


def process_csv(input_path: str, output_path: str, anonymize: bool = False, min_amount: float = 0):
    """
    Read Salesforce CSV report, group by Opportunity, and emit training records.

    CSV structure (from client export):
      - Rows are product line items with opportunity info duplicated
      - Group by Opportunity Name + Close Date to reconstruct deals
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    print(f"Reading: {input_path}")
    print(f"File size: {input_path.stat().st_size / 1e6:.1f} MB")

    # Group rows by Opportunity (columns: OppOwner|OppName|Close Date|... + product row)
    opportunities = defaultdict(lambda: {"line_items": []})

    total_rows = 0
    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1

            opp_name = (row.get("Opportunity Name") or "").strip()
            close_date = (row.get("Close Date") or "").strip()
            if not opp_name:
                continue

            # Unique opportunity key
            opp_key = f"{opp_name}|{close_date}|{row.get('Opportunity Owner', '')}"

            opp = opportunities[opp_key]

            # Fill opportunity-level fields (from first row encountered)
            if "opp_name" not in opp:
                amount = clean_number(row.get("Amount", "0"))
                stage = (row.get("Stage") or "").strip()

                # Won/Lost detection from stage name
                stage_lower = stage.lower()
                is_won = "won" in stage_lower or "closed won" in stage_lower
                is_lost = "lost" in stage_lower or "canceled" in stage_lower or "cancelled" in stage_lower
                is_closed = is_won or is_lost

                opp.update({
                    "opp_name": opp_name,
                    "owner": (row.get("Opportunity Owner") or "").strip(),
                    "owner_role": (row.get("Owner Role") or "").strip(),
                    "type": (row.get("Type") or "").strip(),
                    "amount": amount,
                    "close_date": close_date,
                    "created_date": (row.get("Created Date") or "").strip(),
                    "stage": stage,
                    "probability": clean_number(row.get("Probability (%)", "0")),
                    "is_won": is_won,
                    "is_lost": is_lost,
                    "is_closed": is_closed,
                    "account_name": (row.get("Account Name") or "").strip(),
                })

            # Add line item if present
            product_name = (row.get("Product Name") or "").strip()
            if product_name:
                opp["line_items"].append({
                    "product": product_name,
                    "description": (row.get("Product Description") or "").strip(),
                    "code": (row.get("Product Code") or "").strip(),
                    "quantity": clean_number(row.get("Quantity", "1")) or 1,
                    "unit_price": clean_number(row.get("Sales Price", "0")),
                    "list_price": clean_number(row.get("List Price", "0")),
                    "total_price": clean_number(row.get("Total Price", "0")),
                    "product_date": (row.get("Product Date") or "").strip(),
                    "active": row.get("Active Product", "0") == "1",
                })

    print(f"Total CSV rows: {total_rows:,}")
    print(f"Unique opportunities: {len(opportunities):,}")

    # Build training records
    training_records = []
    stats = {
        "won": 0, "lost": 0, "open": 0,
        "with_products": 0, "no_account": 0,
        "high_value": 0, "skipped_low_value": 0,
    }

    for opp_key, opp in opportunities.items():
        if "opp_name" not in opp:
            continue

        amount = opp["amount"]

        # Apply minimum amount filter
        if amount < min_amount:
            stats["skipped_low_value"] += 1
            continue

        # Deduplicate line items by product
        line_items_seen = {}
        for item in opp["line_items"]:
            key = item["product"]
            if key not in line_items_seen:
                line_items_seen[key] = item
            else:
                # Aggregate quantities for duplicate products
                line_items_seen[key]["quantity"] += item["quantity"]
                line_items_seen[key]["total_price"] += item["total_price"]

        line_items = list(line_items_seen.values())

        # If amount is 0 but line items exist, sum them
        if amount == 0 and line_items:
            amount = sum(li["total_price"] for li in line_items)

        # Stats
        if opp["is_won"]:
            stats["won"] += 1
        elif opp["is_lost"]:
            stats["lost"] += 1
        else:
            stats["open"] += 1
        if line_items:
            stats["with_products"] += 1
        if not opp["account_name"]:
            stats["no_account"] += 1
        if amount > 50000:
            stats["high_value"] += 1

        account_name = opp["account_name"] or "Unknown Account"
        opp_name = opp["opp_name"]
        owner = opp["owner"]

        if anonymize:
            account_name = anonymize_value(account_name, "CLIENT")
            opp_name = anonymize_value(opp_name, "DEAL")
            owner = anonymize_value(owner, "REP")

        record = {
            "deal_id": hashlib.md5(opp_key.encode()).hexdigest()[:18],
            "deal_name": opp_name,
            "deal_amount": round(amount, 2),
            "deal_type": opp["type"],
            "stage": opp["stage"],
            "close_date": opp["close_date"],
            "created_date": opp["created_date"],
            "probability": opp["probability"],
            "is_won": opp["is_won"],
            "is_lost": opp["is_lost"],
            "is_closed": opp["is_closed"],
            "owner": owner,
            "owner_role": opp["owner_role"],
            "client": {
                "name": account_name,
                "region": "US",  # Could be enhanced with billing country
            },
            "line_items": line_items,
            "line_item_count": len(line_items),
            "source": "salesforce_csv_export",
        }

        training_records.append(record)

    # Sort: closed first (more useful), then by amount descending
    training_records.sort(key=lambda r: (not r["is_closed"], -r["deal_amount"]))

    # Write JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for record in training_records:
            f.write(json.dumps(record, default=str) + "\n")

    print("\n" + "=" * 60)
    print(f"✅ Saved {len(training_records):,} training records")
    print(f"✅ File: {output_path}")
    print(f"\nBreakdown:")
    print(f"   Won deals:              {stats['won']:,}")
    print(f"   Lost/Canceled deals:    {stats['lost']:,}")
    print(f"   Open/In-progress:       {stats['open']:,}")
    print(f"   With product line items:{stats['with_products']:,}")
    print(f"   High value (>$50K):     {stats['high_value']:,}")
    print(f"   No account name:        {stats['no_account']:,}")
    if min_amount > 0:
        print(f"   Skipped (below ${min_amount:,.0f}): {stats['skipped_low_value']:,}")

    # Show top 5 biggest deals
    print(f"\nTop 5 deals by amount:")
    for r in training_records[:5]:
        won_marker = "✅" if r["is_won"] else ("❌" if r["is_lost"] else "🔄")
        print(f"   {won_marker} ${r['deal_amount']:>12,.2f}  {r['deal_name'][:50]}")

    # Show sample industries/types
    types = defaultdict(int)
    for r in training_records:
        if r["deal_type"]:
            types[r["deal_type"]] += 1
    if types:
        print(f"\nDeal types:")
        for t, c in sorted(types.items(), key=lambda x: -x[1])[:10]:
            print(f"   {t}: {c:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to Salesforce CSV export")
    parser.add_argument("--output", default=None, help="Output JSONL path")
    parser.add_argument("--anonymize", action="store_true", help="Replace client names with hash placeholders")
    parser.add_argument("--min-amount", type=float, default=0, help="Skip deals below this amount")
    args = parser.parse_args()

    output = args.output or str(OUTPUT_DIR / "client_real_proposals.jsonl")
    process_csv(args.input, output, args.anonymize, args.min_amount)
