#!/usr/bin/env python3
"""
Training-data pipeline for QuoteForge-V3 (Negotiation).

Reads historical closed-won deals and emits JSONL in the prompt/completion
layout `NegotiationService` uses at inference time. Keep the serialization
format here in lock-step with `app/gateway/negotiation/prompt.py`.

Two input sources are supported:

  --source seeded   — read DocumentLog rows from the seeded SQLite DB.
                      Useful for smoke-testing this pipeline itself; the
                      synthesized dataset is tiny (<10 examples) with the
                      demo seed.

  --source csv --csv-path <path>
                    — read a CSV export of real Salesforce deals. Expected
                      columns are described in the CSV_SCHEMA constant below.

Outputs:
  models/quoteforge-v3/data/train.jsonl
  models/quoteforge-v3/data/valid.jsonl
  models/quoteforge-v3/data/dataset_stats.json    — attrition + counts

Attrition is logged at every filter step; V2 training dropped 78,428 → 2,010,
so we expect similar pruning here.

Usage:
  ./venv/bin/python training/prepare_negotiation_dataset.py --source seeded
  ./venv/bin/python training/prepare_negotiation_dataset.py --source csv \\
      --csv-path ~/Downloads/sf_closed_won.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session         # noqa: E402
from app.gateway.negotiation.prompt import SYSTEM_INSTRUCTION   # noqa: E402
from app.models.document_log import DocumentLog     # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prepare_negotiation_dataset")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models" / "quoteforge-v3" / "data"

# CSV columns expected. The real Salesforce export names vary by org; adjust
# the CSV_ALIASES map if your column names differ.
CSV_SCHEMA = {
    "account_name", "deal_name", "billing_country", "amount",
    "probability", "stage", "close_date",
    # Per-line: a JSON-encoded string column is the simplest way to roundtrip
    # Salesforce line items through CSV without exploding the schema.
    "line_items_json",
}
CSV_ALIASES = {
    "accountName": "account_name",
    "opportunityName": "deal_name",
    "country": "billing_country",
    "totalAmount": "amount",
}


@dataclass(frozen=True)
class Example:
    """One (input, output) training pair."""
    input_json: dict[str, Any]
    output_json: dict[str, Any]

    def to_jsonl_line(self) -> str:
        # MLX fine-tune accepts a "text" field with the full prompt+completion
        # concatenated. Match the inference-time format in prompt.py exactly.
        prompt = (
            f"<|system|>\n{SYSTEM_INSTRUCTION}\n"
            f"<|user|>\n{json.dumps(self.input_json, separators=(',', ':'))}\n"
            f"<|assistant|>\n"
        )
        completion = json.dumps(self.output_json, separators=(",", ":"))
        return json.dumps({"text": prompt + completion})


def _region_from_country(country: str) -> str:
    c = (country or "").strip().upper()
    if c in ("US", "USA", "UNITED STATES"):
        return "US"
    if c in ("GB", "UK", "UNITED KINGDOM"):
        return "UK"
    if c in ("DE", "FR", "NL", "ES", "IT", "EU"):
        return "EU"
    if c in ("PK", "PAKISTAN"):
        return "PK"
    if c in ("SG", "JP", "IN", "AU"):
        return "APAC"
    return c or "US"


def _synthesize(
    account_name: str,
    deal_name: str,
    region: str,
    line_items: list[dict[str, Any]],
    final_total_cents: int,
) -> Example | None:
    """Build one training example. Returns None if the record can't be used."""
    if not line_items or final_total_cents <= 0 or not account_name:
        return None

    # Each line item must have sku, quantity, unit_price_cents (final agreed).
    # Synthesize base_price and min_price_floor when missing — treat the agreed
    # price as a discount off a 5-25% higher nominal base, with a 15-25% floor
    # below the final price. This gives the model a realistic "margin above
    # floor" signal to learn from.
    input_lines: list[dict[str, Any]] = []
    output_prices: dict[str, int] = {}
    rng = random.Random(hash(f"{account_name}|{deal_name}"))
    for li in line_items:
        sku = li.get("sku")
        qty = int(li.get("quantity", 0))
        agreed_cents = int(li.get("unit_price_cents") or 0)
        if not sku or qty <= 0 or agreed_cents <= 0:
            return None
        base_cents = int(agreed_cents * (1.0 + rng.uniform(0.05, 0.25)))
        floor_cents = int(agreed_cents * (1.0 - rng.uniform(0.10, 0.20)))
        floor_cents = max(1, min(floor_cents, agreed_cents - 1))
        input_lines.append({
            "sku": sku,
            "product_name": li.get("product_name", sku),
            "quantity": qty,
            "base_price_cents": base_cents,
            "min_price_floor_cents": floor_cents,
        })
        output_prices[sku] = agreed_cents

    input_json = {
        "buyer": {"region": region, "client_name": account_name, "deal_name": deal_name},
        "line_items": input_lines,
        "policy": {
            "min_margin_percent": 15.0,
            "max_discount_percent": 20.0,
            "max_discount_with_approval_percent": 35.0,
            "allowed_regions": ["US", "EU", "APAC", "UK", "PK"],
            "currency_allowlist": ["USD"],
        },
    }
    output_json = {
        "proposed_unit_prices": output_prices,
        "rationale": "",                      # trained to be empty — model fills freely
        "confidence": 0.9,
    }
    return Example(input_json=input_json, output_json=output_json)


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------

