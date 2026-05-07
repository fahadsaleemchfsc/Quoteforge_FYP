import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Eye, EyeOff, ArrowRight, Shield, User, AlertCircle } from 'lucide-react';
import { useAuth } from '@/context';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const user = await login(email, password);
      navigate(user.role === 'admin' ? '/' : '/documents');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = async (demoEmail, demoPassword) => {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setError('');
    setLoading(true);
    try {
      const user = await login(demoEmail, demoPassword);
      navigate(user.role === 'admin' ? '/' : '/documents');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* ─── Left Panel: Branding ─── */}
      <div className="hidden lg:flex lg:w-[55%] bg-gradient-to-br from-[#0f172a] via-[#1e1b4b] to-[#312e81] relative overflow-hidden flex-col justify-between p-12">
        {/* Decorative elements */}
        <div className="absolute top-0 right-0 w-[500px] h-[500px] rounded-full bg-brand-500/10 blur-3xl" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full bg-cyan-500/5 blur-2xl" />

        {/* Grid pattern */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.1) 1px, transparent 1px)`,
            backgroundSize: '60px 60px',
          }}
        />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-400 to-purple-500 flex items-center justify-center shadow-lg shadow-brand-500/25">
            <Zap size={24} color="#fff" />
          </div>
          <div>
            <div className="text-xl font-bold text-white tracking-tight">QuoteForge</div>
            <div className="text-xs text-brand-300 font-medium">AI Quote & Proposal Engine</div>
          </div>
        </div>

        {/* Main content */}
        <div className="relative z-10 max-w-md">
          <h1 className="text-4xl font-bold text-white leading-tight tracking-tight mb-4">
            Generate quotes<br />
            <span className="bg-gradient-to-r from-brand-300 to-cyan-300 bg-clip-text text-transparent">
              10x faster
            </span>{' '}
            with AI.
          </h1>
          <p className="text-base text-gray-400 leading-relaxed mb-8">
            Automate professional, compliant, and brand-consistent proposals directly within
            your CRM. Powered by RAG + LLM technology.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2.5">
            {['Salesforce', 'HubSpot', 'Custom CRM', 'SOC 2', 'GDPR', 'PPRA'].map((tag) => (
              <span
                key={tag}
                className="px-3.5 py-1.5 rounded-full text-xs font-medium bg-white/5 text-gray-300 border border-white/10 backdrop-blur-sm"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Bottom */}
        <div className="relative z-10 text-xs text-gray-500">
          FYP — Forman Christian College University © 2026
        </div>
      </div>

      {/* ─── Right Panel: Login Form ─── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-gray-50">
        <div className="w-full max-w-[420px]">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-10">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center">
              <Zap size={22} color="#fff" />
            </div>
            <span className="text-xl font-bold text-gray-900">QuoteForge</span>
          </div>

          <h2 className="text-2xl font-bold text-gray-900 tracking-tight mb-1.5">Welcome back</h2>
          <p className="text-sm text-gray-500 mb-8">Sign in to your account to continue</p>

          {/* Error message */}
          {error && (
            <div className="flex items-center gap-2.5 p-3.5 mb-6 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 animate-fade-in">
              <AlertCircle size={18} className="flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@quoteforge.io"
                required
                className="input-field w-full"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  className="input-field w-full pr-11"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" className="w-4 h-4 rounded border-gray-300 text-brand-500 focus:ring-brand-500" />
                <span className="text-sm text-gray-600">Remember me</span>
              </label>
              <button type="button" className="text-sm text-brand-600 font-medium hover:text-brand-700 transition-colors">
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              disabled={loading}
              className={`w-full flex items-center justify-center gap-2.5 py-3 px-6 rounded-xl text-sm font-semibold text-white transition-all duration-200 ${
                loading
                  ? 'bg-brand-400 cursor-not-allowed'
                  : 'bg-brand-500 hover:bg-brand-600 active:bg-brand-700 shadow-lg shadow-brand-500/25 hover:shadow-xl hover:shadow-brand-500/30'
              }`}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in...
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-8">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-gray-50 px-4 text-gray-400 font-medium">Demo Credentials</span>
            </div>
          </div>

          {/* Quick login buttons */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => quickLogin('admin@quoteforge.io', 'admin123')}
              disabled={loading}
              className="flex items-center gap-2.5 p-3.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 hover:border-brand-300 transition-all cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center group-hover:bg-red-200 transition-colors">
                <Shield size={18} className="text-red-600" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold text-gray-900">Admin</div>
                <div className="text-[11px] text-gray-400">Full access</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => quickLogin('sarah@quoteforge.io', 'user123')}
              disabled={loading}
              className="flex items-center gap-2.5 p-3.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 hover:border-brand-300 transition-all cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center group-hover:bg-blue-200 transition-colors">
                <User size={18} className="text-blue-600" />
              </div>
              <div className="text-left">
                <div className="text-sm font-semibold text-gray-900">User</div>
                <div className="text-[11px] text-gray-400">Limited access</div>
              </div>
            </button>
          </div>

          <p className="mt-6 text-center text-xs text-gray-400">
            Protected by SOC 2 & GDPR compliant infrastructure
          </p>
        </div>
      </div>
    </div>
  );
}
