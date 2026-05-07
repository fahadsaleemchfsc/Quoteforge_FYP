import { useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, FileText, DollarSign, Sparkles, Users, Settings as SettingsIcon,
  Zap, Package, Clock, Shield, Brain, Link as LinkIcon, Send, Link2,
  TrendingUp,
} from 'lucide-react';
import { useAuth } from '@context/AuthContext';
import { usePendingApprovalCount } from '@hooks';
import clsx from 'clsx';

/*
 * Dense, sectioned sidebar in the operator-tool aesthetic.
 * Sidebar surface stays dark in both themes (a branded rail).
 * Navigation grouped under small-caps labels.
 */

const SECTIONS = [
  {
    id: 'operate',
    label: 'OPERATE',
    items: [
      { id: 'dashboard',    label: 'Dashboard',     path: '/',             icon: LayoutDashboard },
      { id: 'negotiations', label: 'Negotiations',  path: '/negotiations', icon: Brain },
      { id: 'approvals',    label: 'Approvals',     path: '/approvals',    icon: Clock },
      { id: 'share-links',  label: 'Buyer Links',   path: '/share-links',  icon: LinkIcon },
    ],
  },
  {
    id: 'configure',
    label: 'CONFIGURE',
    items: [
      { id: 'products',   label: 'Products',   path: '/products',   icon: Package },
      { id: 'guardrails', label: 'Guardrails', path: '/guardrails', icon: Shield,     adminOnly: true },
      { id: 'pricing',    label: 'Pricing',    path: '/pricing',    icon: DollarSign, adminOnly: true },
      { id: 'prompts',    label: 'AI Prompts', path: '/prompts',    icon: Sparkles,   adminOnly: true },
      { id: 'users',      label: 'Users',      path: '/users',      icon: Users },
      { id: 'settings',   label: 'Settings',   path: '/settings',   icon: SettingsIcon, adminOnly: true },
    ],
  },
  {
    id: 'predict',
    label: 'PREDICT',
    items: [
      { id: 'insights-models', label: 'Deal Insights', path: '/insights/models', icon: TrendingUp },
      { id: 'insights-setup',  label: 'Insights Setup', path: '/insights/setup',  icon: SettingsIcon, adminOnly: true },
      { id: 'icp-builder',     label: 'ICP Builder',    path: '/icp',            icon: Shield, adminOnly: true },
    ],
  },
  {
    id: 'data',
    label: 'DATA',
    items: [
      { id: 'documents', label: 'Documents',        path: '/documents', icon: Send },
      { id: 'templates', label: 'Templates',        path: '/templates', icon: FileText },
      { id: 'crm',       label: 'CRM Integrations', path: '/crm',       icon: Link2 },
      { id: 'generate',  label: 'Generate',         path: '/generate',  icon: Zap },
    ],
  },
];

export default function Sidebar({ collapsed, setCollapsed }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const { count: pendingApprovals } = usePendingApprovalCount(true);

  const width = collapsed ? 52 : 220;

  return (
    <aside
      className="min-h-screen flex flex-col flex-shrink-0 sticky top-0 z-40 border-r"
      style={{
        width,
        background: '#0A0A0B',
        borderColor: '#27272A',
        transition: 'width 200ms ease',
      }}
    >
      {/* Wordmark */}
      <div
        className="h-14 flex items-center gap-2.5 border-b px-3.5"
        style={{ borderColor: '#27272A' }}
      >
        <div
          className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
          style={{ background: 'var(--accent)' }}
        >
          <Zap size={14} className="text-white" />
        </div>
        {!collapsed && (
          <div className="font-semibold text-[13.5px] tracking-tight" style={{ color: '#FAFAFA' }}>
            QuoteForge
          </div>
        )}
      </div>

      {/* Sections */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {SECTIONS.map((section) => {
          const visible = section.items.filter((i) => isAdmin || !i.adminOnly);
          if (!visible.length) return null;
          return (
            <div key={section.id} className="mb-3 last:mb-0">
              {!collapsed && (
                <div
                  className="px-3 pt-2 pb-1 font-mono tracking-wider text-[10px] font-medium"
                  style={{ color: '#52525B' }}
                >
                  {section.label}
                </div>
              )}
              <ul className="px-2 flex flex-col gap-0">
                {visible.map((item) => {
                  const Icon = item.icon;
                  const active = location.pathname === item.path;
                  const badge = item.id === 'approvals' && pendingApprovals > 0 ? pendingApprovals : null;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => navigate(item.path)}
                        className={clsx(
                          'w-full flex items-center gap-2.5 rounded text-left transition-colors',
                          collapsed ? 'h-8 justify-center px-0' : 'h-7 px-2.5',
                        )}
                        style={{
                          color: active ? '#FAFAFA' : '#A1A1AA',
                          background: active ? '#1E1B2E' : 'transparent',
                          borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
                          marginLeft: active ? -2 : 0,
                          paddingLeft: collapsed ? 0 : (active ? 10 : 10),
                          fontSize: 12.5,
                          fontWeight: active ? 500 : 400,
                        }}
                        onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = '#1C1C21'; }}
                        onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
                      >
                        <Icon size={15} strokeWidth={active ? 2 : 1.6} />
                        {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
                        {!collapsed && badge != null && (
                          <span
                            className="font-mono text-[10px] font-semibold px-1.5 rounded-sm"
                            style={{
                              background: 'var(--accent-muted)',
                              color: 'var(--accent)',
                              minWidth: 18,
                              height: 15,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                          >
                            {badge}
                          </span>
                        )}
                        {collapsed && badge != null && (
                          <span
                            className="absolute w-1.5 h-1.5 rounded-full"
                            style={{ background: 'var(--accent)', top: 4, right: 4 }}
                          />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* Collapse handle */}
      <div className="p-2 border-t" style={{ borderColor: '#27272A' }}>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full h-7 rounded flex items-center justify-center text-[11px] font-mono transition-colors"
          style={{ color: '#71717A' }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#1C1C21'; e.currentTarget.style.color = '#A1A1AA'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#71717A'; }}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '▸' : '◂ COLLAPSE'}
        </button>
      </div>
    </aside>
  );
}
