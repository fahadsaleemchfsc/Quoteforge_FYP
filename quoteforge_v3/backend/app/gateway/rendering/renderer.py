"""
OfferRenderer — takes a persisted, signed offer_payload and produces either:

  - render_pdf(payload, tenant) -> bytes        : human-readable ReportLab PDF
  - render_ucp_json(payload, tenant) -> dict    : UCP 2026-01 style offer envelope

Both derive from the SAME stored offer_payload. The signature that was
produced at quote time remains authoritative — we echo it verbatim into the
UCP envelope so a buyer agent can verify the offer hasn't been mutated in
rendering.

Neither renderer re-runs guardrails or re-queries products. Rendering is
purely a presentation concern.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# UCP protocol version this renderer targets.
UCP_VERSION = "2026-01"

# Brand constants — kept minimal.
BRAND_HEX = "#3576e8"


class OfferRenderer:
    """Stateless — instantiate once, call as many times as you like."""

    def render_pdf(self, offer_payload: dict[str, Any], tenant_name: str = "QuoteForge") -> bytes:
        """
        Render a single-template PDF:
          cover page → line items table → totals → signature block.

        ReportLab in-memory; returns bytes the caller can stream.
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=letter,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
            title=f"Offer {offer_payload.get('offer_id', '')}",
        )
        styles = getSampleStyleSheet()
        story: list = []

        brand_header = ParagraphStyle(
            "BrandHeader", parent=styles["Title"],
            textColor=colors.HexColor(BRAND_HEX), spaceAfter=2,
        )
        tiny = ParagraphStyle(
            "Tiny", parent=styles["Normal"],
            fontSize=8, textColor=colors.grey, spaceAfter=0,
        )
        body = styles["BodyText"]

        # ── Header ──
        story.append(Paragraph(f"<b>{tenant_name}</b>", brand_header))
        story.append(Paragraph("Offer issued via QuoteForge Agent Gateway", tiny))
        story.append(Spacer(1, 0.3 * inch))

        # ── Cover block ──
        offer_id = offer_payload.get("offer_id", "")
        doc_id = offer_payload.get("doc_id", "")
        client = offer_payload.get("client_name", "")
        deal = offer_payload.get("deal_name", "")
        issued_at = offer_payload.get("issued_at", "")
        valid_until = offer_payload.get("valid_until", "")
        region = offer_payload.get("region", "")

        cover = [
            ["Offer ID", offer_id],
            ["Document", doc_id],
            ["Client", client],
            ["Deal", deal],
            ["Region", region],
            ["Issued at", self._fmt_iso(issued_at)],
            ["Valid until", self._fmt_iso(valid_until)],
        ]
        t = Table(cover, colWidths=[1.6 * inch, 5.0 * inch])
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.35 * inch))

        # ── Line items ──
        items_data: list[list[Any]] = [
            ["SKU", "Product", "Qty", "Unit Price", "Line Total"],
        ]
        for li in offer_payload.get("line_items", []):
            items_data.append([
                li.get("sku", ""),
                li.get("product_name", ""),
                str(li.get("quantity", "")),
                self._fmt_money(li.get("unit_price"), offer_payload),
                self._fmt_money(li.get("line_total"), offer_payload),
            ])
        items_tbl = Table(items_data, colWidths=[1.1 * inch, 2.6 * inch, 0.6 * inch, 1.1 * inch, 1.2 * inch])
        items_tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ]))
        story.append(items_tbl)
        story.append(Spacer(1, 0.25 * inch))

        # ── Totals ──
        pricing = offer_payload.get("pricing", {}) or {}
        totals = [
            ["Subtotal", self._fmt_money(pricing.get("subtotal"), offer_payload)],
            ["Discount", "-" + self._fmt_money(pricing.get("discount", 0), offer_payload)],
            ["Tax", self._fmt_money(pricing.get("tax", 0), offer_payload)],
            ["Total", self._fmt_money(pricing.get("total"), offer_payload)],
        ]
        totals_tbl = Table(totals, colWidths=[5.4 * inch, 1.2 * inch])
        totals_tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -2), "Helvetica", 9),
            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TEXTCOLOR", (0, 0), (0, -2), colors.grey),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#111827")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(totals_tbl)
        story.append(Spacer(1, 0.5 * inch))

        # ── Signature block ──
        story.append(Paragraph("<b>Acceptance</b>", body))
        story.append(Paragraph(
            "This offer is accepted by the buyer agent via the QuoteForge MCP "
            "<b>accept_offer</b> tool, using the offer_id and signature below. "
            "The signature covers the canonical form of the offer payload — if "
            "any byte has been altered, acceptance will be refused.",
            tiny,
        ))
        story.append(Spacer(1, 0.1 * inch))
        sig_rows = [
            ["offer_id", offer_id],
            ["signature_alg", "HS256"],
            ["signature", offer_payload.get("__signature__", "") or "<echoed from request_quote>"],
        ]
        sig_tbl = Table(sig_rows, colWidths=[1.3 * inch, 5.3 * inch])
        sig_tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Courier", 8),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(sig_tbl)
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            f"Rendered {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · "
            f"QuoteForge Agent Gateway · offer {offer_id}",
            tiny,
        ))

        doc.build(story)
        return buf.getvalue()

    def render_ucp_json(
        self,
        offer_payload: dict[str, Any],
        tenant_name: str = "QuoteForge",
        signature: str | None = None,
    ) -> dict[str, Any]:
        """
        Returns a UCP 2026-01 compliant offer envelope.

        Signature passes through verbatim — callers should supply the signature
        that was stored alongside the offer at request_quote time.
        """
        currency = (offer_payload.get("pricing", {}) or {}).get("currency", "USD")

        items = [
            {
                "sku": li.get("sku"),
                "name": li.get("product_name", li.get("sku", "")),
                "description": li.get("description", ""),
                "quantity": int(li.get("quantity", 0)),
                "unit": li.get("unit", "ea"),
                "unit_price": {
                    "amount_cents": self._to_cents(li.get("unit_price")),
                    "currency": currency,
                },
                "line_total": {
                    "amount_cents": self._to_cents(li.get("line_total")),
                    "currency": currency,
                },
            }
            for li in offer_payload.get("line_items", [])
        ]

        pricing = offer_payload.get("pricing", {}) or {}
        totals = {
            "subtotal": {"amount_cents": self._to_cents(pricing.get("subtotal")), "currency": currency},
            "discount": {"amount_cents": self._to_cents(pricing.get("discount", 0)), "currency": currency},
            "tax": {"amount_cents": self._to_cents(pricing.get("tax", 0)), "currency": currency},
            "total": {
                "amount_cents": int(pricing.get("total_cents") or self._to_cents(pricing.get("total", 0))),
                "currency": currency,
            },
        }

        return {
            "ucp_version": UCP_VERSION,
            "type": "offer",
            "issuer": {
                "id": f"quoteforge:{offer_payload.get('tenant_id', '')}",
                "name": tenant_name,
            },
            "offer": {
                "id": offer_payload.get("offer_id"),
                "document_id": offer_payload.get("doc_id"),
                "issued_at": offer_payload.get("issued_at"),
                "valid_until": offer_payload.get("valid_until"),
                "buyer": {
                    "client_name": offer_payload.get("client_name"),
                    "deal_name": offer_payload.get("deal_name", ""),
                    "region": offer_payload.get("region"),
                    "contact_email": offer_payload.get("contact_email", ""),
                },
                "items": items,
                "totals": totals,
            },
            "acceptance": {
                "protocol": "mcp",
                "tool": "accept_offer",
                "signature_algorithm": "HS256",
                "signature": signature or offer_payload.get("__signature__", ""),
            },
        }

    # ------------------------------ helpers ------------------------------

    @staticmethod
    def _fmt_iso(iso: str) -> str:
        if not iso:
            return "—"
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            return iso

    @staticmethod
    def _fmt_money(value: Any, payload: dict[str, Any]) -> str:
        currency = (payload.get("pricing", {}) or {}).get("currency", "USD")
        symbol = "$" if currency == "USD" else ""
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            return "—"
        return f"{symbol}{amount:,.2f}"

    @staticmethod
    def _to_cents(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(round(float(value) * 100))
        except (TypeError, ValueError):
            return 0


# Debug helper so curl outputs are easy to parse in shells.
def offer_to_ucp_text(offer_payload: dict[str, Any], signature: str | None = None) -> str:
    return json.dumps(
        OfferRenderer().render_ucp_json(offer_payload, signature=signature),
        indent=2, default=str,
    )
