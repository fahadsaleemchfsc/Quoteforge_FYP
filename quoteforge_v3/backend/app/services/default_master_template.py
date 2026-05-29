"""Default 2-page HTML master template shipped with QuoteForge.

CSS is intentionally limited to the xhtml2pdf-supported subset of CSS2
(no flex, no grid, no @bottom-center, no `position: running(...)`). The
template fits comfortably in 2 pages: page 1 covers header + summary +
line items, page 2 covers totals + terms + signatures (forced via
`page-break-before: always`).

Admins replace this verbatim from Templates → Master Template in the UI.
The rendering path tolerates Jinja2 syntax errors by falling back to the
legacy section-based renderer in app/routers/quotes.py.

Variables (Jinja2):
    client_name, deal_name, deal_id, doc_id, doc_type, generated_at,
    valid_until, region, line_items (list of {product, quantity,
    unit_price}), subtotal, discount, tax, total, currency_symbol,
    tenant_name, seller_email, compliance_framework.

Anything else passed through `context` is available too.
"""

DEFAULT_MASTER_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>{{ deal_name or 'Quote' }} — {{ client_name }}</title>
<style>
  @page { size: letter; margin: 0.65in 0.7in; }
  body { font-family: Helvetica, Arial, sans-serif; color: #1f2937; font-size: 10.5pt; line-height: 1.45; }
  h1 { font-size: 22pt; color: #7C3AED; margin: 0 0 4pt 0; }
  h2 { font-size: 13pt; color: #7C3AED; margin: 14pt 0 4pt 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 2pt; }
  .meta { color: #6b7280; font-size: 9pt; margin-bottom: 12pt; }
  .meta b { color: #1f2937; }
  .accent { color: #7C3AED; }
  .hero { background-color: #F3F0FF; padding: 14pt; margin-bottom: 10pt; }
  .hero-title { font-size: 16pt; font-weight: bold; color: #1f2937; margin: 0 0 2pt 0; }
  .hero-sub { color: #6b7280; }
  .kv { width: 100%; margin-top: 4pt; }
  .kv td { padding: 2pt 0; font-size: 9pt; }
  .kv td.l { color: #6b7280; width: 110pt; }
  table.items { width: 100%; border-collapse: collapse; margin-top: 4pt; font-size: 10pt; }
  table.items th { background-color: #7C3AED; color: #ffffff; text-align: left; padding: 6pt 8pt; font-weight: bold; }
  table.items td { border-bottom: 1px solid #e5e7eb; padding: 5pt 8pt; }
  table.items td.r { text-align: right; }
  table.totals { width: 60%; margin-left: 40%; margin-top: 6pt; font-size: 10pt; }
  table.totals td { padding: 3pt 8pt; }
  table.totals td.l { color: #6b7280; }
  table.totals td.r { text-align: right; }
  table.totals tr.total td { border-top: 1.5pt solid #7C3AED; font-weight: bold; color: #7C3AED; padding-top: 5pt; }
  .terms { color: #4b5563; font-size: 9pt; margin-top: 10pt; }
  .sign { margin-top: 22pt; border-top: 1px solid #e5e7eb; padding-top: 14pt; font-size: 9pt; color: #6b7280; }
  .sign-line { display: inline-block; width: 220pt; border-bottom: 1px solid #1f2937; margin-right: 30pt; padding-top: 18pt; }
  .footer { color: #9ca3af; font-size: 8pt; text-align: center; margin-top: 16pt; }
  .page-2 { page-break-before: always; }
</style>
</head>
<body>

<h1>{{ tenant_name or 'QuoteForge' }}</h1>
<div class="meta">
  {{ doc_type or 'Proposal' }} <b>{{ doc_id }}</b> &middot;
  prepared {{ generated_at.strftime('%B %d, %Y') if generated_at else '' }} &middot;
  valid until <b class="accent">{{ valid_until.strftime('%B %d, %Y') if valid_until else '—' }}</b>
</div>

<div class="hero">
  <div class="hero-title">{{ deal_name or 'Engagement' }}</div>
  <div class="hero-sub">Prepared for <b style="color:#1f2937;">{{ client_name }}</b></div>
  <table class="kv">
    <tr><td class="l">Region</td><td>{{ region or 'US' }}</td></tr>
    {% if deal_id %}<tr><td class="l">Deal ref</td><td>{{ deal_id }}</td></tr>{% endif %}
    {% if seller_email %}<tr><td class="l">Account exec</td><td>{{ seller_email }}</td></tr>{% endif %}
  </table>
</div>

<h2>Summary</h2>
<p>
  This {{ (doc_type or 'proposal') | lower }} outlines the engagement, line-item pricing, and
  payment terms for <b>{{ client_name }}</b>. Total contract value
  is <b class="accent">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(total or 0) }}</b>,
  with the rates locked through the validity date above.
</p>

<h2>Line Items</h2>
<table class="items">
  <thead>
    <tr>
      <th>Item</th>
      <th style="width:60pt;">Qty</th>
      <th class="r" style="width:90pt;">Unit price</th>
      <th class="r" style="width:90pt;">Amount</th>
    </tr>
  </thead>
  <tbody>
  {% for item in line_items or [] %}
    <tr>
      <td>{{ item.product or item.name or 'Item' }}</td>
      <td>{{ item.quantity or 1 }}</td>
      <td class="r">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(item.unit_price or 0) }}</td>
      <td class="r">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format((item.unit_price or 0) * (item.quantity or 1)) }}</td>
    </tr>
  {% else %}
    <tr><td colspan="4" style="color:#6b7280;">No line items provided.</td></tr>
  {% endfor %}
  </tbody>
</table>

<div class="page-2"></div>

<h2>Pricing</h2>
<table class="totals">
  <tr><td class="l">Subtotal</td><td class="r">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(subtotal or 0) }}</td></tr>
  {% if (discount or 0) > 0 %}
  <tr><td class="l">Discount</td><td class="r">&minus;{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(discount) }}</td></tr>
  {% endif %}
  {% if (tax or 0) > 0 %}
  <tr><td class="l">Tax</td><td class="r">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(tax) }}</td></tr>
  {% endif %}
  <tr class="total"><td class="l">Total due</td><td class="r">{{ currency_symbol or '$' }}{{ '{:,.2f}'.format(total or 0) }}</td></tr>
</table>

<h2>Terms</h2>
<p class="terms">
  Net 30 from invoice date. Pricing locked through the validity date.
  Either party may terminate with 30 days' written notice; fees accrued
  through the termination date remain due. Confidentiality clauses
  survive termination for three years.
  {% if compliance_framework %}
  Compliance framework: <b>{{ compliance_framework }}</b>.
  {% endif %}
</p>

<div class="sign">
  <span class="sign-line">Authorised by ({{ client_name }})</span>
  <span class="sign-line">Authorised by ({{ tenant_name or 'QuoteForge' }})</span>
</div>

<div class="footer">Generated by {{ tenant_name or 'QuoteForge' }} on {{ generated_at.strftime('%B %d, %Y') if generated_at else '' }}</div>

</body>
</html>
"""
