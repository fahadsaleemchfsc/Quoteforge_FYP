import { useState, useEffect } from 'react';
import {
  Plus, Edit3, Lock, Trash2, CheckCircle, XCircle, Shield, User,
  Eye, Activity, FileText, Clock, Search, Filter, MoreHorizontal,
} from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { useAuth } from '@/context';
import api from '@/services/api';
import clsx from 'clsx';

// ─── Mock Activity Data (visible to admin) ───────────────────
const USER_ACTIVITIES = [
  { id: 1, userId: 2, userName: 'Sarah Johnson', action: 'Generated quote', target: 'Acme Corp — Enterprise License', amount: '$45,000', time: '2 min ago', type: 'quote' },
  { id: 2, userId: 3, userName: 'Mike Rodriguez', action: 'Generated proposal', target: 'TechStart Inc — SaaS Platform', amount: '$128,000', time: '15 min ago', type: 'proposal' },
  { id: 3, userId: 5, userName: 'Lisa Kim', action: 'Generated quote', target: 'Global Traders — Consulting', amount: '$22,500', time: '1 hr ago', type: 'quote' },
  { id: 4, userId: 2, userName: 'Sarah Johnson', action: 'Delivered proposal', target: 'Nexus Systems — Infrastructure', amount: '$89,000', time: '2 hrs ago', type: 'delivery' },
  { id: 5, userId: 3, userName: 'Mike Rodriguez', action: 'Updated template', target: 'Enterprise Sales Proposal', amount: '—', time: '3 hrs ago', type: 'template' },
  { id: 6, userId: 5, userName: 'Lisa Kim', action: 'Generated quote', target: 'Pinnacle Health — Data Analytics', amount: '$67,200', time: '4 hrs ago', type: 'quote' },
  { id: 7, userId: 2, userName: 'Sarah Johnson', action: 'Generated proposal', target: 'Vertex Solutions — Cloud Migration', amount: '$230,000', time: '5 hrs ago', type: 'proposal' },
  { id: 8, userId: 3, userName: 'Mike Rodriguez', action: 'Failed generation', target: 'OmniCorp — Security Audit', amount: '$15,000', time: '6 hrs ago', type: 'error' },
];

const ROLE_PERMISSIONS = [
  { perm: 'Generate Quotes & Proposals', admin: true, user: true },
  { perm: 'View Own Documents', admin: true, user: true },
  { perm: 'View All Users\' Documents', admin: true, user: false },
  { perm: 'Manage Templates', admin: true, user: false },
  { perm: 'Configure Pricing Rules', admin: true, user: false },
  { perm: 'Manage AI Prompts', admin: true, user: false },
  { perm: 'CRM Integration Settings', admin: true, user: false },
  { perm: 'User Management', admin: true, user: false },
  { perm: 'View Activity Logs', admin: true, user: false },
  { perm: 'System Settings', admin: true, user: false },
];

const ROLE_STYLES = {
  admin: { bg: 'bg-danger-muted', text: 'text-danger', icon: Shield },
  user: { bg: 'bg-accent-muted', text: 'text-blue-800', icon: User },
};

const TYPE_COLORS = {
  quote: 'bg-brand-50 text-brand-700',
  proposal: 'bg-accent-muted text-accent',
  delivery: 'bg-success-muted text-success',
  template: 'bg-warning-muted text-warning',
  error: 'bg-danger-muted text-danger',
};

