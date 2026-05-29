import { Link, useLocation } from 'react-router-dom';
import { Zap } from 'lucide-react';
import clsx from 'clsx';

// Top navigation shared across the public marketing pages (landing,
// plans, signup). Intentionally lighter than the admin TopBar — no
// theme toggle, no user menu, no command palette.
const NAV_LINKS = [
  { to: '/lp', label: 'Product' },
  { to: '/plans', label: 'Pricing' },
  { to: '/lp#how-it-works', label: 'How it works' },
];

export default function MarketingNav() {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-30 bg-white/85 backdrop-blur border-b border-zinc-200">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/lp" className="flex items-center gap-2 group">
          <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center text-white shadow-sm shadow-violet-200 group-hover:scale-105 transition-transform">
            <Zap size={16} strokeWidth={2.5} />
          </span>
          <span className="font-semibold text-zinc-900 tracking-tight text-[15px]">QuoteForge</span>
        </Link>

        <nav className="hidden md:flex items-center gap-7">
          {NAV_LINKS.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              className={clsx(
                'text-sm font-medium transition-colors',
                pathname === to.split('#')[0]
                  ? 'text-violet-700'
                  : 'text-zinc-600 hover:text-zinc-900',
              )}
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="text-sm font-medium text-zinc-700 hover:text-zinc-900 transition-colors"
          >
            Sign in
          </Link>
          <Link
            to="/signup"
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-sm font-semibold rounded-md bg-zinc-900 text-white hover:bg-zinc-800 transition-colors"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}
