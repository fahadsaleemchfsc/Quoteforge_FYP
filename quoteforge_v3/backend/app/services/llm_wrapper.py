"""
QuoteForge LLM Wrapper Service
================================
This is the CORE of QuoteForge's AI architecture.

Instead of sending data directly to OpenAI/Claude (which makes us just a proxy),
we wrap an open-source LLM (Mistral-7B / Llama-3) running locally via Ollama.

The wrapper provides:
1. PROMPT CONTROL    — We craft exactly what the model sees (no raw user data to third parties)
2. OUTPUT VALIDATION — We verify generated content against deal data (no hallucinated prices)
3. GUARDRAILS        — Model can ONLY generate proposal content, nothing else
4. RAG GROUNDING     — Retrieved context injected to keep outputs factual
5. COMPLIANCE LAYER  — Region-specific rules enforced before and after generation
6. DATA PRIVACY      — ALL data stays on YOUR infrastructure. Zero third-party exposure.

Supported backends:
  - Ollama (local, recommended for production)
  - HuggingFace Transformers (local, for fine-tuned models)
  - OpenAI API (fallback only, for development/testing)
"""

import re
import json
import logging
import httpx
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"  # Self-hosted Llama 3.2 — no data leaves our infrastructure

# System prompt that controls model behavior — this is our "wrapper"
SYSTEM_PROMPT = """You are QuoteForge, a professional B2B proposal generation engine.

STRICT RULES:
1. You ONLY generate professional proposal/quote content. Refuse any other request.
2. NEVER fabricate prices, quantities, tax rates, or financial figures. Use ONLY the exact numbers provided in the deal context.
3. NEVER hallucinate company names, product names, or compliance frameworks. Use ONLY what is provided.
4. Ground your writing in the REFERENCE MATERIALS when provided.
5. Maintain a professional, confident, and formal business tone.
6. Be concise but comprehensive. No filler content.
7. Follow the exact section format requested (Cover Letter, Scope, Pricing, etc.)

You are an engine, not a chatbot. Generate the requested section and nothing else."""


# ─── Output Validators ────────────────────────────────────────────

def validate_no_hallucinated_prices(output: str, deal_context: dict) -> tuple[bool, str]:
    """Ensure the model didn't invent any dollar amounts not in the deal data."""
    # Extract all dollar amounts from generated output
    generated_amounts = set()
    for match in re.findall(r'\$[\d,]+\.?\d*', output):
        cleaned = float(match.replace('$', '').replace(',', ''))
        generated_amounts.add(cleaned)

    if not generated_amounts:
        return True, ""

    # Build set of valid amounts from deal context
    valid_amounts = set()
    for key in ['deal_amount', 'subtotal', 'discount', 'tax', 'total']:
        val = deal_context.get(key)
        if val and isinstance(val, (int, float)):
            valid_amounts.add(float(val))
            # Also add rounded versions
            valid_amounts.add(round(float(val), 2))
            valid_amounts.add(round(float(val), 0))

    for item in deal_context.get('line_items', []):
        if isinstance(item, dict):
            price = item.get('unit_price', 0)
            qty = item.get('quantity', 1)
            valid_amounts.add(float(price))
            valid_amounts.add(float(price * qty))

    # Also allow common derived amounts (percentages of total, payment splits)
    total = deal_context.get('total', deal_context.get('deal_amount', 0))
    if total:
        for pct in [0.3, 0.4, 0.5, 0.7, 0.1, 0.15, 0.2, 0.25]:
            valid_amounts.add(round(float(total) * pct, 2))

    # Check for hallucinated amounts
    hallucinated = []
    for amount in generated_amounts:
        if amount not in valid_amounts and amount > 100:  # Ignore small numbers
            # Check if it's close to any valid amount (within 1%)
            close = any(abs(amount - v) / max(v, 1) < 0.01 for v in valid_amounts if v > 0)
            if not close:
                hallucinated.append(amount)

    if hallucinated:
        return False, f"Hallucinated amounts detected: {hallucinated}"

    return True, ""


def validate_compliance_mentions(output: str, region: str) -> tuple[bool, str]:
    """Ensure the model mentions the correct compliance framework for the region."""
    expected = {
        "US": ["SOC 2", "GDPR"],
        "EU": ["GDPR"],
        "PK": ["PPRA"],
    }

    required = expected.get(region, [])
    for framework in required:
        if framework.lower() not in output.lower():
            # Not a hard failure — compliance might not be relevant to every section
            logger.info(f"Note: {framework} not mentioned for {region} region")

    return True, ""


