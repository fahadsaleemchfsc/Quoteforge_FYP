"""
AI Generation Service — Wrapped LLM + RAG integration.
Generates proposal sections using a self-hosted wrapped LLM (Ollama/Mistral).

Architecture (LLM Wrapping Concept):
  1. RAG Engine retrieves relevant context from knowledge base (ChromaDB)
  2. Prompt templates filled with deal data + retrieved context
  3. WRAPPED LLM generates content (self-hosted via Ollama, NOT third-party API)
  4. Output validation: price hallucination check, quality guardrails
  5. Fallback templates used when LLM is unavailable

The LLM is OUR model running on OUR infrastructure.
No data leaves the system. This is what differentiates us from PandaDoc/Salesforce CPQ.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ai_prompt import AIPrompt
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import RAG engine
try:
    from rag_pipeline.rag_engine import retrieve_context, initialize_rag
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logger.info("RAG engine not available — running without retrieval augmentation")

# Default prompt templates for each section
DEFAULT_PROMPTS = {
    "Cover Letter": (
        "Write a professional cover letter for a sales proposal.\n"
        "Client: {{client_name}}\nDeal: {{deal_name}}\nAmount: ${{deal_amount}}\n"
        "Products/Services: {{line_items}}\n\n"
        "The tone should be professional, confident, and personalized. "
        "Keep it concise (2-3 paragraphs)."
    ),
    "Scope": (
        "Write a detailed Scope of Work section for the following deal.\n"
        "Client: {{client_name}}\nDeal: {{deal_name}}\n"
        "Products/Services:\n{{line_items}}\n\n"
        "Include objectives, deliverables timeline, and success criteria."
    ),
    "Pricing": (
        "Write a pricing summary section for this proposal.\n"
        "Client: {{client_name}}\nDeal: {{deal_name}}\n"
        "Line Items:\n{{line_items}}\n"
        "Subtotal: ${{subtotal}}\nDiscount: ${{discount}}\nTax: ${{tax}}\n"
        "Total: ${{total}}\n\n"
        "Present the pricing clearly and professionally."
    ),
    "Deliverables": (
        "Write a deliverables section for this proposal.\n"
        "Client: {{client_name}}\nDeal: {{deal_name}}\n"
        "Products/Services:\n{{line_items}}\n\n"
        "List each deliverable with description and timeline."
    ),
    "Terms": (
        "Write Terms and Conditions for this proposal.\n"
        "Region: {{region}}\nCompliance: {{compliance_framework}}\n"
        "Include payment terms, warranty, liability, and applicable compliance clauses.\n"
        "{{compliance_clauses}}"
    ),
    "Summary": (
        "Write an executive summary for this proposal.\n"
        "Client: {{client_name}}\nDeal: {{deal_name}}\nAmount: ${{deal_amount}}\n"
        "Products/Services: {{line_items}}\n\n"
        "Summarize the value proposition in 2-3 paragraphs."
    ),
}


def _fill_template(template: str, context: dict) -> str:
    """Replace {{variable}} placeholders with context values."""
    result = template
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def _format_line_items(items: list) -> str:
    if not items:
        return "N/A"
    lines = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("product", "Item")
            qty = item.get("quantity", 1)
            price = item.get("unit_price", 0)
            lines.append(f"- {name} (Qty: {qty}, Unit Price: ${price:,.2f})")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


async def generate_section_with_wrapped_llm(
    section: str,
    prompt_text: str,
    rag_context: str = "",
    deal_context: dict = None,
) -> str:
    """
    Generate content using the WRAPPED LLM (self-hosted via Ollama).
    Falls back to OpenAI only if Ollama is unavailable.
    NO data goes to third parties when Ollama is running.
    """
    try:
        from app.services.llm_wrapper import generate_with_wrapped_llm
        result = await generate_with_wrapped_llm(
            section=section,
            prompt_text=prompt_text,
            rag_context=rag_context,
            deal_context=deal_context,
        )
        if result["content"]:
            logger.info(
                f"[{section}] Generated via {result['model']} | "
                f"Validated: {result['validated']} | "
                f"RAG: {result['rag_used']} | "
                f"Notes: {result['validation_notes']}"
            )
            return result["content"]
    except Exception as e:
        logger.error(f"Wrapped LLM generation failed: {e}")

    return ""


def _fallback_cover_letter(ctx: dict) -> str:
    return (
        f"Dear {ctx.get('client_name', 'Valued Client')},\n\n"
        f"Thank you for the opportunity to present this proposal for {ctx.get('deal_name', 'your project')}. "
        f"We are pleased to offer our products and services totaling ${ctx.get('deal_amount', 0):,.2f}.\n\n"
        f"We are confident that our solution will deliver exceptional value and look forward to "
        f"building a successful partnership with your organization.\n\n"
        f"Sincerely,\nThe QuoteForge Team"
    )


def _fallback_scope(ctx: dict) -> str:
    items = ctx.get("line_items_formatted", "N/A")
    return (
        f"Scope of Work — {ctx.get('deal_name', 'Project')}\n\n"
        f"Objective: Deliver the following products and services to {ctx.get('client_name', 'the client')}.\n\n"
        f"Deliverables:\n{items}\n\n"
        f"Timeline: To be mutually agreed upon following contract execution.\n"
        f"Success Criteria: Successful delivery and acceptance of all listed items."
    )


def _fallback_pricing(ctx: dict) -> str:
    return (
        f"Pricing Summary\n\n"
        f"Subtotal: ${ctx.get('subtotal', 0):,.2f}\n"
        f"Discount: ${ctx.get('discount', 0):,.2f}\n"
        f"Tax: ${ctx.get('tax', 0):,.2f}\n"
        f"Total: ${ctx.get('total', 0):,.2f}\n\n"
        f"Payment Terms: Net 30 days from invoice date."
    )


def _fallback_deliverables(ctx: dict) -> str:
    items = ctx.get("line_items_formatted", "N/A")
    return f"Deliverables\n\n{items}\n\nAll deliverables will be provided as specified above."


def _fallback_terms(ctx: dict) -> str:
    region = ctx.get("region", "US")
    clauses = ctx.get("compliance_clauses", "")
    base = (
        "Terms and Conditions\n\n"
        "1. Payment: Net 30 days from invoice date.\n"
        "2. Warranty: 12-month warranty on all deliverables.\n"
        "3. Liability: Limited to the total contract value.\n"
        "4. Confidentiality: Both parties agree to maintain confidentiality.\n"
        "5. Termination: Either party may terminate with 30 days written notice.\n"
    )
    if clauses:
        base += f"\nCompliance:\n{clauses}\n"
    return base


def _fallback_summary(ctx: dict) -> str:
    return (
        f"Executive Summary\n\n"
        f"This proposal outlines our offering for {ctx.get('deal_name', 'the project')} "
        f"for {ctx.get('client_name', 'the client')}, valued at ${ctx.get('deal_amount', 0):,.2f}.\n\n"
        f"Our solution is designed to meet your specific requirements while ensuring "
        f"compliance with applicable regulatory frameworks."
    )


FALLBACKS = {
    "Cover Letter": _fallback_cover_letter,
    "Scope": _fallback_scope,
    "Pricing": _fallback_pricing,
    "Deliverables": _fallback_deliverables,
    "Terms": _fallback_terms,
    "Summary": _fallback_summary,
}


async def generate_proposal_sections(
    db: AsyncSession,
    context: dict,
) -> dict:
    """
    Generate all proposal sections using AI prompts from the database.
    Falls back to template-based generation if LLM is unavailable.
    """
    line_items_formatted = _format_line_items(context.get("line_items", []))
    ctx = {
        **context,
        "line_items": line_items_formatted,
        "line_items_formatted": line_items_formatted,
    }

    sections = {}
    section_names = ["Cover Letter", "Scope", "Pricing", "Deliverables", "Terms", "Summary"]

    for section_name in section_names:
        # Try to get prompt from database
        result = await db.execute(
            select(AIPrompt).where(
                AIPrompt.section == section_name,
                AIPrompt.status == "active",
            )
        )
        prompt_record = result.scalar_one_or_none()

        if prompt_record and prompt_record.prompt_text:
            prompt_text = _fill_template(prompt_record.prompt_text, ctx)
        else:
            default = DEFAULT_PROMPTS.get(section_name, "")
            prompt_text = _fill_template(default, ctx)

        # Generate content — prefer fine-tuned MLX model, fallback to templates
        import os
        use_llm = os.getenv("QUOTEFORGE_USE_LLM", "false").lower() == "true"
        llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()

        generated = ""
        if use_llm:
            try:
                import asyncio

                if llm_backend == "mlx":
                    # Use our fine-tuned Apple Silicon model
                    from app.services.mlx_inference import generate_mlx
                    generated = await asyncio.wait_for(
                        generate_mlx(prompt_text, max_tokens=512),
                        timeout=30.0,
                    )
                else:
                    # Fallback: Ollama/OpenAI wrapped LLM
                    generated = await asyncio.wait_for(
                        generate_section_with_wrapped_llm(
                            section=section_name,
                            prompt_text=prompt_text,
                            rag_context="",
                            deal_context=ctx,
                        ),
                        timeout=10.0,
                    )
            except Exception as e:
                logger.info(f"LLM unavailable for {section_name}, using template: {e}")

        if generated:
            sections[section_name] = generated
            if prompt_record:
                prompt_record.last_used = datetime.now(timezone.utc)
                await db.commit()
        else:
            # Fast professional templates (instant)
            fallback_fn = FALLBACKS.get(section_name)
            sections[section_name] = fallback_fn(ctx) if fallback_fn else ""

    return sections


async def test_prompt(db: AsyncSession, prompt_id: int, test_context: Optional[dict] = None) -> dict:
    """Test a specific prompt with sample data."""
    result = await db.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        return {"error": "Prompt not found"}

    sample_context = test_context or {
        "client_name": "Acme Corporation",
        "deal_name": "Enterprise License Agreement",
        "deal_amount": "75,000",
        "line_items": "- Enterprise Platform License (Qty: 1, $50,000)\n- Implementation Services (Qty: 1, $15,000)\n- Annual Support (Qty: 1, $10,000)",
        "region": "US",
        "compliance_framework": "SOC 2, GDPR",
        "compliance_clauses": "SOC 2 Type II compliance required. GDPR data processing agreement included.",
        "subtotal": "75,000",
        "discount": "7,500",
        "tax": "5,062.50",
        "total": "72,562.50",
    }

    filled_prompt = _fill_template(prompt.prompt_text or DEFAULT_PROMPTS.get(prompt.section, ""), sample_context)
    generated = await generate_section_with_llm(filled_prompt)

    if not generated:
        fallback_fn = FALLBACKS.get(prompt.section)
        generated = fallback_fn(sample_context) if fallback_fn else "No output generated. Configure OPENAI_API_KEY for AI generation."

    return {
        "prompt_id": prompt.id,
        "section": prompt.section,
        "filled_prompt": filled_prompt,
        "output": generated,
        "model": settings.AI_MODEL if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key-here" else "fallback-template",
    }
