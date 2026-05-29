import { useEffect, useMemo, useState } from 'react';
import {
  Building2, Users as UsersIcon, FileText, Cloud, Sparkles,
  Search, ArrowUpRight, Calendar, X, ShieldAlert,
} from 'lucide-react';
import clsx from 'clsx';
import adminService from '@/services/adminService';
import { StatusBadge } from '@/components/ui';

/**
 * Platform super-admin landing — every workspace in the deployment, the
 * users in each, recent quotes, integration health. Visible only when
 * AuthContext.isSuperAdmin is true; the App.jsx route guard 302s away
 * otherwise. Backend additionally enforces SUPER_ADMIN_EMAILS.
 */

const fmtRelative = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  const delta = (Date.now() - d.getTime()) / 1000;
  if (delta < 60)       return 'just now';
  if (delta < 3600)     return `${Math.round(delta / 60)}m ago`;
  if (delta < 86_400)   return `${Math.round(delta / 3600)}h ago`;
  if (delta < 7 * 86_400) return `${Math.round(delta / 86_400)}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

export default function SuperAdmin() {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [stats, setStats] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [query, setQuery] = useState('');
  const [drawer, setDrawer] = useState(null); // currently-open tenant detail

  useEffect(() => {
    Promise.all([adminService.stats(), adminService.tenants()])
      .then(([s, t]) => {
        setStats(s.data);
        setTenants(t.data);
      })
      .catch((e) => {
        setErr(e?.response?.data?.detail || e.message || 'Failed to load');
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tenants;
    return tenants.filter(
      (t) => t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q),
    );
  }, [tenants, query]);

  if (loading) {
    return <div className="page-enter"><div className="card p-10 text-text-secondary text-sm">Loading platform data…</div></div>;
  }

  if (err) {
    return (
      <div className="page-enter">
        <div className="card p-10 flex items-start gap-4">
          <ShieldAlert size={28} className="text-rose-500 flex-shrink-0" />
          <div>
            <div className="font-semibold text-text-primary">Can't reach super-admin data</div>
            <div className="text-sm text-text-secondary mt-1">{err}</div>
            <div className="text-xs text-text-muted mt-3">
              Backend gates this view by <code className="font-mono">SUPER_ADMIN_EMAILS</code>.
              If you're seeing 403, your email isn't on the allowlist for this deployment.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-enter">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent-muted flex items-center justify-center">
            <Building2 size={18} className="text-accent" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-text-primary">Platform · Workspaces</div>
            <div className="text-xs text-text-secondary">Every QuoteForge tenant in this deployment</div>
          </div>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or slug"
            className="input-field pl-8 w-64"
            style={{ height: 36, fontSize: 13 }}
          />
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <StatCard icon={Building2} label="Workspaces"     value={stats?.total_tenants ?? 0} accent />
        <StatCard icon={UsersIcon} label="Users"          value={stats?.total_users ?? 0} />
        <StatCard icon={FileText}  label="Quotes"         value={stats?.total_quotes ?? 0} />
        <StatCard icon={Cloud}     label="SF connections" value={stats?.connected_salesforce_orgs ?? 0} />
        <StatCard icon={Sparkles}  label="New (7d)"       value={stats?.new_tenants_last_7d ?? 0} good />
      </div>

      {/* Workspaces table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-border bg-bg-subtle flex items-center justify-between">
          <div className="text-[13px] font-bold text-text-primary">
            Workspaces <span className="text-text-muted font-normal">({filtered.length})</span>
          </div>
        </div>
        {filtered.length === 0 ? (
          <div className="p-10 text-center text-text-secondary text-sm">
            No workspaces match {query ? `"${query}"` : 'this filter'}.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-muted text-[11px] uppercase tracking-wider font-semibold">
                  <th className="text-left py-3 px-5">Workspace</th>
                  <th className="text-right py-3 px-4">Users</th>
                  <th className="text-right py-3 px-4">Quotes</th>
                  <th className="text-left  py-3 px-4">Salesforce</th>
                  <th className="text-left  py-3 px-4">Last quote</th>
                  <th className="text-left  py-3 px-4">Created</th>
                  <th className="py-3 px-5" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => setDrawer(t.id)}
                    className="border-b border-border last:border-b-0 hover:bg-bg-subtle cursor-pointer transition-colors"
                  >
                    <td className="py-3.5 px-5">
                      <div className="font-semibold text-text-primary">{t.name || t.slug}</div>
                      <div className="text-xs text-text-muted font-mono">{t.slug}</div>
                    </td>
                    <td className="py-3.5 px-4 text-right tabular-nums text-text-primary">{t.users}</td>
                    <td className="py-3.5 px-4 text-right tabular-nums text-text-primary">{t.quotes}</td>
                    <td className="py-3.5 px-4">
                      {t.salesforce_orgs > 0 ? (
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          {t.salesforce_orgs} org{t.salesforce_orgs > 1 ? 's' : ''}
                        </span>
                      ) : t.crm_connections > 0 ? (
                        <span className="text-xs text-text-secondary">Legacy CRM only</span>
                      ) : (
                        <span className="text-xs text-text-muted">—</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-text-secondary text-xs">{fmtRelative(t.last_quote_at)}</td>
                    <td className="py-3.5 px-4 text-text-secondary text-xs">{fmtRelative(t.created_at)}</td>
                    <td className="py-3.5 px-5 text-right">
                      <ArrowUpRight size={14} className="text-text-muted" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail drawer */}
      {drawer && <TenantDrawer tenantId={drawer} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, accent = false, good = false }) {
  return (
    <div
      className={clsx(
        'card p-4 relative overflow-hidden',
        accent && 'bg-gradient-to-br from-accent-muted to-bg-surface',
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <Icon size={16} className={clsx('text-text-muted', accent && 'text-accent', good && 'text-emerald-600')} />
        <span className="text-[10px] uppercase tracking-wider font-semibold text-text-muted">{label}</span>
      </div>
      <div className="text-2xl font-bold text-text-primary tabular-nums">{(value ?? 0).toLocaleString('en-US')}</div>
    </div>
  );
}

function TenantDrawer({ tenantId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    adminService
      .tenant(tenantId)
      .then((res) => setData(res.data))
      .catch((e) => setErr(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [tenantId]);

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-xl bg-bg-surface border-l border-border shadow-2xl overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-bg-surface z-10">
          <div className="text-[13px] font-bold text-text-primary">Workspace detail</div>
          <button onClick={onClose} className="icon-btn"><X size={16} className="text-text-secondary" /></button>
        </div>
        <div className="p-5">
          {loading ? (
            <div className="text-sm text-text-secondary">Loading…</div>
          ) : err ? (
            <div className="text-sm text-rose-600">{err}</div>
          ) : (
            <>
              {/* Header */}
              <div className="mb-5">
                <div className="text-xl font-bold text-text-primary">{data.name || data.slug}</div>
                <div className="text-xs text-text-muted font-mono mt-1">{data.slug} · {data.id}</div>
                <div className="text-xs text-text-secondary mt-2 flex items-center gap-1.5">
                  <Calendar size={12} /> Created {fmtRelative(data.created_at)}
                </div>
              </div>

              {/* Salesforce status */}
              <div className="card p-4 mb-5">
                <div className="text-[10px] uppercase tracking-wider font-bold text-text-muted mb-2">Salesforce</div>
                {data.salesforce.connected ? (
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" />
                      <span className="text-sm font-semibold text-text-primary">Connected</span>
                    </div>
                    <div className="text-xs text-text-secondary mt-2 font-mono">{data.salesforce.org_id}</div>
                    <div className="text-xs text-text-muted font-mono">{data.salesforce.instance_url}</div>
                    <div className="text-xs text-text-muted mt-1">Connected {fmtRelative(data.salesforce.connected_at)}</div>
                  </div>
                ) : (
                  <div className="text-sm text-text-secondary">Not connected to a Salesforce org.</div>
                )}
              </div>

              {/* Members */}
              <div className="mb-5">
                <div className="text-[10px] uppercase tracking-wider font-bold text-text-muted mb-2">
                  Members ({data.users.length})
                </div>
                <div className="space-y-1.5">
                  {data.users.map((u) => (
                    <div key={u.id} className="flex items-center justify-between p-2.5 rounded border border-border bg-bg-app">
                      <div>
                        <div className="text-sm font-semibold text-text-primary">{u.name}</div>
                        <div className="text-xs text-text-muted font-mono">{u.email}</div>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={u.role} />
                        <span className="text-xs text-text-muted">{u.quotes_generated}q</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent docs */}
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-text-muted mb-2">
                  Recent documents ({data.recent_documents.length})
                </div>
                {data.recent_documents.length === 0 ? (
                  <div className="text-xs text-text-secondary">No quotes yet.</div>
                ) : (
                  <div className="space-y-1.5">
                    {data.recent_documents.map((d) => (
                      <div key={d.doc_id} className="p-2.5 rounded border border-border bg-bg-app">
                        <div className="flex items-center justify-between">
                          <div className="text-sm font-mono text-text-primary">{d.doc_id}</div>
                          <div className="text-xs text-text-muted">{fmtRelative(d.generated_at)}</div>
                        </div>
                        <div className="text-xs text-text-secondary mt-1">
                          {d.client} · ${(d.amount || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          {d.synced_to_salesforce && (
                            <span className="ml-2 text-emerald-600 font-semibold">· synced</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
