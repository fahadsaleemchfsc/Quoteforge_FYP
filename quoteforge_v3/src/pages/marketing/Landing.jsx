import { Link } from 'react-router-dom';
import {
  Sparkles, Zap, ShieldCheck, BarChart3, Workflow, FileText,
  ArrowRight, Check, Cloud, Bot, Lock, Activity, CircleCheck,
  TrendingUp, MessageSquare, Database, Globe2,
} from 'lucide-react';
import MarketingNav from '@/components/marketing/MarketingNav';
import MarketingFooter from '@/components/marketing/MarketingFooter';
import {
  FloatingOrbs, GlassCard, TiltCard, Reveal, AnimatedCounter,
} from '@/components/marketing/visuals';

/**
 * Public landing page (/lp) — "premium SaaS product" surface.
 * Pure-CSS 3D + floating + scroll-reveal (see marketing.css).
 */

const FEATURES = [
  {
    icon: Bot,
    title: 'AI-drafted in seconds',
    body: 'Pull a deal from Salesforce, hit Generate, get a brand-styled proposal in under 5 seconds.',
  },
  {
    icon: FileText,
    title: 'Master template, one truth',
    body: 'Set your HTML once. Every quote across every rep renders from it, capped at 2 pages.',
  },
  {
    icon: ShieldCheck,
    title: 'Guardrails that say no',
    body: 'Hard caps on discount %, approval thresholds, compliance by region. AI cannot violate them.',
  },
  {
    icon: Cloud,
    title: 'One-click Salesforce install',
    body: 'Connected App OAuth — admin clicks Connect, approves on Salesforce, done.',
  },
  {
    icon: BarChart3,
    title: 'Win-probability built in',
    body: 'Per-tenant LightGBM model. Every quote ships with a confidence interval, not a guess.',
  },
  {
    icon: Workflow,
    title: 'Buyer-room negotiation',
    body: 'Share a link. Mediator AI respects your guardrails. Agreed offers hit your approval queue.',
  },
];

const STEPS = [
  { n: '01', title: 'Connect Salesforce',     body: 'Click Connect, approve the Connected App. Opportunities + accounts stream in. ~30 seconds.' },
  { n: '02', title: 'Set your master template', body: 'Drop your HTML & CSS, or use the included 2-page template. Live preview, instant save.' },
  { n: '03', title: 'Generate & push back',     body: 'Rep picks a deal, hits Generate, reviews the PDF, ships. Approved quotes write back to SF Quote.' },
];

