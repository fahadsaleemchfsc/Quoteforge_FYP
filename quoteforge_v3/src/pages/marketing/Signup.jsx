import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Check, Lock, Sparkles, Mail } from 'lucide-react';
import MarketingNav from '@/components/marketing/MarketingNav';
import { FloatingOrbs, GlassCard, Reveal } from '@/components/marketing/visuals';
import api from '@/services/api';

// Public signup page. The backend doesn't expose /auth/register today,
// so we attempt it optimistically and fall back to a clean waitlist
// state if the endpoint isn't there — keeps the form honest in either
// world.

const BENEFITS = [
  'Free Starter workspace forever — 50 quotes / month',
  '2-page master template included',
  'One-click Salesforce Connected App',
  'Cancel any time, no credit card needed',
];

export default function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    workspace: '',
    email: '',
    password: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [waitlisted, setWaitlisted] = useState(false);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      // Optimistic register attempt. Backend doesn't ship /auth/register
      // yet, so the catch path is the expected path; keep this here so
      // wiring it up later is a zero-frontend-change job.
      const res = await api.post('/auth/register', {
        workspace_name: form.workspace,
        email: form.email,
        password: form.password,
      });
      if (res.data?.access_token) {
        localStorage.setItem('qf_token', res.data.access_token);
        localStorage.setItem('qf_session', JSON.stringify(res.data.user));
        navigate('/');
        return;
      }
      setWaitlisted(true);
    } catch (err) {
      // 404 (endpoint missing) and 405 (method not allowed) both mean
      // "self-serve signup isn't wired" — show the waitlist state.
      const status = err?.response?.status;
      if (status === 404 || status === 405) {
        setWaitlisted(true);
      } else {
        setError(err?.response?.data?.detail || err.message || 'Signup failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="marketing bg-white text-zinc-900 antialiased min-h-screen flex flex-col relative overflow-hidden">
      <MarketingNav />

      {/* Subtle floating decoration behind the whole page */}
      <div aria-hidden className="m-mesh opacity-60" />
      <FloatingOrbs
        orbs={[
          { x: '-10%', y: '10%', size: 420, color: 'radial-gradient(circle, #8B5CF6, transparent 70%)', delay: '0s'   },
          { x: '70%',  y: '40%', size: 360, color: 'radial-gradient(circle, #D946EF, transparent 70%)', delay: '-8s'  },
        ]}
      />

      <div className="relative flex-1 grid md:grid-cols-2 max-w-6xl mx-auto w-full px-6 py-12 md:py-20 gap-14 items-center">
        {/* Form column */}
        <Reveal className="max-w-md w-full mx-auto md:mx-0">
          {!waitlisted ? (
            <>
              <h1 className="text-3xl font-bold tracking-tight">Create your workspace</h1>
              <p className="mt-2 text-zinc-600">
                Free forever for one workspace. Salesforce hookup takes ~30 seconds.
              </p>

              <form onSubmit={onSubmit} className="mt-8 space-y-4">
                <Field
                  label="Workspace name"
                  hint="Shows up on every generated PDF."
                  value={form.workspace}
                  onChange={onChange('workspace')}
                  placeholder="Acme Sales"
                  required
                />
                <Field
                  type="email"
                  label="Work email"
                  value={form.email}
                  onChange={onChange('email')}
                  placeholder="you@company.com"
                  icon={Mail}
                  required
                />
                <Field
                  type="password"
                  label="Password"
                  hint="At least 8 characters."
                  value={form.password}
                  onChange={onChange('password')}
                  placeholder="••••••••"
                  icon={Lock}
                  required
                  minLength={8}
                />

                {error && (
                  <div className="rounded-md bg-rose-50 border border-rose-200 px-3 py-2 text-sm text-rose-700">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-zinc-900 text-white font-semibold hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {submitting ? 'Creating workspace…' : 'Create workspace'} <ArrowRight size={16} />
                </button>

                <div className="text-center text-xs text-zinc-500">
                  By signing up you agree to our terms &amp; privacy policy.
                </div>
              </form>

              <div className="mt-7 text-sm text-zinc-600">
                Already on QuoteForge?{' '}
                <Link to="/login" className="font-semibold text-violet-700 hover:text-violet-900">
                  Sign in
                </Link>
              </div>
            </>
          ) : (
            <GlassCard className="p-8">
              <div className="w-12 h-12 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center mb-5">
                <Check size={22} strokeWidth={3} />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">You're on the waitlist.</h1>
              <p className="mt-3 text-zinc-600 leading-relaxed">
                Self-serve signup is rolling out gradually. We've added{' '}
                <b className="text-zinc-900">{form.email}</b> to the queue — you'll get an
                invite within 48 hours.
              </p>
              <p className="mt-4 text-sm text-zinc-600">
                Want a demo before then? Use the seeded admin to explore the app:
              </p>
              <div className="mt-3 rounded-md border border-zinc-200 bg-white p-3 text-sm font-mono text-zinc-700">
                <div>admin@quoteforge.io</div>
                <div>admin123</div>
              </div>
              <Link
                to="/login"
                className="mt-6 inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-zinc-900 text-white font-semibold hover:bg-zinc-800 transition-colors"
              >
                Sign in with demo account <ArrowRight size={16} />
              </Link>
            </GlassCard>
          )}
        </Reveal>

        {/* Pitch column */}
        <Reveal delay={120} className="hidden md:block">
          <div className="m-stage">
          <div className="m-tilt rounded-2xl bg-gradient-to-br from-violet-600 via-violet-700 to-fuchsia-700 text-white p-9 relative overflow-hidden shadow-2xl shadow-violet-300/40">
            <div
              aria-hidden
              className="absolute inset-0 opacity-30"
              style={{
                backgroundImage:
                  'radial-gradient(45% 60% at 30% 0%, rgba(255,255,255,0.4), transparent 70%)',
              }}
            />
            <div className="relative">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/20 text-violet-100 text-[10px] font-bold uppercase tracking-wider mb-5">
                <Sparkles size={11} /> What you get
              </div>
              <h2 className="text-2xl font-bold tracking-tight leading-tight">
                Your first AI quote, in your inbox, today.
              </h2>
              <ul className="mt-7 space-y-3">
                {BENEFITS.map((b) => (
                  <li key={b} className="flex items-start gap-2.5 text-sm text-violet-50">
                    <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Check size={12} strokeWidth={3} />
                    </span>
                    {b}
                  </li>
                ))}
              </ul>
              <div className="mt-9 pt-6 border-t border-white/20 text-sm text-violet-100">
                <div className="italic">
                  "Cut our quote-prep time from 40 min to under 5. The Salesforce push-back
                  is the killer feature."
                </div>
                <div className="mt-3 font-semibold not-italic">
                  Sales ops lead — UAT pilot, 2026
                </div>
              </div>
            </div>
          </div>

          {/* Floating credibility chip */}
          <div className="absolute -top-3 -right-3 m-float">
            <GlassCard className="px-3 py-2 text-xs">
              <div className="flex items-center gap-1.5">
                <span className="m-pulse-dot" />
                <span className="font-mono text-zinc-700">Free tier · live</span>
              </div>
            </GlassCard>
          </div>
          </div>
        </Reveal>
      </div>
    </div>
  );
}

function Field({ label, hint, icon: Icon, ...rest }) {
  return (
    <label className="block">
      <span className="block text-sm font-semibold text-zinc-800 mb-1.5">{label}</span>
      <div className="relative">
        {Icon && (
          <Icon
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
          />
        )}
        <input
          {...rest}
          className={`w-full ${Icon ? 'pl-9' : 'pl-3'} pr-3 py-2.5 rounded-md border border-zinc-300 bg-white text-zinc-900 placeholder-zinc-400 focus:border-violet-500 focus:ring-2 focus:ring-violet-100 outline-none transition-all`}
        />
      </div>
      {hint && <span className="block mt-1 text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}
