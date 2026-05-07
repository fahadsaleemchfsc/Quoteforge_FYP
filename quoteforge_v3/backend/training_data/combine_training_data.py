"""
Combine synthetic + real client training data into final training sets.

Produces:
  - hf_train_combined.jsonl (for local LoRA)
  - openai_train_combined.jsonl (for OpenAI fine-tune)
"""
import json
import random
import hashlib
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent


def format_real_deal_as_proposal(record: dict) -> list:
    """
    Convert a real Salesforce deal record into instruction-response pairs
    for each proposal section.

    Returns list of {instruction, output} dicts.
    """
    client_name = record["client"]["name"]
    deal_name = record["deal_name"]
    amount = record["deal_amount"]
    deal_type = record["deal_type"] or "New Business"
    line_items = record["line_items"]
    is_won = record["is_won"]

    # Build line items text
    items_text = "\n".join(
        f"- {it['product']} (Qty: {int(it['quantity'])}, ${it['unit_price']:,.2f})"
        for it in line_items[:10]  # Cap at 10 items
    ) if line_items else "Services to be defined"

    # Only use WON or high-probability deals for training (they're the quality signal)
    if not (is_won or record.get("probability", 0) >= 50):
        return []

    # Generate instruction for different sections
    base_context = (
        f"Generate proposal content for this deal.\n\n"
        f"Client: {client_name}\n"
        f"Deal: {deal_name}\n"
        f"Deal Type: {deal_type}\n"
        f"Amount: ${amount:,.2f}\n"
        f"Products/Services:\n{items_text}\n"
    )

    pairs = []

    # Cover Letter
    cover_output = (
        f"Dear {client_name} Team,\n\n"
        f"Thank you for the opportunity to present this {deal_type.lower()} engagement. "
        f"We are pleased to submit this proposal for {deal_name}, "
        f"with a total investment of ${amount:,.2f}.\n\n"
        f"Our solution covers the following scope:\n{items_text}\n\n"
        f"We look forward to partnering with you on this initiative and welcome any questions "
        f"your team may have. Our team is ready to begin upon your approval.\n\n"
        f"Sincerely,\nThe Sales Team"
    )
    pairs.append({
        "instruction": base_context + "\nGenerate the Cover Letter section.",
        "output": cover_output,
    })

    # Pricing
    pricing_output = (
        f"Pricing Summary — {deal_name}\n\n"
        f"Engagement Investment Breakdown:\n{items_text}\n\n"
        f"Total Contract Value: ${amount:,.2f}\n\n"
        f"Payment Terms: Net 30 days from invoice. "
        f"Pricing is valid for 30 days from proposal date. "
        f"All amounts in USD, exclusive of applicable taxes."
    )
    pairs.append({
        "instruction": base_context + "\nGenerate the Pricing Summary section.",
        "output": pricing_output,
    })

    # Scope
    scope_output = (
        f"Scope of Work — {deal_name}\n\n"
        f"Engagement Type: {deal_type}\n\n"
        f"Deliverables:\n{items_text}\n\n"
        f"Timeline: Work commences within 5 business days of contract execution. "
        f"Milestones and reporting cadence to be mutually agreed upon during kickoff.\n\n"
        f"Success Criteria: Clear KPIs documented and tracked. "
        f"Weekly status reviews with designated stakeholders. "
        f"Quarterly business reviews to assess performance and adjust strategy."
    )
    pairs.append({
        "instruction": base_context + "\nGenerate the Scope of Work section.",
        "output": scope_output,
    })

    return pairs


def main():
    print("Combining training data...\n")

    # Load synthetic training data (our 960 samples)
    synthetic = []
    syn_path = OUTPUT_DIR / "hf_train.jsonl"
    if syn_path.exists():
        with open(syn_path) as f:
            synthetic = [json.loads(line) for line in f]
        print(f"Synthetic samples: {len(synthetic):,}")

    # Load real client data (Tier 1)
    real_pairs = []
    real_path = OUTPUT_DIR / "client_tier1_premium.jsonl"
    if real_path.exists():
        with open(real_path) as f:
            for line in f:
                record = json.loads(line)
                pairs = format_real_deal_as_proposal(record)
                real_pairs.extend(pairs)
        print(f"Real client training pairs: {len(real_pairs):,}")
    else:
        print("Real client data not found. Run csv_to_training_data.py first.")

    # Combine
    combined = synthetic + real_pairs
    random.shuffle(combined)
    print(f"\nTotal combined: {len(combined):,}")

    # Split 80/10/10
    n = len(combined)
    train = combined[: int(n * 0.8)]
    val = combined[int(n * 0.8) : int(n * 0.9)]
    test = combined[int(n * 0.9):]

    # Save HF format
    for name, data in [("train", train), ("val", val), ("test", test)]:
        path = OUTPUT_DIR / f"hf_{name}_combined.jsonl"
        with open(path, "w") as f:
            for sample in data:
                f.write(json.dumps(sample, default=str) + "\n")
        print(f"Saved: {path.name} ({len(data):,} samples)")

    # Save OpenAI format
    for name, data in [("train", train), ("val", val)]:
        path = OUTPUT_DIR / f"openai_{name}_combined.jsonl"
        with open(path, "w") as f:
            for sample in data:
                entry = {
                    "messages": [
                        {"role": "system", "content": "You are QuoteForge, a professional B2B proposal writer. Generate accurate, professional proposal content based on the provided deal data."},
                        {"role": "user", "content": sample["instruction"]},
                        {"role": "assistant", "content": sample["output"]},
                    ]
                }
                f.write(json.dumps(entry) + "\n")
        print(f"Saved: {path.name} ({len(data):,} samples)")

    # Show sample
    print("\n" + "=" * 60)
    print("Sample from combined training data:")
    print("=" * 60)
    s = random.choice(combined)
    print(f"\n[INSTRUCTION]\n{s['instruction'][:300]}...")
    print(f"\n[OUTPUT]\n{s['output'][:300]}...")


if __name__ == "__main__":
    main()
