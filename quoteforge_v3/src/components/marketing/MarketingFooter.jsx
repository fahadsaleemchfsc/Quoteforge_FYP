import { Link } from 'react-router-dom';
import { Zap, Github, Twitter, Linkedin } from 'lucide-react';

const COLS = [
  {
    title: 'Product',
    links: [
      { label: 'Features', to: '/lp#features' },
      { label: 'How it works', to: '/lp#how-it-works' },
      { label: 'Pricing', to: '/plans' },
      { label: 'Salesforce integration', to: '/lp#integration' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About', to: '/lp' },
      { label: 'Contact', to: 'mailto:hello@quoteforge.io' },
      { label: 'Privacy', to: '/lp' },
      { label: 'Terms', to: '/lp' },
    ],
  },
  {
    title: 'For developers',
    links: [
      { label: 'API docs', to: '/lp' },
      { label: 'Status', to: '/lp' },
      { label: 'Changelog', to: '/lp' },
      { label: 'GitHub', to: 'https://github.com' },
    ],
  },
];

export default function MarketingFooter() {
  return (
    <footer className="border-t border-zinc-200 bg-zinc-50 mt-24">
      <div className="max-w-6xl mx-auto px-6 py-14">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-10">
          <div>
            <Link to="/lp" className="flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center text-white">
                <Zap size={16} strokeWidth={2.5} />
              </span>
              <span className="font-semibold text-zinc-900 tracking-tight">QuoteForge</span>
            </Link>
            <p className="text-sm text-zinc-500 mt-3 leading-relaxed">
              AI-powered quotes &amp; proposals that close, without the copy-paste.
            </p>
            <div className="flex gap-3 mt-5">
              <a href="#" className="text-zinc-400 hover:text-zinc-700"><Twitter size={16} /></a>
              <a href="#" className="text-zinc-400 hover:text-zinc-700"><Linkedin size={16} /></a>
              <a href="#" className="text-zinc-400 hover:text-zinc-700"><Github size={16} /></a>
            </div>
          </div>
          {COLS.map((col) => (
            <div key={col.title}>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 mb-3">
                {col.title}
              </div>
              <ul className="space-y-2">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      to={l.to}
                      className="text-sm text-zinc-700 hover:text-violet-700 transition-colors"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 pt-6 border-t border-zinc-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="text-xs text-zinc-500">
            © {new Date().getFullYear()} QuoteForge. Final-year project · Forman Christian College University.
          </div>
          <div className="text-xs text-zinc-500">
            Built with FastAPI · React · Salesforce
          </div>
        </div>
      </div>
    </footer>
  );
}