export default function Landing() {
  return (
    <div className="marketing bg-white text-zinc-900">
      <MarketingNav />

      {/* ═══ HERO ═══════════════════════════════════════════════ */}
      <section className="relative overflow-hidden">
        {/* Layered background: dotted grid → animated mesh → blurred orbs */}
        <div aria-hidden className="absolute inset-0 m-grid-bg" />
        <div aria-hidden className="m-mesh" />
        <FloatingOrbs
          orbs={[
            { x: '-15%', y: '-25%', size: 560, color: 'radial-gradient(circle, #8B5CF6, transparent 70%)', delay: '0s'   },
            { x: '55%',  y: '-10%', size: 460, color: 'radial-gradient(circle, #D946EF, transparent 70%)', delay: '-7s'  },
            { x: '25%',  y: '55%',  size: 420, color: 'radial-gradient(circle, #06B6D4, transparent 70%)', delay: '-14s' },
          ]}
        />

        <div className="relative z-10 max-w-6xl mx-auto px-6 pt-20 pb-12 md:pt-28 md:pb-16 text-center">
          <Reveal>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/70 backdrop-blur border border-violet-200 text-violet-700 text-xs font-medium mb-6 shadow-sm">
              <span className="m-pulse-dot" /> Salesforce Connected App — live in beta
            </div>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="text-4xl md:text-7xl font-bold tracking-tight leading-[1.02]">
              Quote in seconds.<br />
              <span className="m-gradient-text">Close on your terms.</span>
            </h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="mt-7 text-lg md:text-xl text-zinc-600 max-w-2xl mx-auto leading-relaxed">
              QuoteForge turns Salesforce opportunities into branded,
              guardrail-checked proposals in under five seconds. The AI drafts.
              You keep the rules.
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                to="/signup"
                className="group inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-zinc-900 text-white font-semibold hover:bg-zinc-800 transition-all shadow-lg shadow-violet-200/40 hover:shadow-xl hover:shadow-violet-300/50 hover:-translate-y-0.5"
              >
                Start free
                <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <Link
                to="/plans"
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-md bg-white/80 backdrop-blur text-zinc-900 font-semibold border border-zinc-300 hover:border-zinc-400 hover:bg-white transition-all"
              >
                See pricing
              </Link>
            </div>
          </Reveal>
          <Reveal delay={320}>
            <div className="mt-6 text-xs text-zinc-500">
              Free forever for the first workspace · No credit card · Sets up in under 10 minutes
            </div>
          </Reveal>
        </div>

        {/* ─── 3D tilted product stack with orbiting float cards ─── */}
        <div className="relative max-w-6xl mx-auto px-6 pb-28 md:pb-36 m-stage">
          <Reveal delay={420}>
            <div className="relative">
              {/* Floating "notification" card — top-left */}
              <div
                className="hidden md:block absolute -left-4 lg:-left-10 top-8 z-20 m-float--slow"
                style={{ transform: 'translateZ(60px)' }}
              >
                <GlassCard className="px-4 py-3 w-[260px]">
                  <div className="flex items-center gap-2.5">
                    <span className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
                      <CircleCheck size={16} />
                    </span>
                    <div>
                      <div className="text-[12px] font-semibold text-zinc-900">Quote DOC-2467 pushed</div>
                      <div className="text-[10px] text-zinc-500">Acme Corp · $42,500 · just now</div>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* Floating "win probability" card — top-right */}
              <div
                className="hidden md:block absolute -right-4 lg:-right-12 top-16 z-20 m-float"
                style={{ transform: 'translateZ(80px)', animationDelay: '-3s' }}
              >
                <GlassCard className="p-4 w-[230px]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">Win probability</span>
                    <TrendingUp size={12} className="text-emerald-600" />
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-2xl font-bold text-zinc-900">82%</span>
                    <span className="text-[11px] text-emerald-600 font-semibold">+14%</span>
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
                    <div className="h-full w-[82%] rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500" />
                  </div>
                </GlassCard>
              </div>

              {/* Floating "guardrail" card — bottom-left */}
              <div
                className="hidden lg:block absolute -left-8 bottom-10 z-20 m-float--fast"
                style={{ transform: 'translateZ(40px)', animationDelay: '-5s' }}
              >
                <GlassCard className="px-4 py-3 w-[250px]">
                  <div className="flex items-center gap-2.5">
                    <span className="w-8 h-8 rounded-lg bg-violet-100 text-violet-700 flex items-center justify-center">
                      <ShieldCheck size={16} />
                    </span>
                    <div>
                      <div className="text-[12px] font-semibold text-zinc-900">Discount cap held</div>
                      <div className="text-[10px] text-zinc-500">Max 15% enforced · AI requested 22%</div>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* Floating "buyer room" card — bottom-right */}
              <div
                className="hidden lg:block absolute -right-6 bottom-20 z-20 m-float--slow"
                style={{ transform: 'translateZ(50px)', animationDelay: '-2s' }}
              >
                <GlassCard className="px-4 py-3 w-[240px]">
                  <div className="flex items-center gap-2.5">
                    <span className="w-8 h-8 rounded-lg bg-cyan-100 text-cyan-700 flex items-center justify-center">
                      <MessageSquare size={16} />
                    </span>
                    <div>
                      <div className="text-[12px] font-semibold text-zinc-900">Buyer countered</div>
                      <div className="text-[10px] text-zinc-500">Mediator AI replied · 3 turns</div>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* The product mockup itself, 3D-tilted */}
              <TiltCard className="rounded-2xl overflow-hidden shadow-2xl shadow-violet-300/50 bg-white border border-zinc-200">
                <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-zinc-200 bg-zinc-50">
                  <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
                  <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
                  <span className="w-2.5 h-2.5 rounded-full bg-zinc-300" />
                  <span className="text-[11px] text-zinc-500 ml-3">app.quoteforge.io · /dashboard</span>
                  <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                    <span className="m-pulse-dot" /> live
                  </span>
                </div>
                <div className="grid grid-cols-12 min-h-[380px]">
                  <aside className="col-span-2 bg-zinc-900 text-zinc-300 p-4 text-xs">
                    <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3 font-bold">Operate</div>
                    <div className="space-y-0.5">
                      {[
                        ['Dashboard', false],
                        ['Generate',  true ],
                        ['Templates', false],
                        ['Approvals', false],
                        ['Documents', false],
                      ].map(([label, active]) => (
                        <div
                          key={label}
                          className={
                            active
                              ? 'px-2 py-1.5 rounded bg-violet-500/20 text-white font-semibold'
                              : 'px-2 py-1.5 hover:text-white transition-colors cursor-default'
                          }
                        >
                          {label}
                        </div>
                      ))}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-zinc-500 mt-5 mb-3 font-bold">Predict</div>
                    <div className="space-y-0.5">
                      {['Insights', 'ICP', 'Negotiations'].map((label) => (
                        <div key={label} className="px-2 py-1.5 cursor-default">{label}</div>
                      ))}
                    </div>
                  </aside>
                  <div className="col-span-10 p-6 bg-gradient-to-br from-white to-zinc-50">
                    <div className="grid grid-cols-4 gap-3 mb-5">
                      {[
                        { l: 'Quotes generated', v: '1,248', t: '+12%' },
                        { l: 'Conversion',       v: '34.2%', t: '+1.8%' },
                        { l: 'Avg latency',      v: '4.6s',  t: '−12%' },
                        { l: 'Live deals',       v: '87',    t: 'now'   },
                      ].map((m) => (
                        <div key={m.l} className="border border-zinc-200 rounded-lg p-3 bg-white shadow-sm">
                          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{m.l}</div>
                          <div className="text-lg font-bold mt-1 text-zinc-900">{m.v}</div>
                          <div className="text-[10px] text-violet-600 font-medium mt-1">{m.t}</div>
                        </div>
                      ))}
                    </div>
                    <div className="border border-zinc-200 rounded-lg p-4 bg-white shadow-sm">
                      <div className="flex items-end gap-1.5 h-36">
                        {[42, 28, 56, 38, 72, 64, 88, 76, 95, 84, 110, 102].map((h, i) => (
                          <div
                            key={i}
                            className="flex-1 rounded-t bg-gradient-to-t from-violet-300 via-violet-500 to-fuchsia-500 transition-all hover:opacity-80"
                            style={{ height: `${h}%` }}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </TiltCard>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ═══ TRUST BAR ═════════════════════════════════════════════ */}
      <section className="border-y border-zinc-200 bg-zinc-50/60">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <Reveal>
            <div className="text-center text-[11px] uppercase tracking-wider text-zinc-500 mb-4 font-semibold">
              Built on stacks teams already trust
            </div>
            <div className="flex flex-wrap justify-center gap-x-12 gap-y-3 text-sm font-semibold text-zinc-500">
              {['Salesforce', 'HubSpot', 'FastAPI', 'React', 'Postgres', 'Render'].map((x, i) => (
                <span
                  key={x}
                  className="opacity-60 hover:opacity-100 transition-opacity tracking-tight"
                  style={{ animation: `m-bob 9s ease-in-out infinite`, animationDelay: `${-i}s` }}
                >
                  {x}
                </span>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ═══ STATS ═════════════════════════════════════════════════ */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {[
            { label: 'Avg generate time', to: 5,    suffix: 's',   sub: 'down from 40 min hand-prep' },
            { label: 'Quote pages',       to: 2,                   sub: 'capped by master template'  },
            { label: 'Win-lift on Pro',   to: 18,   suffix: '%',   sub: 'per-tenant model lift'      },
            { label: 'Setup minutes',     to: 10,                  sub: 'Render deploy → first quote'},
          ].map((s, i) => (
            <Reveal key={s.label} delay={i * 80}>
              <div className="text-4xl md:text-5xl font-bold tracking-tight m-gradient-text">
                <AnimatedCounter to={s.to} suffix={s.suffix || ''} />
              </div>
              <div className="text-sm font-semibold text-zinc-900 mt-2">{s.label}</div>
              <div className="text-xs text-zinc-500 mt-1">{s.sub}</div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ═══ FEATURES ══════════════════════════════════════════════ */}
      <section id="features" className="relative max-w-6xl mx-auto px-6 py-24">
        <Reveal>
          <div className="text-center mb-14">
            <div className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-2">
              Why teams pick QuoteForge
            </div>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
              Everything you need between<br />
              <span className="m-gradient-text">"quote requested" and signed.</span>
            </h2>
          </div>
        </Reveal>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map(({ icon: Icon, title, body }, i) => (
            <Reveal key={title} delay={i * 60}>
              <div
                className="group h-full rounded-2xl border border-zinc-200 p-6 bg-white hover:border-violet-300 hover:shadow-xl hover:shadow-violet-100/60 transition-all hover:-translate-y-1"
              >
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-100 to-violet-200 text-violet-700 flex items-center justify-center mb-4 group-hover:scale-110 group-hover:rotate-3 transition-transform">
                  <Icon size={20} />
                </div>
                <h3 className="font-semibold text-zinc-900">{title}</h3>
                <p className="text-sm text-zinc-600 mt-2 leading-relaxed">{body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ═══ HOW IT WORKS ══════════════════════════════════════════ */}
      <section id="how-it-works" className="relative bg-gradient-to-br from-zinc-900 via-zinc-900 to-violet-950 text-white overflow-hidden">
        <FloatingOrbs
          orbs={[
            { x: '-10%', y: '-20%', size: 480, color: 'radial-gradient(circle, rgba(139,92,246,.7), transparent 70%)', delay: '0s'  },
            { x: '70%',  y: '60%',  size: 380, color: 'radial-gradient(circle, rgba(217,70,239,.6), transparent 70%)', delay: '-8s' },
          ]}
        />
        <div className="relative max-w-6xl mx-auto px-6 py-24">
          <Reveal>
            <div className="text-center mb-14">
              <div className="text-xs font-semibold uppercase tracking-wider text-violet-300 mb-2">
                How it works
              </div>
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight">
                From install to first quote<br />in under 10 minutes.
              </h2>
            </div>
          </Reveal>

          <div className="grid md:grid-cols-3 gap-5">
            {STEPS.map((s, i) => (
              <Reveal key={s.n} delay={i * 100}>
                <GlassCard tone="dark" className="p-7 h-full relative overflow-hidden">
                  <div className="text-[64px] font-bold leading-none mb-3 tracking-tight m-gradient-text">{s.n}</div>
                  <h3 className="text-lg font-semibold">{s.title}</h3>
                  <p className="text-sm text-zinc-300 mt-2 leading-relaxed">{s.body}</p>
                </GlassCard>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ INTEGRATION ═══════════════════════════════════════════ */}
      <section id="integration" className="relative max-w-6xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-12 items-center">
        <Reveal>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-violet-600 mb-2">
              Salesforce-native
            </div>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight leading-tight">
              One-click install.<br />
              <span className="m-gradient-text">Real OAuth.</span> Real Connected App.
            </h2>
            <p className="mt-5 text-zinc-600 leading-relaxed">
              QuoteForge ships as a proper Salesforce Connected App — not a webhook
              glue job. Your admin installs the package, clicks Connect, approves
              the OAuth prompt, and QuoteForge is authorised to read opportunities,
              push quotes, and attach signed proposals to the right record.
            </p>
            <ul className="mt-6 space-y-3">
              {[
                'OAuth 2.0 Web Server Flow + PKCE — the same standard Slack and Notion use',
                'Refresh tokens stored encrypted at rest (Fernet)',
                'Per-org granularity — connect prod and sandbox independently',
                'Disconnect revokes the token at Salesforce — no orphaned access',
              ].map((line) => (
                <li key={line} className="flex items-start gap-2.5 text-sm text-zinc-700">
                  <span className="w-5 h-5 rounded-full bg-gradient-to-br from-violet-100 to-violet-200 text-violet-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Check size={12} strokeWidth={3} />
                  </span>
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div className="m-stage">
            <TiltCard>
              <GlassCard className="p-7 relative overflow-hidden">
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-2.5">
                    <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-100 to-violet-200 flex items-center justify-center text-violet-700">
                      <Lock size={16} />
                    </span>
                    <div>
                      <div className="font-semibold text-zinc-900 text-sm">QuoteForge — Salesforce Connection</div>
                      <div className="text-xs text-zinc-500">Pinned to your dashboard</div>
                    </div>
                  </div>
                  <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <span className="m-pulse-dot" /> Connected
                  </span>
                </div>
                <div className="text-sm space-y-1.5 border-t border-zinc-200/70 pt-4">
                  <div className="flex justify-between"><span className="text-zinc-500">Org</span><span className="font-mono text-zinc-700">00DXX0000004CXX</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">Instance</span><span className="font-mono text-zinc-700 text-xs">acme.my.salesforce.com</span></div>
                  <div className="flex justify-between"><span className="text-zinc-500">Scopes</span><span className="font-mono text-zinc-700 text-xs">api · refresh_token · offline_access</span></div>
                </div>
                <button className="mt-5 w-full px-3.5 py-2.5 text-sm font-semibold rounded-md bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white hover:from-violet-500 hover:to-fuchsia-500 transition-all shadow-lg shadow-violet-200/60">
                  Push next quote to Salesforce
                </button>
              </GlassCard>
            </TiltCard>

            {/* Floating data tag */}
            <div
              className="hidden md:block absolute -top-4 -right-4 m-float"
              style={{ animationDelay: '-2s' }}
            >
              <GlassCard className="px-3 py-2 text-xs">
                <div className="flex items-center gap-1.5">
                  <Database size={12} className="text-emerald-600" />
                  <span className="font-mono text-zinc-700">142 opps synced</span>
                </div>
              </GlassCard>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ═══ FINAL CTA ═════════════════════════════════════════════ */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <Reveal>
          <div className="relative rounded-3xl overflow-hidden bg-gradient-to-br from-violet-600 via-violet-700 to-fuchsia-700 text-white p-10 md:p-16 text-center">
            <FloatingOrbs
              orbs={[
                { x: '-10%', y: '-30%', size: 360, color: 'radial-gradient(circle, rgba(255,255,255,.35), transparent 70%)', delay: '0s'   },
                { x: '70%',  y: '40%',  size: 320, color: 'radial-gradient(circle, rgba(255,255,255,.25), transparent 70%)', delay: '-6s'  },
              ]}
            />
            <div className="relative">
              <Zap size={32} className="mx-auto mb-4 text-violet-200" />
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Stop hand-crafting proposals.</h2>
              <p className="mt-4 text-violet-100 max-w-xl mx-auto text-lg">
                Spin up a free workspace and have your first AI-drafted quote in your inbox
                in the next ten minutes.
              </p>
              <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
                <Link
                  to="/signup"
                  className="group inline-flex items-center justify-center gap-2 px-6 py-3 rounded-md bg-white text-violet-700 font-semibold hover:bg-zinc-50 transition-all shadow-xl hover:-translate-y-0.5"
                >
                  Create workspace
                  <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                </Link>
                <Link
                  to="/plans"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-md border border-white/40 text-white font-semibold hover:bg-white/10 transition-all"
                >
                  Compare plans
                </Link>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      <MarketingFooter />
    </div>
  );
}
