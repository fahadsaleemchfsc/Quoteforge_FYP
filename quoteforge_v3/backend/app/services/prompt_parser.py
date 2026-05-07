"""
Prompt-to-Deal Parser
======================
Takes natural language like:
  "Create a proposal for Acme Corp. They need an enterprise license
   for $50K, implementation services for $15K, and annual support for $10K."

And extracts structured deal data:
  {
    "client_name": "Acme Corp",
    "deal_name": "Enterprise License Package",
    "line_items": [
      {"product": "Enterprise License", "quantity": 1, "unit_price": 50000},
      {"product": "Implementation Services", "quantity": 1, "unit_price": 15000},
      {"product": "Annual Support", "quantity": 1, "unit_price": 10000}
    ],
    "region": "US",
    "deal_amount": 75000
  }

Uses the fine-tuned MLX model when available, falls back to regex parsing.
"""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Regex-based Parser (Fallback, always works) ─────────────────

def parse_with_regex(prompt: str) -> dict:
    """Extract deal data using regex patterns — works without AI."""
    result = {
        "client_name": "",
        "deal_name": "",
        "deal_amount": 0.0,
        "region": "US",
        "contact_email": "",
        "line_items": [],
        "notes": "",
    }

    # ─── Client Name ───────────────────────────────────────────
    # Order matters: most specific first
    client_patterns = [
        # "for ClientName" — highest priority, stops at "in" or "they" or period
        r'(?:proposal|quote|deal)\s+for\s+([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,5}?)(?=\s+(?:in|they|who|that|which|wants|needs|requires|is|are|located)|\.\s|$|,)',
        # "for ClientName" as a fallback
        r'(?:for|to|with)\s+([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3})(?=\s*[.,]|\s+(?:they|who|that|which|wants|needs|requires|is\s+looking|is\s+interested))',
        # Explicit "client: XYZ" or "company: XYZ"
        r'(?:client|company|account|organization)[:\s]+([A-Z][A-Za-z0-9&.\s-]{2,40}?)(?=[.,\n]|$)',
        # "ClientName needs/wants/requires"
        r'\b([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3})\s+(?:needs|wants|requires|is\s+looking)',
        # Direct mention with Corp/Inc/LLC suffix
        r'\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3}\s+(?:Corp|Corporation|Inc|Incorporated|LLC|Ltd|Limited|GmbH|SA|plc|Co|Group|Holdings|Partners|Systems|Solutions|Services|Technologies|Software|Industries|Enterprises|Board|Authority|Agency))\b',
    ]

    stop_words = {"create", "generate", "proposal", "quote", "deal", "please", "hi", "hello", "hey",
                  "the", "a", "an", "this", "that", "these", "those", "i", "we", "they"}

    for pattern in client_patterns:
        match = re.search(pattern, prompt)
        if match:
            candidate = match.group(1).strip().rstrip('.,').strip()
            # Skip if starts with stop word
            first_word = candidate.split()[0].lower() if candidate else ""
            if first_word in stop_words:
                continue
            if 3 <= len(candidate) <= 60 and candidate[0].isupper():
                result["client_name"] = candidate
                break

    # ─── Email (optional) ──────────────────────────────────────
    email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', prompt)
    if email_match:
        result["contact_email"] = email_match.group(0)

    # ─── Region Detection ──────────────────────────────────────
    prompt_lower = prompt.lower()
    if any(w in prompt_lower for w in ["pakistan", "ppra", "lahore", "karachi", "islamabad"]):
        result["region"] = "PK"
    elif any(w in prompt_lower for w in ["europe", "european", "gdpr", "germany", "france", "uk", "eu "]):
        result["region"] = "EU"

    # ─── Line Items ────────────────────────────────────────────
    # Best pattern: "Product Name for $X,XXX" or "Product Name at $X"
    # We look for product phrases followed by prices, using comma/and as delimiters

    # Clean up article words and conjunctions from product names
    product_stop_words = {"they", "need", "needs", "want", "wants", "require", "requires",
                          "needing", "wanting", "requiring", "is", "are", "was", "were",
                          "we", "you", "us", "client", "company",
                          "looking", "interested", "for",
                          "an", "a", "the", "and", "plus", "with", "also", "some", "our",
                          "this", "that", "these", "those"}

    def clean_product_name(name: str) -> str:
        """Strip leading/trailing stop words from a product name."""
        words = name.strip().rstrip('.,').split()
        # Trim leading stop words
        while words and words[0].lower() in product_stop_words:
            words.pop(0)
        # Trim trailing stop words
        while words and words[-1].lower() in product_stop_words:
            words.pop()
        return " ".join(words)

    found_items = []

    # Primary pattern: "Product for $amount" or "Product at $amount"
    # Use sentence-aware matching
    item_pattern = r'([A-Z][A-Za-z0-9\s&-]{2,50}?)\s+(?:for|at|@|priced\s+at|costs?|costing)\s+\$([\d,]+(?:\.\d{1,2})?)\s*([kKmM]?)'

    for match in re.finditer(item_pattern, prompt):
        name_raw = match.group(1)
        amount_str = match.group(2)
        suffix = match.group(3).lower()

        try:
            amount = float(amount_str.replace(',', ''))
            if suffix == 'k':
                amount *= 1000
            elif suffix == 'm':
                amount *= 1_000_000

            name = clean_product_name(name_raw)

            if amount > 0 and 3 <= len(name) <= 60:
                found_items.append({
                    "product": name.title() if name.islower() else name,
                    "quantity": 1,
                    "unit_price": amount,
                })
        except ValueError:
            continue

    # Secondary pattern: "$X for Product"
    reverse_pattern = r'\$([\d,]+(?:\.\d{1,2})?)\s*([kKmM]?)\s+(?:for|of|worth\s+of)\s+([A-Z][A-Za-z0-9\s&-]{2,50}?)(?=[.,]|\s+and\s+|\s+plus\s+|$)'

    for match in re.finditer(reverse_pattern, prompt):
        amount_str = match.group(1)
        suffix = match.group(2).lower()
        name_raw = match.group(3)

        try:
            amount = float(amount_str.replace(',', ''))
            if suffix == 'k':
                amount *= 1000
            elif suffix == 'm':
                amount *= 1_000_000

            name = clean_product_name(name_raw)

            if amount > 0 and 3 <= len(name) <= 60:
                found_items.append({
                    "product": name.title() if name.islower() else name,
                    "quantity": 1,
                    "unit_price": amount,
                })
        except ValueError:
            continue

    # Deduplicate by product name (case-insensitive)
    seen = set()
    for item in found_items:
        key = item["product"].lower()
        if key not in seen:
            seen.add(key)
            result["line_items"].append(item)

    # ─── Total Deal Amount ─────────────────────────────────────
    if result["line_items"]:
        result["deal_amount"] = sum(i["quantity"] * i["unit_price"] for i in result["line_items"])
    else:
        # Try to find a "total" or overall amount
        total_patterns = [
            r'(?:total|overall|deal\s+value|worth|contract)[:\s]+\$?([\d,]+(?:\.\d+)?)\s*[kK]?',
            r'\$([\d,]+(?:\.\d+)?)\s*[kK]?\s+(?:total|deal|contract|engagement)',
        ]
        for pattern in total_patterns:
            m = re.search(pattern, prompt, re.IGNORECASE)
            if m:
                amt = float(m.group(1).replace(',', ''))
                if 'k' in prompt[m.start():m.end()].lower():
                    amt *= 1000
                result["deal_amount"] = amt
                break

    # ─── Deal Name ─────────────────────────────────────────────
    # Generate from line items or client
    if result["line_items"]:
        primary = result["line_items"][0]["product"]
        result["deal_name"] = f"{result['client_name']} - {primary}" if result["client_name"] else primary
    elif result["client_name"]:
        result["deal_name"] = f"{result['client_name']} Engagement"

    # Store original prompt as notes
    result["notes"] = prompt[:500]

    return result


