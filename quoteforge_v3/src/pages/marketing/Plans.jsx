import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, ArrowRight, Sparkles, ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import MarketingNav from '@/components/marketing/MarketingNav';
import MarketingFooter from '@/components/marketing/MarketingFooter';

// Public pricing tiers page. No real Stripe — these CTAs all push to
// /signup. Annual toggle just adjusts the visible numbers (-20%).

const TIERS = [
  {
    name: 'Starter',
    tagline: 'For one rep testing the waters.',
    priceMonthly: 0,
    priceAnnual: 0,
    cta: 'Start free',
    href: '/signup',
    highlighted: false,
    features: [
      '50 quotes / month',
      'Default 2-page master template',
      'Salesforce Connected App',
      'PDF + DOCX export',
      'Email delivery',
      'Community support',
    ],
  },
  {
    name: 'Pro',
    tagline: 'For sales teams shipping every day.',
    priceMonthly: 49,
    priceAnnual: 39,
    cta: 'Start 14-day trial',
    href: '/signup',
    highlighted: true,
    features: [
      'Unlimited quotes',
      'Custom HTML master template',
      'Guardrails &amp; approval workflows',
      'Win-probability model (per-tenant)',
      'Buyer-room negotiation links',
      'CRM write-back (Quote object)',
      'Priority email support',
    ],
  },
  {
    name: 'Enterprise',
    tagline: 'For orgs with compliance, scale, SSO.',
    priceMonthly: null,
    priceAnnual: null,
    cta: 'Contact sales',
    href: 'mailto:sales@quoteforge.io',
    highlighted: false,
    features: [
      'Everything in Pro, plus —',
      'SSO (Okta, Azure AD, Google)',
      'SOC 2 audit log export',
      'Dedicated tenant instance',
      'Custom data residency',
      'Salesforce managed package install',
      'Solutions engineer onboarding',
      'SLA &amp; uptime guarantee',
    ],
  },
];

const COMPARE = [
  { label: 'Quotes per month', starter: '50', pro: 'Unlimited', enterprise: 'Unlimited' },
  { label: 'Master template HTML editor', starter: '—', pro: '✓', enterprise: '✓' },
  { label: 'Guardrails (discount caps, approval thresholds)', starter: '—', pro: '✓', enterprise: '✓' },
  { label: 'Buyer-room negotiation', starter: '—', pro: '✓', enterprise: '✓' },
  { label: 'Salesforce one-click install', starter: '✓', pro: '✓', enterprise: 'Managed package' },
  { label: 'Win-probability model', starter: '—', pro: 'Per-tenant', enterprise: 'Per-tenant + holdout' },
  { label: 'SSO + audit log export', starter: '—', pro: '—', enterprise: '✓' },
  { label: 'Support', starter: 'Community', pro: 'Priority email', enterprise: 'Dedicated CSM' },
];

const FAQS = [
  {
    q: 'Do I need Salesforce to use QuoteForge?',
    a: 'No. The full quote-generation pipeline works without any CRM connection — Salesforce just makes it 10x faster by streaming opportunities directly. HubSpot and a generic JSON API are also supported.',
  },
  {
    q: 'How does the 2-page cap work?',
    a: 'The default master template is designed to fit on two pages with typical line-item counts. If you edit the template, the cap becomes whatever your HTML produces — you control it via CSS page-breaks. Generated PDFs reliably render at exactly 2 pages with our default.',
  },
  {
    q: 'Can I bring my own AI model?',
    a: 'Yes. Pro and Enterprise support OpenAI, Anthropic, and self-hosted (MLX on Apple Silicon, Ollama, vLLM) backends via the AI Config setting. The default falls back to deterministic templates when no model is configured.',
  },
  {
    q: 'What happens to my data?',
    a: 'Your quote contents, Salesforce tokens, and AI prompts live in your dedicated Postgres database (Enterprise) or your tenant-scoped row on the shared one (Starter/Pro). Tokens are Fernet-encrypted at rest.',
  },
  {
    q: 'Can I cancel any time?',
    a: 'Yes. No annual lock-in on Pro — cancel from Settings and you keep access through the end of your billing period. Enterprise contracts are typically annual.',
  },
];

