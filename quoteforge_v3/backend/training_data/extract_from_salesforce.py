"""
Salesforce Training Data Extractor
====================================
Pulls historical proposals/quotes from a Salesforce org and saves them
as training data for fine-tuning QuoteForge's model.

Usage:
  python extract_from_salesforce.py --connection-id 1 --output client_proposals.jsonl
  python extract_from_salesforce.py --connection-id 1 --anonymize
"""
import asyncio
import json
import argparse
import re
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import async_session
from app.services.salesforce_connector import get_salesforce_client

OUTPUT_DIR = Path(__file__).parent


async def extract_all_training_data(connection_id: int = None, anonymize: bool = False):
    """Extract all historical proposal data from Salesforce."""

    async with async_session() as db:
        sf = await get_salesforce_client(db, connection_id)
        if not sf:
            print("ERROR: No active Salesforce connection")
            return

        print("Extracting training data from Salesforce...")
        print("=" * 60)

        # ─── Query 1: Historical Opportunities ────────────────
        print("\n[1/4] Fetching historical Opportunities...")
        opps_query = (
            "SELECT Id, Name, Amount, StageName, CloseDate, Type, "
            "LeadSource, Description, IsWon, IsClosed, "
            "Account.Name, Account.Industry, Account.BillingCountry, "
            "Account.BillingState, Account.AnnualRevenue, "
            "Account.NumberOfEmployees, "
            "(SELECT Id, Product2.Name, Product2.Family, Product2.Description, "
            "Quantity, UnitPrice, TotalPrice "
            "FROM OpportunityLineItems) "
            "FROM Opportunity "
            "ORDER BY CloseDate DESC "
            "LIMIT 500"
        )
        opportunities = await sf._query(opps_query)
        print(f"    Found {len(opportunities)} historical opportunities")

        # ─── Query 2: Contact Roles ───────────────────────────
        print("\n[2/4] Fetching primary contacts...")
        contacts_map = {}
        if opportunities:
            opp_ids = [f"'{o['Id']}'" for o in opportunities[:200]]
            if opp_ids:
                contacts_query = f"""
                    SELECT OpportunityId, Role, IsPrimary,
                           Contact.Name, Contact.Title, Contact.Email,
                           Contact.Department, Contact.Salutation
                    FROM OpportunityContactRole
                    WHERE OpportunityId IN ({','.join(opp_ids)})
                """
                try:
                    contacts = await sf._query(contacts_query)
                    for c in contacts:
                        if c.get("IsPrimary"):
                            contacts_map[c["OpportunityId"]] = c
                    print(f"    Found {len(contacts_map)} primary contacts")
                except Exception as e:
                    print(f"    Could not fetch contacts: {e}")

        # ─── Query 3: Product Catalog ─────────────────────────
        print("\n[3/4] Fetching product catalog...")
        products_query = """
            SELECT Id, Name, ProductCode, Description, Family, IsActive
            FROM Product2
            WHERE IsActive = true
            LIMIT 200
        """
        try:
            products = await sf._query(products_query)
            print(f"    Found {len(products)} products")
            products_file = OUTPUT_DIR / "sf_products.json"
            products_file.write_text(json.dumps(products, indent=2, default=str))
            print(f"    Saved: {products_file.name}")
        except Exception as e:
            print(f"    Could not fetch products: {e}")

        # ─── Query 4: Attached Documents ──────────────────────
        print("\n[4/4] Checking for attached proposal documents...")
        docs_query = """
            SELECT LinkedEntityId, ContentDocument.Title,
                   ContentDocument.FileExtension, ContentDocument.ContentSize
            FROM ContentDocumentLink
            WHERE LinkedEntity.Type = 'Opportunity'
                AND (ContentDocument.FileExtension = 'pdf'
                     OR ContentDocument.FileExtension = 'docx')
            LIMIT 500
        """
        try:
            docs = await sf._query(docs_query)
            docs_map = {}
            for d in docs:
                opp_id = d.get("LinkedEntityId")
                if opp_id not in docs_map:
                    docs_map[opp_id] = []
                docs_map[opp_id].append({
                    "title": d.get("ContentDocument", {}).get("Title"),
                    "ext": d.get("ContentDocument", {}).get("FileExtension"),
                })
            print(f"    Found {sum(len(v) for v in docs_map.values())} attached documents on {len(docs_map)} opps")
        except Exception as e:
            print(f"    Could not fetch documents: {e}")
            docs_map = {}

        # ─── Build Training Records ───────────────────────────
        print("\n" + "=" * 60)
        print("Building training records...")

        training_records = []
        for opp in opportunities:
            account = opp.get("Account") or {}
            contact = contacts_map.get(opp["Id"], {}).get("Contact") or {}

            # Line items
            line_items = []
            oli = opp.get("OpportunityLineItems")
            if oli and isinstance(oli, dict):
                for item in oli.get("records", []):
                    product = item.get("Product2") or {}
                    line_items.append({
                        "product": product.get("Name", "Product"),
                        "family": product.get("Family", ""),
                        "description": product.get("Description", ""),
                        "quantity": float(item.get("Quantity", 1)),
                        "unit_price": float(item.get("UnitPrice", 0)),
                        "total_price": float(item.get("TotalPrice", 0)),
                        "discount": float(item.get("Discount", 0) or 0),
                    })

            # Determine region
            country = (account.get("BillingCountry") or "").upper()
            region = "US"
            if country in ("PAKISTAN", "PK"):
                region = "PK"
            elif country in ("GERMANY", "FRANCE", "UK", "UNITED KINGDOM", "ITALY", "SPAIN"):
                region = "EU"

            # Determine company size
            employees = account.get("NumberOfEmployees") or 0
            revenue = account.get("AnnualRevenue") or 0
            if employees > 1000 or revenue > 100_000_000:
                size = "Enterprise"
            elif employees > 100 or revenue > 10_000_000:
                size = "Mid-Market"
            else:
                size = "SMB"

            record = {
                "deal_id": opp["Id"],
                "deal_name": opp.get("Name", ""),
                "deal_amount": float(opp.get("Amount", 0) or 0),
                "stage": opp.get("StageName", ""),
                "close_date": opp.get("CloseDate", ""),
                "is_won": opp.get("IsWon", False),
                "deal_type": opp.get("Type", ""),
                "lead_source": opp.get("LeadSource", ""),
                "description": opp.get("Description", ""),
                "client": {
                    "name": account.get("Name", ""),
                    "industry": account.get("Industry", ""),
                    "country": account.get("BillingCountry", ""),
                    "state": account.get("BillingState", ""),
                    "annual_revenue": account.get("AnnualRevenue"),
                    "employees": account.get("NumberOfEmployees"),
                    "size": size,
                    "region": region,
                },
                "primary_contact": {
                    "name": contact.get("Name", ""),
                    "title": contact.get("Title", ""),
                    "email": contact.get("Email", ""),
                    "department": contact.get("Department", ""),
                    "salutation": contact.get("Salutation", ""),
                },
                "line_items": line_items,
                "attached_documents": docs_map.get(opp["Id"], []),
            }

            if anonymize:
                record = anonymize_record(record)

            training_records.append(record)

        # ─── Save ─────────────────────────────────────────────
        output_file = OUTPUT_DIR / ("sf_client_proposals_anon.jsonl" if anonymize else "sf_client_proposals.jsonl")
        with open(output_file, "w") as f:
            for record in training_records:
                f.write(json.dumps(record, default=str) + "\n")

        print(f"\n✅ Saved {len(training_records)} training records")
        print(f"✅ File: {output_file}")
        print(f"\nStats:")
        print(f"   Won deals: {sum(1 for r in training_records if r['is_won'])}")
        print(f"   Lost deals: {sum(1 for r in training_records if not r['is_won'])}")
        print(f"   With line items: {sum(1 for r in training_records if r['line_items'])}")
        print(f"   With contacts: {sum(1 for r in training_records if r['primary_contact']['name'])}")
        print(f"   With attached docs: {sum(1 for r in training_records if r['attached_documents'])}")

        print("\nNext steps:")
        print("  1. Review the JSONL file for quality")
        print("  2. Combine with other training data")
        print("  3. Re-run generate_training_data.py to format for fine-tuning")
        print("  4. Fine-tune your model with the new data")


def anonymize_record(record: dict) -> dict:
    """Strip PII — replace names/emails with placeholders."""
    record["client"]["name"] = f"[CLIENT_{record['deal_id'][-4:]}]"
    if record.get("primary_contact"):
        record["primary_contact"]["name"] = "[CONTACT]"
        record["primary_contact"]["email"] = "[EMAIL]"
    record["deal_name"] = re.sub(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[NAME]", record.get("deal_name", ""))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract training data from Salesforce")
    parser.add_argument("--connection-id", type=int, default=None,
                        help="CRM connection ID (default: first active Salesforce)")
    parser.add_argument("--anonymize", action="store_true",
                        help="Remove PII (names, emails) from output")
    args = parser.parse_args()

    asyncio.run(extract_all_training_data(
        connection_id=args.connection_id,
        anonymize=args.anonymize,
    ))
