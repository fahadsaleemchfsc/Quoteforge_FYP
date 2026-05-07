import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronRight, Zap, LogOut } from 'lucide-react';
import { NAV_ITEMS } from '@constants/navigation';
import { useAuth } from '@context/AuthContext';
import clsx from 'clsx';

// IDs that only admins can access
const ADMIN_ONLY_IDS = ['users', 'settings', 'pricing', 'prompts'];

export default function Sidebar({ collapsed, setCollapsed }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useAuth();

  const visibleItems = NAV_ITEMS.filter(
    (item) => isAdmin || !ADMIN_ONLY_IDS.includes(item.id)
  );

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside
      className={clsx(
        'min-h-screen bg-sidebar border-r border-sidebar-border flex flex-col flex-shrink-0 sticky top-0 z-50 transition-all duration-300',
        collapsed ? 'w-[72px]' : 'w-[260px]'
      )}
    >
      {/* ─── Logo ─── */}
      <div className={clsx(
        'border-b border-sidebar-border flex items-center gap-3 min-h-[72px]',
        collapsed ? 'px-4 py-5' : 'px-6 py-5'
      )}>
        <div className="w-9 h-9 rounded-[10px] bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center flex-shrink-0">
          <Zap size={20} className="text-white" />
        </div>
        {!collapsed && (
          <div className="overflow-hidden whitespace-nowrap">
            <div className="text-base font-bold text-slate-50 tracking-tight">QuoteForge</div>
            <div className="text-[11px] text-slate-500 font-medium">AI Quote Engine</div>
          </div>
        )}
      </div>

      {/* ─── Navigation ─── */}
      <nav className="flex-1 p-3 flex flex-col gap-1">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;

          return (
            <button
              key={item.id}
              onClick={() => navigate(item.path)}
              className={clsx(
                'flex items-center gap-3 rounded-[10px] border-none cursor-pointer w-full text-left text-sm transition-all duration-200',
                collapsed ? 'px-3.5 py-2.5 justify-center' : 'px-4 py-2.5',
                isActive
                  ? 'bg-brand-500 text-white font-semibold'
                  : 'bg-transparent text-sidebar-text hover:bg-sidebar-hover hover:text-slate-200 font-medium'
              )}
            >
              <Icon size={20} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* ─── User + Collapse ─── */}
      <div className="p-3 border-t border-sidebar-border space-y-2">
        {/* User info */}
        {!collapsed && user && (
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-[10px] bg-sidebar-hover/50">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {user.avatar}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-gray-200 truncate">{user.name}</div>
              <div className="text-[11px] text-gray-500 capitalize flex items-center gap-1">
                <span className={clsx(
                  'w-1.5 h-1.5 rounded-full',
                  user.role === 'admin' ? 'bg-red-400' : 'bg-blue-400'
                )} />
                {user.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="text-gray-500 hover:text-red-400 transition-colors p-1"
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        )}

        {collapsed && (
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center p-2.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-sidebar-hover transition-all"
            title="Sign out"
          >
            <LogOut size={18} />
          </button>
        )}

        {/* Collapse */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center gap-2 p-2 rounded-lg border border-slate-700 cursor-pointer w-full bg-sidebar-hover text-sidebar-text text-sm transition-all hover:border-brand-500 hover:text-slate-200"
        >
          <ChevronRight
            size={16}
            className="transition-transform duration-300"
            style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)' }}
          />
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
