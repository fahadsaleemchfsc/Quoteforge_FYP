import { useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, FileText, DollarSign, Sparkles, Users,
  Link2, Send, Settings, ChevronRight, Zap,
} from 'lucide-react';
import { NAV_ITEMS } from '@utils/constants';
import { cn } from '@utils/helpers';

// Map icon strings to actual icon components
const ICON_MAP = {
  LayoutDashboard, FileText, DollarSign, Sparkles,
  Users, Link2, Send, Settings,
};

export default function Sidebar({ collapsed, setCollapsed }) {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <aside
      className={cn(
        'min-h-screen bg-sidebar border-r border-sidebar-border flex flex-col',
        'transition-all duration-300 ease-in-out flex-shrink-0 sticky top-0 z-50',
        collapsed ? 'w-[72px]' : 'w-[260px]'
      )}
    >
      {/* ─── Logo ─── */}
      <div
        className={cn(
          'border-b border-sidebar-border flex items-center gap-3 min-h-[72px]',
          collapsed ? 'px-4 py-5' : 'px-6 py-5'
        )}
      >
        <div className="w-9 h-9 rounded-[10px] bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center flex-shrink-0">
          <Zap size={20} color="#fff" />
        </div>
        {!collapsed && (
          <div className="overflow-hidden whitespace-nowrap">
            <div className="text-base font-bold text-gray-50 tracking-tight">QuoteForge</div>
            <div className="text-[11px] text-gray-500 font-medium">AI Quote Engine</div>
          </div>
        )}
      </div>

      {/* ─── Navigation ─── */}
      <nav className="flex-1 p-3 flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const Icon = ICON_MAP[item.icon];
          const isActive = location.pathname === item.path;

          return (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              className={cn(
                'nav-item',
                isActive ? 'nav-item-active' : 'nav-item-inactive',
                collapsed && 'justify-center px-3'
              )}
            >
              <Icon size={20} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* ─── Collapse Toggle ─── */}
      <div className="p-3 border-t border-sidebar-border">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center gap-2 p-2 rounded-lg border border-gray-700
                     w-full bg-sidebar-hover text-sidebar-text text-sm cursor-pointer
                     transition-colors hover:border-brand-500 hover:text-gray-200"
        >
          <ChevronRight
            size={16}
            className={cn('transition-transform duration-300', !collapsed && 'rotate-180')}
          />
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