export default function Users() {
  const { user: currentUser, isAdmin, getAllUsers } = useAuth();
  const [allUsers, setAllUsers] = useState([]);
  const [tab, setTab] = useState('users');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const load = async () => {
      const users = await getAllUsers();
      setAllUsers(users);
    };
    load();
  }, [getAllUsers]);

  const filteredUsers = allUsers.filter((u) =>
    u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ─── Admin View ────────────────────────────────────────────
  if (isAdmin) {
    return (
      <div className="page-enter">
        {/* Tabs */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex gap-2">
            {[
              { id: 'users', label: 'All Users', count: allUsers.length },
              { id: 'activity', label: 'Activity Log', count: USER_ACTIVITIES.length },
              { id: 'roles', label: 'Roles & Permissions' },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'px-4 py-2 rounded border text-sm font-medium transition-all',
                  tab === t.id
                    ? 'border-brand-500 bg-brand-50 text-brand-700'
                    : 'border-border bg-white text-text-secondary hover:bg-subtle'
                )}
              >
                {t.label} {t.count != null && <span className="ml-1 text-xs opacity-60">({t.count})</span>}
              </button>
            ))}
          </div>
          <button className="btn-primary"><Plus size={18} /> Invite User</button>
        </div>

        {/* ── Users Tab ── */}
        {tab === 'users' && (
          <>
            {/* Search */}
            <div className="relative mb-4">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search users by name or email..."
                className="input-field pl-10 w-full max-w-md"
              />
            </div>

            <div className="card overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-subtle">
                    {['User', 'Role', 'Department', 'Quotes Generated', 'Status', 'Last Login', 'Actions'].map((h) => (
                      <th key={h} className="table-header">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u, i) => {
                    const rs = ROLE_STYLES[u.role];
                    const RoleIcon = rs.icon;
                    return (
                      <tr key={u.id} className="table-row " >
                        <td className="table-cell">
                          <div className="flex items-center gap-3.5">
                            <div
                              className="w-8 h-8 rounded flex items-center justify-center text-sm font-bold"
                              style={{ background: `hsl(${u.id * 55}, 60%, 92%)`, color: `hsl(${u.id * 55}, 60%, 40%)` }}
                            >
                              {u.avatar}
                            </div>
                            <div>
                              <div className="text-sm font-semibold text-text-primary">{u.name}</div>
                              <div className="text-xs text-text-muted">{u.email}</div>
                            </div>
                          </div>
                        </td>
                        <td className="table-cell">
                          <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold', rs.bg, rs.text)}>
                            <RoleIcon size={12} />
                            {u.role === 'admin' ? 'Admin' : 'User'}
                          </span>
                        </td>
                        <td className="table-cell text-sm text-text-secondary">{u.department}</td>
                        <td className="table-cell">
                          <span className="text-sm font-semibold text-text-primary">{u.quotesGenerated}</span>
                        </td>
                        <td className="table-cell"><StatusBadge status={u.status} /></td>
                        <td className="table-cell text-sm text-text-secondary">{u.lastLogin}</td>
                        <td className="table-cell">
                          <div className="flex gap-1.5">
                            <button className="icon-btn" title="View details"><Eye size={14} className="text-text-secondary" /></button>
                            <button className="icon-btn" title="Edit user"><Edit3 size={14} className="text-text-secondary" /></button>
                            <button className="icon-btn" title="Reset password"><Lock size={14} className="text-text-secondary" /></button>
                            {u.id !== currentUser?.id && (
                              <button className="icon-btn hover:!border-red-300 hover:!bg-danger-muted" title="Deactivate">
                                <Trash2 size={14} className="text-red-400" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* ── Activity Log Tab ── */}
        {tab === 'activity' && (
          <div className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-brand-500" />
                <h3 className="text-sm font-bold text-text-primary">All User Activity</h3>
              </div>
              <button className="btn-secondary text-xs"><Filter size={13} /> Filter</button>
            </div>
            <div className="divide-y divide-subtle">
              {USER_ACTIVITIES.map((act, i) => (
                <div
                  key={act.id}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-subtle/50 transition-colors "
                  
                >
                  {/* User avatar */}
                  <div
                    className="w-7 h-7 rounded flex items-center justify-center text-xs font-bold flex-shrink-0"
                    style={{ background: `hsl(${act.userId * 55}, 60%, 92%)`, color: `hsl(${act.userId * 55}, 60%, 40%)` }}
                  >
                    {act.userName.split(' ').map((n) => n[0]).join('')}
                  </div>

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-text-primary">
                      <span className="font-semibold">{act.userName}</span>
                      <span className="text-text-secondary"> {act.action}</span>
                    </div>
                    <div className="text-xs text-text-muted truncate">{act.target}</div>
                  </div>

                  {/* Type badge */}
                  <span className={clsx('px-2.5 py-1 rounded text-xs font-medium capitalize flex-shrink-0', TYPE_COLORS[act.type])}>
                    {act.type}
                  </span>

                  {/* Amount */}
                  <span className="text-sm font-semibold text-text-primary w-24 text-right flex-shrink-0">{act.amount}</span>

                  {/* Time */}
                  <span className="text-xs text-text-muted w-20 text-right flex-shrink-0">{act.time}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Roles Tab ── */}
        {tab === 'roles' && (
          <div className="grid grid-cols-3 gap-4">
            {/* Permissions Matrix */}
            <div className="col-span-2 card p-5">
              <h3 className="text-[13px] font-bold text-text-primary mb-4">Role Permissions Matrix</h3>
              <table className="w-full">
                <thead>
                  <tr className="bg-subtle">
                    <th className="table-header">Permission</th>
                    <th className="table-header text-center">
                      <span className="inline-flex items-center gap-1.5"><Shield size={12} /> Admin</span>
                    </th>
                    <th className="table-header text-center">
                      <span className="inline-flex items-center gap-1.5"><User size={12} /> User</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ROLE_PERMISSIONS.map((row) => (
                    <tr key={row.perm} className="border-t border-border">
                      <td className="table-cell font-medium text-text-primary">{row.perm}</td>
                      <td className="table-cell text-center">
                        {row.admin ? <CheckCircle size={18} className="text-success inline" /> : <XCircle size={18} className="text-muted inline" />}
                      </td>
                      <td className="table-cell text-center">
                        {row.user ? <CheckCircle size={18} className="text-success inline" /> : <XCircle size={18} className="text-muted inline" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Role Summary */}
            <div className="space-y-5">
              <div className="card p-4">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded bg-danger-muted flex items-center justify-center">
                    <Shield size={20} className="text-danger" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-text-primary">Admin Role</h4>
                    <p className="text-xs text-text-secondary">{allUsers.filter((u) => u.role === 'admin').length} users</p>
                  </div>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">
                  Full system access. Can manage all users, configure CRM integrations, pricing rules,
                  AI prompts, templates, and view all activity logs and generated documents.
                </p>
              </div>

              <div className="card p-4">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded bg-accent-muted flex items-center justify-center">
                    <User size={20} className="text-accent" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-text-primary">User Role</h4>
                    <p className="text-xs text-text-secondary">{allUsers.filter((u) => u.role === 'user').length} users</p>
                  </div>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">
                  Limited access. Can generate quotes and proposals, view and download their own
                  documents. Cannot manage system configuration or view other users' data.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ─── User (non-admin) View ─────────────────────────────────
  return (
    <div className="page-enter">
      <div className="max-w-2xl">
        {/* Profile card */}
        <div className="card p-5 mb-4">
          <div className="flex items-center gap-4 mb-4">
            <div
              className="w-12 h-12 rounded flex items-center justify-center text-lg font-bold"
              style={{ background: `hsl(${currentUser?.id * 55}, 60%, 92%)`, color: `hsl(${currentUser?.id * 55}, 60%, 40%)` }}
            >
              {currentUser?.avatar}
            </div>
            <div>
              <h2 className="text-lg font-bold text-text-primary">{currentUser?.name}</h2>
              <p className="text-sm text-text-secondary">{currentUser?.email}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold bg-accent-muted text-blue-800">
                  <User size={12} /> User
                </span>
                <span className="text-xs text-text-muted">• {currentUser?.department}</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 rounded bg-subtle text-center">
              <div className="text-2xl font-bold text-text-primary">{currentUser?.quotesGenerated}</div>
              <div className="text-xs text-text-secondary">Quotes Generated</div>
            </div>
            <div className="p-4 rounded bg-subtle text-center">
              <div className="text-2xl font-bold text-text-primary">12</div>
              <div className="text-xs text-text-secondary">This Month</div>
            </div>
            <div className="p-4 rounded bg-subtle text-center">
              <div className="text-2xl font-bold text-success">89%</div>
              <div className="text-xs text-text-secondary">Delivery Rate</div>
            </div>
          </div>
        </div>

        {/* Permissions info */}
        <div className="card p-5">
          <h3 className="text-[13px] font-bold text-text-primary mb-4">Your Permissions</h3>
          <div className="space-y-3">
            {ROLE_PERMISSIONS.map((row) => (
              <div key={row.perm} className="flex items-center gap-3">
                {row.user ? (
                  <CheckCircle size={16} className="text-success flex-shrink-0" />
                ) : (
                  <XCircle size={16} className="text-text-muted flex-shrink-0" />
                )}
                <span className={clsx('text-sm', row.user ? 'text-text-primary' : 'text-text-muted')}>
                  {row.perm}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-5 text-xs text-text-muted">
            Need additional access? Contact your administrator.
          </p>
        </div>
      </div>
    </div>
  );
}