export default function Plans() {
  const [annual, setAnnual] = useState(true);

  return (
    <div className="bg-white text-zinc-900 antialiased">
      <MarketingNav />

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-50 border border-violet-200 text-violet-700 text-xs font-medium mb-5">
          <Sparkles size={12} /> Simple, usage-based pricing
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          Free until you're shipping every day.
        </h1>
        <p className="mt-5 text-lg text-zinc-600 max-w-xl mx-auto">
          Start on Starter forever, upgrade when you outgrow it. No surprise overages,
          no per-seat fees on the free tier.
        </p>

        {/* Monthly / annual toggle */}
        <div className="mt-9 inline-flex items-center bg-zinc-100 rounded-full p-1">
          <button
            onClick={() => setAnnual(false)}
            className={clsx(
              'px-4 py-1.5 text-sm font-semibold rounded-full transition-colors',
              !annual ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700',
            )}
          >
            Monthly
          </button>
          <button
            onClick={() => setAnnual(true)}
            className={clsx(
              'px-4 py-1.5 text-sm font-semibold rounded-full transition-colors flex items-center gap-1.5',
              annual ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700',
            )}
          >
            Annual <span className="text-[10px] text-emerald-600 font-bold">−20%</span>
          </button>
        </div>
      </section>

      {/* Tier cards */}
      <section className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid md:grid-cols-3 gap-5">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={clsx(
                'rounded-2xl p-7 flex flex-col transition-all',
                tier.highlighted
                  ? 'bg-zinc-900 text-white border border-zinc-900 shadow-2xl shadow-violet-300/30 md:scale-[1.03]'
                  : 'bg-white border border-zinc-200 hover:border-zinc-300',
              )}
            >
              {tier.highlighted && (
                <div className="inline-flex self-start items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-200 text-[10px] font-bold uppercase tracking-wider mb-3">
                  <Sparkles size={10} /> Most popular
                </div>
              )}
              <div className="text-lg font-semibold">{tier.name}</div>
              <div className={clsx('text-sm mt-1', tier.highlighted ? 'text-zinc-400' : 'text-zinc-500')}>
                {tier.tagline}
              </div>

              <div className="mt-7">
                {tier.priceMonthly === null ? (
                  <div className="text-4xl font-bold tracking-tight">Custom</div>
                ) : tier.priceMonthly === 0 ? (
                  <>
                    <div className="text-4xl font-bold tracking-tight">$0</div>
                    <div className={clsx('text-sm mt-1', tier.highlighted ? 'text-zinc-400' : 'text-zinc-500')}>
                      forever, for one workspace
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-4xl font-bold tracking-tight">
                        ${annual ? tier.priceAnnual : tier.priceMonthly}
                      </span>
                      <span className={clsx('text-sm', tier.highlighted ? 'text-zinc-400' : 'text-zinc-500')}>
                        / workspace / month
                      </span>
                    </div>
                    <div className={clsx('text-xs mt-1', tier.highlighted ? 'text-zinc-400' : 'text-zinc-500')}>
                      Billed {annual ? 'annually' : 'monthly'}, cancel any time
                    </div>
                  </>
                )}
              </div>

              <Link
                to={tier.href}
                className={clsx(
                  'mt-6 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-md font-semibold text-sm transition-colors',
                  tier.highlighted
                    ? 'bg-violet-500 text-white hover:bg-violet-400'
                    : 'bg-zinc-900 text-white hover:bg-zinc-800',
                )}
              >
                {tier.cta} <ArrowRight size={14} />
              </Link>

              <ul className="mt-7 space-y-2.5">
                {tier.features.map((f) => (
                  <li
                    key={f}
                    className={clsx(
                      'flex items-start gap-2 text-sm',
                      tier.highlighted ? 'text-zinc-200' : 'text-zinc-700',
                    )}
                  >
                    <Check
                      size={14}
                      strokeWidth={3}
                      className={clsx(
                        'flex-shrink-0 mt-0.5',
                        tier.highlighted ? 'text-violet-400' : 'text-violet-600',
                      )}
                    />
                    <span dangerouslySetInnerHTML={{ __html: f }} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Compare table */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-2xl md:text-3xl font-bold text-center tracking-tight mb-10">
          Compare plans
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200">
                <th className="text-left py-3 px-4 font-semibold text-zinc-700">Feature</th>
                <th className="text-center py-3 px-4 font-semibold text-zinc-700">Starter</th>
                <th className="text-center py-3 px-4 font-semibold text-violet-700 bg-violet-50/40 rounded-t">Pro</th>
                <th className="text-center py-3 px-4 font-semibold text-zinc-700">Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE.map((row) => (
                <tr key={row.label} className="border-b border-zinc-100">
                  <td className="py-3 px-4 text-zinc-700">{row.label}</td>
                  <td className="py-3 px-4 text-center text-zinc-500">{row.starter}</td>
                  <td className="py-3 px-4 text-center font-medium text-zinc-900 bg-violet-50/40">{row.pro}</td>
                  <td className="py-3 px-4 text-center text-zinc-500">{row.enterprise}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-3xl mx-auto px-6 py-16">
        <h2 className="text-2xl md:text-3xl font-bold text-center tracking-tight mb-10">
          Common questions
        </h2>
        <div className="space-y-3">
          {FAQS.map((faq, i) => (
            <FaqItem key={i} q={faq.q} a={faq.a} defaultOpen={i === 0} />
          ))}
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}

function FaqItem({ q, a, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-zinc-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-zinc-50 transition-colors"
      >
        <span className="font-semibold text-zinc-900">{q}</span>
        <ChevronDown
          size={16}
          className={clsx('text-zinc-500 transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="px-5 pb-4 text-sm text-zinc-600 leading-relaxed">{a}</div>
      )}
    </div>
  );
}