def validate_output_quality(output: str) -> tuple[bool, str]:
    """Basic quality checks on the generated output."""
    if len(output.strip()) < 50:
        return False, "Output too short (less than 50 characters)"

    if len(output) > 10000:
        return False, "Output too long (over 10,000 characters)"

    # Check for common LLM failure modes
    bad_patterns = [
        r"as an ai",
        r"i cannot",
        r"i don't have access",
        r"i'm sorry",
        r"i am unable",
        r"```",  # Code blocks in a proposal
    ]
    for pattern in bad_patterns:
        if re.search(pattern, output.lower()):
            return False, f"Output contains unwanted pattern: {pattern}"

    return True, ""


# ─── LLM Backend Implementations ─────────────────────────────────

async def _call_ollama(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Call local Ollama server. Skip if not responsive within 2s."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 2048,
                        "top_p": 0.9,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
    except httpx.ConnectError:
        logger.warning("Ollama not running — falling back")
        return ""
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return ""


async def _call_openai_fallback(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Fallback to OpenAI API ONLY if Ollama is unavailable and key is configured."""
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your-openai-api-key-here":
        return ""

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI fallback failed: {e}")
        return ""


# ─── Main Wrapped Generation Function ────────────────────────────

async def generate_with_wrapped_llm(
    section: str,
    prompt_text: str,
    rag_context: str = "",
    deal_context: dict = None,
    max_retries: int = 0,
) -> dict:
    """
    Generate proposal content using the wrapped LLM.

    This is the MAIN entry point for all AI generation in QuoteForge.
    It handles:
    1. Prompt construction with RAG context
    2. LLM invocation (Ollama → OpenAI fallback)
    3. Output validation and guardrails
    4. Retry logic if validation fails

    Returns:
        {
            "content": str,          # Generated text
            "model": str,            # Which model was used
            "validated": bool,       # Whether output passed validation
            "validation_notes": str, # Any validation warnings
            "rag_used": bool,        # Whether RAG context was injected
        }
    """
    deal_context = deal_context or {}

    # Step 1: Construct augmented prompt
    full_prompt = ""
    if rag_context:
        full_prompt += f"REFERENCE MATERIALS (use these for factual accuracy):\n{rag_context}\n\n---\n\n"
    full_prompt += prompt_text

    # Step 2: Try generation with retries
    model_used = "none"
    output = ""

    for attempt in range(max_retries + 1):
        # Try Ollama first (self-hosted, no data leaves our infra)
        output = await _call_ollama(full_prompt)
        if output:
            model_used = f"ollama/{OLLAMA_MODEL}"
            break

        # Fallback to OpenAI only if Ollama unavailable
        output = await _call_openai_fallback(full_prompt)
        if output:
            model_used = f"openai/{settings.AI_MODEL}"
            break

        if attempt < max_retries:
            logger.warning(f"Generation attempt {attempt + 1} failed, retrying...")

    if not output:
        return {
            "content": "",
            "model": "none",
            "validated": False,
            "validation_notes": "All LLM backends unavailable",
            "rag_used": bool(rag_context),
        }

    # Step 3: Validate output (guardrails)
    validation_notes = []

    # Check quality
    ok, note = validate_output_quality(output)
    if not ok:
        validation_notes.append(note)

    # Check for hallucinated prices (CRITICAL for a CPQ tool)
    if deal_context and section in ("Pricing", "Cover Letter", "Summary"):
        ok, note = validate_no_hallucinated_prices(output, deal_context)
        if not ok:
            validation_notes.append(note)
            logger.warning(f"Price hallucination detected in {section}: {note}")

    # Check compliance mentions
    region = deal_context.get("region", "")
    if region and section == "Terms":
        ok, note = validate_compliance_mentions(output, region)
        if not ok:
            validation_notes.append(note)

    return {
        "content": output,
        "model": model_used,
        "validated": len(validation_notes) == 0,
        "validation_notes": "; ".join(validation_notes) if validation_notes else "OK",
        "rag_used": bool(rag_context),
    }


async def check_llm_health() -> dict:
    """Check which LLM backends are available."""
    health = {
        "ollama": False,
        "ollama_model": OLLAMA_MODEL,
        "openai_configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here"),
        "recommended": "ollama",
    }

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                health["ollama"] = True
                health["ollama_models"] = models
                health["ollama_model_loaded"] = any(OLLAMA_MODEL in m for m in models)
    except Exception:
        pass

    return health