# ─── AI-Enhanced Parser (Uses fine-tuned model) ──────────────────

async def parse_with_ai(prompt: str) -> Optional[dict]:
    """Use fine-tuned LLM to extract structured data. Returns None if AI unavailable."""
    try:
        from app.services.mlx_inference import generate_mlx
    except ImportError:
        return None

    extraction_prompt = f"""Extract deal information from this sales description.
Return ONLY valid JSON with these fields:
- client_name (string)
- deal_name (string)
- deal_amount (number, USD)
- region (string: US, EU, or PK)
- contact_email (string or empty)
- line_items (array of {{product, quantity, unit_price}})

Description: {prompt}

JSON:"""

    try:
        output = await generate_mlx(extraction_prompt, max_tokens=500, temperature=0.2)

        # Try to extract JSON from output
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
    except Exception as e:
        logger.warning(f"AI parsing failed: {e}")

    return None


# ─── Main Entry Point ────────────────────────────────────────────

async def parse_prompt(prompt: str) -> dict:
    """
    Parse a natural language prompt into structured deal data.
    Uses AI first, falls back to regex.
    """
    # Always get regex baseline
    regex_result = parse_with_regex(prompt)

    # Try AI enhancement (merge where AI has better data)
    ai_result = await parse_with_ai(prompt)

    if ai_result:
        # Merge: use AI values when non-empty, fall back to regex
        merged = regex_result.copy()
        for key in ["client_name", "deal_name", "contact_email", "region"]:
            if ai_result.get(key):
                merged[key] = ai_result[key]

        if ai_result.get("deal_amount", 0) > 0:
            merged["deal_amount"] = ai_result["deal_amount"]

        # Prefer AI line items if present
        ai_items = ai_result.get("line_items", [])
        if ai_items and len(ai_items) > len(regex_result["line_items"]):
            merged["line_items"] = ai_items

        merged["source"] = "ai+regex"
        return merged

    regex_result["source"] = "regex"
    return regex_result
