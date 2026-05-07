import { useLocation } from 'react-router-dom';
import { Search, Bell, ChevronDown } from 'lucide-react';
import { PAGE_META } from '@utils/constants';

export default function TopBar() {
  const location = useLocation();
  const meta = PAGE_META[location.pathname] || { title: 'QuoteForge', subtitle: '' };

  return (
    <header className="px-8 h-[72px] flex items-center justify-between border-b border-gray-200 bg-white sticky top-0 z-40">
      {/* Left: Page title */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 tracking-tight">{meta.title}</h1>
        {meta.subtitle && (
          <p className="text-sm text-gray-500 mt-0.5">{meta.subtitle}</p>
        )}
      </div>

      {/* Right: Search, notifications, user */}
      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          />
          <input
            type="text"
            placeholder="Search..."
            className="input pl-10 pr-4 h-[38px] w-[220px] bg-gray-50 focus:bg-white"
          />
        </div>

        {/* Notification bell */}
        <button className="btn-ghost relative">
          <Bell size={18} className="text-gray-500" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 ring-2 ring-white" />
        </button>

        {/* User avatar */}
        <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors">
          <div className="w-[30px] h-[30px] rounded-lg bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center text-white text-sm font-semibold">
            A
          </div>
          <span className="text-sm font-semibold text-gray-700">Admin</span>
          <ChevronDown size={14} className="text-gray-400" />
        </div>
      </div>
    </header>
  );
}