async def _read_seeded() -> Iterable[tuple[str, str, str, list[dict[str, Any]], int]]:
    """Yield rows from the DocumentLog table. Tiny — just for pipeline smoke test."""
    async with async_session() as db:
        from sqlalchemy import select       # local import; script is standalone-runnable
        docs = (await db.execute(select(DocumentLog))).scalars().all()
        for d in docs:
            if not d.amount or d.amount <= 0:
                continue
            # Synthesize a single-line item from the doc — real Salesforce CSVs
            # have richer line data; the seed DB doesn't.
            yield (
                d.client or "Unknown",
                d.deal_name or "",
                _region_from_country("US"),
                [{
                    "sku": "LEGACY-LINE",
                    "product_name": d.deal_name or "Line",
                    "quantity": 1,
                    "unit_price_cents": int(d.amount * 100),
                }],
                int(d.amount * 100),
            )


def _read_csv(path: Path) -> Iterable[tuple[str, str, str, list[dict[str, Any]], int]]:
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            normalized = {CSV_ALIASES.get(k, k): v for k, v in row.items()}
            try:
                amount_cents = int(float(normalized.get("amount", 0)) * 100)
            except (TypeError, ValueError):
                continue
            try:
                line_items = json.loads(normalized.get("line_items_json") or "[]")
            except json.JSONDecodeError:
                continue
            yield (
                normalized.get("account_name", ""),
                normalized.get("deal_name", ""),
                _region_from_country(normalized.get("billing_country", "")),
                line_items,
                amount_cents,
            )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("seeded", "csv"), default="seeded")
    parser.add_argument("--csv-path", type=Path, default=None)
    parser.add_argument("--split", type=float, default=0.9, help="train fraction")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"raw": 0, "kept": 0, "deduped": 0, "final_train": 0, "final_valid": 0}

    # Read source
    if args.source == "seeded":
        source_iter = [row async for row in _read_seeded()]
    else:
        if args.csv_path is None or not args.csv_path.exists():
            raise SystemExit("--csv-path required and must exist for --source csv")
        source_iter = list(_read_csv(args.csv_path))

    stats["raw"] = len(source_iter)
    logger.info("raw rows: %d", stats["raw"])

    examples: list[Example] = []
    seen_keys: set[str] = set()
    for row in source_iter:
        ex = _synthesize(*row)
        if ex is None:
            continue
        key = f"{row[0]}|{row[1]}|{sum(li['unit_price_cents'] for li in row[3])}"
        if key in seen_keys:
            stats["deduped"] += 1
            continue
        seen_keys.add(key)
        examples.append(ex)
    stats["kept"] = len(examples)
    logger.info("synthesized: %d (deduped %d)", stats["kept"], stats["deduped"])

    random.Random(args.seed).shuffle(examples)
    split = int(len(examples) * args.split)
    train_rows = examples[:split]
    valid_rows = examples[split:]
    stats["final_train"] = len(train_rows)
    stats["final_valid"] = len(valid_rows)

    (OUTPUT_DIR / "train.jsonl").write_text(
        "\n".join(e.to_jsonl_line() for e in train_rows), encoding="utf-8"
    )
    (OUTPUT_DIR / "valid.jsonl").write_text(
        "\n".join(e.to_jsonl_line() for e in valid_rows), encoding="utf-8"
    )
    (OUTPUT_DIR / "dataset_stats.json").write_text(json.dumps(stats, indent=2))

    logger.info("wrote %d train / %d valid to %s", stats["final_train"], stats["final_valid"], OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
