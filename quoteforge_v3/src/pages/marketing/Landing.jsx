import { Link } from 'react-router-dom';
import {
  Sparkles, Zap, ShieldCheck, BarChart3, Workflow, FileText,
  ArrowRight, Check, Cloud, Bot, Lock,
} from 'lucide-react';
import MarketingNav from '@/components/marketing/MarketingNav';
import MarketingFooter from '@/components/marketing/MarketingFooter';

// Visual SaaS landing page for QuoteForge. Public route /lp.
// Sections: hero · trust · features · how-it-works · integration · CTA.

const FEATURES = [
  {
    icon: Bot,
    title: 'AI-drafted in seconds',
    body: 'Pull a deal from Salesforce, hit Generate, get a brand-styled proposal in under 5 seconds. The AI fills in scope, terms, and pricing — you sign off.',
  },
  {
    icon: FileText,
    title: 'Master template, one source of truth',
    body: 'Set your HTML master template once. Every quote across every rep renders from it, capped at 2 pages. No more "did marketing approve this version?"',
  },
  {
    icon: ShieldCheck,
    title: 'Guardrails that say no for you',
    body: 'Hard caps on discount %, approval thresholds, compliance clauses by region. The AI literally cannot violate them.',
  },
  {
    icon: Cloud,
    title: 'One-click Salesforce install',
    body: 'Connected App OAuth — admin clicks Connect, approves on Salesforce, done. No tunnels, no copy-paste credentials.',
  },
  {
    icon: BarChart3,
    title: 'Win-probability built in',
    body: 'Per-tenant LightGBM model trained on your closed deals. Every quote ships with a confidence interval, not a guess.',
  },
  {
    icon: Workflow,
    title: 'Buyer room negotiation',
    body: 'Share a link, let the buyer chat with a mediator AI that respects your guardrails. Agreed offers land back in your approval queue.',
  },
];

const STEPS = [
  {
    n: '01',
    title: 'Connect Salesforce',
    body: 'Click Connect, approve the Connected App, and your opportunities + accounts stream in. ~30 seconds.',
  },
  {
    n: '02',
    title: 'Set your master template',
    body: 'Drop in your HTML & CSS or use the included 2-page template. Live preview, instant save.',
  },
  {
    n: '03',
    title: 'Generate &amp; push back',
    body: 'Rep picks a deal, hits Generate, reviews the PDF, ships it. Approved quotes write back to the SF Quote object automatically.',
  },
];

