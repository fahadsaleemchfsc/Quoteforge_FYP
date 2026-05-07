import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, ArrowRight, Shield, User, AlertCircle, Zap } from 'lucide-react';
import { useAuth } from '@/context';

/*
 * Editorial-Swiss split login.
 *   Left (45%): dark-always branded surface, wordmark, tagline, live-looking
 *               monospace metrics ticker at the bottom, footer.
 *   Right (55%): theme-aware surface with form, demo credential rails,
 *               monospace chips footer. No compliance anything.
 */

const METRICS_CYCLE = [
  { label: 'tokens.issued',   value: '14,293' },
  { label: 'offers.signed',   value: '891'    },
  { label: 'deals.committed', value: '142'    },
  { label: 'guardrail.blocks','value': '37'   },
  { label: 'avg.latency.ms',  value: '842'    },
];

function MetricsTicker() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % METRICS_CYCLE.length), 3000);
    return () => clearInterval(t);
  }, []);
  const m = METRICS_CYCLE[idx];
  return (
    <div className="font-mono text-[11.5px] tracking-tight" style={{ color: '#71717A' }}>
      <span style={{ color: '#52525B' }}>●</span>
      <span className="ml-2">{m.label}</span>
      <span className="mx-2" style={{ color: '#3F3F46' }}>·</span>
      <span style={{ color: '#D4D4D8' }}>{m.value}</span>
    </div>
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    localStorage.removeItem('qf_token');
    localStorage.removeItem('qf_session');
  }, []);

  async function doLogin(em, pw) {
    setError(''); setLoading(true);
    try {
      const user = await login(em, pw);
      navigate(user.role === 'admin' ? '/' : '/documents');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Left: dark branded panel (always dark, ignores theme) ── */}
      <aside
        className="hidden lg:flex flex-col justify-between p-12 relative overflow-hidden"
        style={{ width: '45%', background: '#0A0A0B', color: '#FAFAFA' }}
      >
        {/* Subtle grid texture */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            opacity: 0.035,
            backgroundImage: `linear-gradient(rgba(255,255,255,.4) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(255,255,255,.4) 1px, transparent 1px)`,
            backgroundSize: '56px 56px',
          }}
        />

        {/* Wordmark */}
        <div className="relative z-10 flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded flex items-center justify-center"
            style={{ background: '#7C3AED' }}
          >
            <Zap size={15} className="text-white" />
          </div>
          <div className="font-semibold text-[15px] tracking-tight">QuoteForge</div>
        </div>

        {/* Main copy */}
        <div className="relative z-10 max-w-md">
          <h1 className="font-semibold leading-[1.15] tracking-tight" style={{ fontSize: 32 }}>
            Deal infrastructure<br />
            for the <span style={{ color: '#A78BFA' }}>agentic&nbsp;commerce</span> era.
          </h1>
          <p className="mt-5 text-[14px] leading-relaxed max-w-[32ch]" style={{ color: '#A1A1AA' }}>
            When buyer AIs show up to negotiate, QuoteForge is where your rules
            live, your guardrails enforce, and your deals close safely.
          </p>
        </div>

        {/* Live-ish metrics + footer */}
        <div className="relative z-10 space-y-3">
          <MetricsTicker />
          <div className="text-[11px] font-mono" style={{ color: '#52525B' }}>
            FYP · Forman Christian College University · 2026
          </div>
        </div>
      </aside>

      {/* ── Right: form (theme-aware surface) ── */}
      <main
        className="flex-1 flex items-center justify-center p-8"
        style={{ background: 'var(--bg-surface)' }}
      >
        <div className="w-full max-w-[400px]">
          {/* Mobile wordmark */}
          <div className="lg:hidden flex items-center gap-2 mb-10">
            <div
              className="w-7 h-7 rounded flex items-center justify-center"
              style={{ background: 'var(--accent)' }}
            >
              <Zap size={14} className="text-white" />
            </div>
            <span className="font-semibold text-[14px] text-text-primary">QuoteForge</span>
          </div>

          <h2 className="text-[22px] font-semibold text-text-primary tracking-tight">Sign in</h2>
          <p className="text-[13px] text-text-secondary mt-1 mb-6">
            Access your deal infrastructure
          </p>

          {error && (
            <div
              className="flex items-center gap-2 p-3 mb-4 rounded text-[13px]"
              style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}
            >
              <AlertCircle size={14} className="flex-shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={(e) => { e.preventDefault(); doLogin(email, password); }} className="space-y-3.5">
            <div>
              <label className="block text-[12px] font-medium text-text-secondary mb-1">Email</label>
              <input
                type="email" required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@quoteforge.io"
                className="input-field"
                style={{ height: 40, fontSize: 13.5 }}
              />
            </div>

            <div>
              <label className="block text-[12px] font-medium text-text-secondary mb-1">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="input-field pr-10"
                  style={{ height: 40, fontSize: 13.5 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center"
              style={{ height: 40, fontSize: 13.5 }}
            >
              {loading ? 'Signing in…' : (<>Sign in <ArrowRight size={14} /></>)}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center">
              <span
                className="px-3 text-[10.5px] font-mono uppercase tracking-wider"
                style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}
              >
                Demo credentials
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => doLogin('admin@quoteforge.io', 'admin123')}
              disabled={loading}
              className="flex items-center gap-2.5 p-3 rounded border border-border bg-surface cursor-pointer transition-colors hover:bg-subtle"
            >
              <div
                className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--accent-muted)' }}
              >
                <Shield size={13} style={{ color: 'var(--accent)' }} />
              </div>
              <div className="text-left min-w-0">
                <div className="text-[12.5px] font-medium text-text-primary">Admin</div>
                <div className="text-[10.5px] text-text-muted font-mono">full access</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => doLogin('sarah@quoteforge.io', 'user123')}
              disabled={loading}
              className="flex items-center gap-2.5 p-3 rounded border border-border bg-surface cursor-pointer transition-colors hover:bg-subtle"
            >
              <div
                className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
                style={{ background: 'var(--success-muted)' }}
              >
                <User size={13} style={{ color: 'var(--success)' }} />
              </div>
              <div className="text-left min-w-0">
                <div className="text-[12.5px] font-medium text-text-primary">User</div>
                <div className="text-[10.5px] text-text-muted font-mono">limited access</div>
              </div>
            </button>
          </div>

          <div className="mt-8 flex items-center justify-center gap-3 font-mono text-[10.5px] text-text-muted">
            <span>MCP-native</span>
            <span>·</span>
            <span>Multi-CRM</span>
            <span>·</span>
            <span>Deterministic guardrails</span>
          </div>
        </div>
      </main>
    </div>
  );
}