export default function Landing() {
  return (
    <div className="bg-white text-zinc-900 antialiased">
      <MarketingNav />

      {/* ─── Hero ─────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10"
          style={{
            backgroundImage:
              'radial-gradient(60% 60% at 50% 0%, rgba(139,92,246,0.18), transparent 70%), radial-gradient(40% 40% at 80% 60%, rgba(167,139,250,0.15), transparent 70%)',
          }}
        />
        <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 md:pt-28 md:pb-24 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-50 border border-violet-200 text-violet-700 text-xs font-medium mb-6">
            <Sparkles size={12} /> Connected App for Salesforce — now in beta
          </div>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-[1.05]">
            Quote in seconds.<br />
            <span className="bg-gradient-to-r from-violet-600 to-fuchsia-600 bg-clip-text text-transparent">
              Close on your terms.
            </span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-zinc-600 max-w-2xl mx-auto leading-relaxed">
            QuoteForge turns Salesforce opportunities into branded, guardrail-checked
            proposals in under five seconds. AI does the drafting. You keep the rules.
          </p>
          <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/signup"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-zinc-900 text-white font-semibold hover:bg-zinc-800 transition-colors shadow-sm"
            >
              Start free <ArrowRight size={16} />
            </Link>
            <Link
              to="/plans"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-white text-zinc-900 font-semibold border border-zinc-300 hover:border-zinc-400 transition-colors"
            >
              See pricing
            </Link>
          </div>
          <div className="mt-6 text-xs text-zinc-500">
            Free forever for the first workspace · No credit card · Sets up in under 10 minutes
          </div>
        </div>

        {/* Product screenshot stand-in */}
        <div className="max-w-5xl mx-auto px-6 pb-24">
          <div className="rounded-2xl border border-zinc-200 bg-white shadow-2xl shadow-violet-200/40 overflow-hidden">
            <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-zinc-200 bg-zinc-50">
              <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
              <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
              <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
              <span className="text-[11px] text-zinc-500 ml-3">app.quoteforge.io / dashboard</span>
            </div>
            <div className="grid grid-cols-12 min-h-[360px]">
              <aside className="col-span-2 bg-zinc-900 text-zinc-300 p-4 text-xs">
                <div className="space-y-1">
                  {['Dashboard','Generate','Templates','Approvals','Documents','Insights'].map((x, i) => (
                    <div key={x} className={i === 1 ? 'px-2 py-1.5 rounded bg-zinc-800 text-white' : 'px-2 py-1.5 hover:text-white transition-colors cursor-default'}>{x}</div>
                  ))}
                </div>
              </aside>
              <div className="col-span-10 p-6">
                <div className="grid grid-cols-4 gap-3 mb-5">
                  {[
                    { l: 'Quotes generated', v: '1,248', t: '+12%' },
                    { l: 'Conversion', v: '34.2%', t: '+1.8%' },
                    { l: 'Avg latency', v: '4.6s', t: '-12%' },
                    { l: 'Live deals', v: '87', t: 'now' },
                  ].map((m) => (
                    <div key={m.l} className="border border-zinc-200 rounded-lg p-3 bg-white">
                      <div className="text-[11px] text-zinc-500">{m.l}</div>
                      <div className="text-lg font-bold mt-1">{m.v}</div>
                      <div className="text-[10px] text-violet-600 font-medium mt-1">{m.t}</div>
                    </div>
                  ))}
                </div>
                <div className="border border-zinc-200 rounded-lg p-4 bg-white">
                  <div className="flex items-end gap-1.5 h-32">
                    {[42, 28, 56, 38, 72, 64, 88, 76, 95, 84, 110, 102].map((h, i) => (
                      <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-violet-200 to-violet-500" style={{ height: `${h}%` }} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Trust bar ────────────────────────────────────── */}
      <section className="border-y border-zinc-200 bg-zinc-50/60">
        <div className="max-w-6xl mx-auto px-6 py-7">
          <div className="text-center text-[11px] uppercase tracking-wider text-zinc-500 mb-4">
            Built on stacks teams already trust
          </div>
          <div className="flex flex-wrap justify-center gap-x-10 gap-y-2 text-sm font-semibold text-zinc-500">
            {['Salesforce', 'HubSpot', 'FastAPI', 'React', 'Postgres', 'Render'].map((x) => (
              <span key={x} className="opacity-70 hover:opacity-100 transition-opacity">{x}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Features ─────────────────────────────────────── */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-24">
        <div className="text-center mb-14">
          <div className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-2">
            Why teams pick QuoteForge
          </div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            Everything you need between "quote requested" and signed.
          </h2>
          <p className="mt-4 text-zinc-600 max-w-2xl mx-auto">
            Not another doc generator. A full quote-to-close surface for sales teams who
            actually run on Salesforce.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="group rounded-xl border border-zinc-200 p-6 bg-white hover:border-violet-300 hover:shadow-lg hover:shadow-violet-100/40 transition-all"
            >
              <div className="w-10 h-10 rounded-lg bg-violet-50 text-violet-600 flex items-center justify-center mb-4 group-hover:bg-violet-100 transition-colors">
                <Icon size={20} />
              </div>
              <h3 className="font-semibold text-zinc-900">{title}</h3>
              <p className="text-sm text-zinc-600 mt-2 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── How it works ─────────────────────────────────── */}
      <section id="how-it-works" className="bg-zinc-50 border-y border-zinc-200">
        <div className="max-w-6xl mx-auto px-6 py-24">
          <div className="text-center mb-14">
            <div className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-2">
              How it works
            </div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              From install to first quote in under 10 minutes.
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-5">
            {STEPS.map((s) => (
              <div key={s.n} className="rounded-xl border border-zinc-200 p-7 bg-white relative">
                <div className="text-[42px] font-bold text-violet-200 leading-none mb-3 tracking-tight">{s.n}</div>
                <h3 className="text-lg font-semibold text-zinc-900">{s.title}</h3>
                <p className="text-sm text-zinc-600 mt-2 leading-relaxed" dangerouslySetInnerHTML={{ __html: s.body }} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Integration callout ──────────────────────────── */}
      <section id="integration" className="max-w-6xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-2">
            Salesforce-native
          </div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight leading-tight">
            One-click install.<br />
            Real OAuth. Real Connected App.
          </h2>
          <p className="mt-5 text-zinc-600 leading-relaxed">
            QuoteForge ships as a proper Salesforce Connected App — not a webhook glue
            job. Your admin installs the package, clicks Connect, approves the OAuth
            prompt, and we're authorised to read opportunities, push quotes, and
            attach signed proposals to the right record.
          </p>
          <ul className="mt-6 space-y-3">
            {[
              'OAuth 2.0 Web Server Flow + PKCE — same standard Slack and Notion use',
              'Refresh tokens stored encrypted at rest (Fernet)',
              'Per-org granularity — connect prod and sandbox independently',
              'Disconnect revokes the token at Salesforce, no orphaned access',
            ].map((line) => (
              <li key={line} className="flex items-start gap-2.5 text-sm text-zinc-700">
                <span className="w-5 h-5 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Check size={12} strokeWidth={3} />
                </span>
                {line}
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-2xl border border-zinc-200 bg-white p-7 shadow-xl shadow-violet-100/30">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2.5">
              <span className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center text-violet-600">
                <Lock size={16} />
              </span>
              <div>
                <div className="font-semibold text-zinc-900 text-sm">QuoteForge — Salesforce Connection</div>
                <div className="text-xs text-zinc-500">Status pinned to your dashboard</div>
              </div>
            </div>
            <span className="text-[10px] uppercase tracking-wide font-bold px-2 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
              Connected
            </span>
          </div>
          <div className="text-sm space-y-1.5 border-t border-zinc-200 pt-4">
            <div className="flex justify-between"><span className="text-zinc-500">Org</span><span className="font-mono text-zinc-700">00DXX0000004CXX</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">Instance</span><span className="font-mono text-zinc-700 text-xs">acme.my.salesforce.com</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">Scopes</span><span className="font-mono text-zinc-700 text-xs">api · refresh_token · offline_access</span></div>
          </div>
          <button className="mt-5 w-full px-3.5 py-2 text-sm font-semibold rounded-md bg-violet-600 text-white hover:bg-violet-700 transition-colors">
            Push next quote to Salesforce
          </button>
        </div>
      </section>

      {/* ─── Final CTA ────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <div className="rounded-2xl bg-gradient-to-br from-violet-600 to-violet-800 text-white p-10 md:p-14 text-center relative overflow-hidden">
          <div
            aria-hidden
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage: 'radial-gradient(45% 60% at 50% 0%, rgba(255,255,255,0.4), transparent 70%)',
            }}
          />
          <Zap size={28} className="mx-auto mb-4 text-violet-200" />
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">Stop hand-crafting proposals.</h2>
          <p className="mt-3 text-violet-100 max-w-xl mx-auto">
            Spin up a free workspace and have your first AI-drafted quote in your inbox
            in the next ten minutes.
          </p>
          <div className="mt-7 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/signup"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-white text-violet-700 font-semibold hover:bg-zinc-50 transition-colors"
            >
              Create workspace <ArrowRight size={16} />
            </Link>
            <Link
              to="/plans"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md border border-violet-300 text-white font-semibold hover:bg-violet-700/50 transition-colors"
            >
              Compare plans
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
