import {
  ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip,
} from 'recharts';
import { MetricCard, StatusBadge } from '@/components/ui';
import { DASHBOARD_METRICS, CHART_DATA, RECENT_ACTIVITY, CRM_CONNECTIONS } from '@/constants/mockData';

export default function Dashboard() {
  return (
    <div className="page-enter">
      {/* ─── Metric Cards ────────────────────── */}
      <div className="grid grid-cols-4 gap-5 mb-7">
        {DASHBOARD_METRICS.map((m, i) => (
          <MetricCard key={i} metric={m} index={i} />
        ))}
      </div>

      {/* ─── Charts Row ──────────────────────── */}
      <div className="grid grid-cols-[2fr_1fr] gap-5 mb-7">
        {/* Trend Chart */}
        <div className="card p-7">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-base font-bold text-gray-900">Generation Trends</h3>
              <p className="text-sm text-gray-500 mt-1">Quotes, proposals, and conversions over time</p>
            </div>
            <select className="input-field w-auto text-sm py-1.5">
              <option>Last 7 months</option>
              <option>Last 3 months</option>
              <option>This Year</option>
            </select>
          </div>

          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={CHART_DATA}>
              <defs>
                <linearGradient id="gQuotes" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gProposals" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e5e7eb', boxShadow: '0 4px 12px rgba(0,0,0,0.08)', fontSize: 13 }} />
              <Area type="monotone" dataKey="quotes" stroke="#6366f1" fill="url(#gQuotes)" strokeWidth={2.5} dot={false} />
              <Area type="monotone" dataKey="proposals" stroke="#06b6d4" fill="url(#gProposals)" strokeWidth={2.5} dot={false} />
              <Area type="monotone" dataKey="conversions" stroke="#10b981" fill="transparent" strokeWidth={2} strokeDasharray="5 5" dot={false} />
            </AreaChart>
          </ResponsiveContainer>

          <div className="flex gap-6 mt-4">
            {[
              { label: 'Quotes', color: '#6366f1' },
              { label: 'Proposals', color: '#06b6d4' },
              { label: 'Conversions', color: '#10b981' },
            ].map((l) => (
              <div key={l.label} className="flex items-center gap-2 text-sm text-gray-500">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: l.color }} />
                {l.label}
              </div>
            ))}
          </div>
        </div>

        {/* Integration Health */}
        <div className="card p-7">
          <h3 className="text-base font-bold text-gray-900 mb-6">Integration Health</h3>
          <div className="flex flex-col gap-4">
            {CRM_CONNECTIONS.map((crm) => (
              <div key={crm.id} className="p-4 rounded-xl border border-gray-100 bg-gray-50/50">
                <div className="flex justify-between items-center mb-2.5">
                  <span className="text-sm font-semibold text-gray-900">{crm.platform}</span>
                  <StatusBadge status={crm.status} />
                </div>
                {crm.status === 'connected' && (
                  <>
                    <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                      <span>Uptime</span>
                      <span className="font-semibold text-emerald-600">{crm.health}%</span>
                    </div>
                    <div className="h-1 rounded-full bg-gray-200">
                      <div
                        className="h-full rounded-full transition-all duration-1000"
                        style={{
                          width: `${crm.health}%`,
                          background: crm.health > 99 ? '#22c55e' : '#f59e0b',
                        }}
                      />
                    </div>
                    <div className="text-[11px] text-gray-400 mt-1.5">Last sync: {crm.lastSync}</div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Recent Activity ─────────────────── */}
      <div className="card p-7">
        <div className="flex justify-between items-center mb-5">
          <div>
            <h3 className="text-base font-bold text-gray-900">Recent Activity</h3>
            <p className="text-sm text-gray-500 mt-1">Latest quote and proposal generation events</p>
          </div>
          <button className="btn-secondary text-sm">View All</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                {['Client', 'Deal', 'Type', 'Amount', 'Status', 'Time', 'User'].map((h) => (
                  <th key={h} className="table-header">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RECENT_ACTIVITY.map((item) => (
                <tr key={item.id} className="table-row">
                  <td className="table-cell font-semibold text-gray-900">{item.client}</td>
                  <td className="table-cell text-gray-500">{item.deal}</td>
                  <td className="table-cell">
                    <span className={`px-2.5 py-0.5 rounded-md text-xs font-medium capitalize ${
                      item.type === 'quote' ? 'bg-brand-50 text-brand-700' : 'bg-purple-50 text-purple-700'
                    }`}>
                      {item.type}
                    </span>
                  </td>
                  <td className="table-cell font-semibold text-gray-900">{item.amount}</td>
                  <td className="table-cell"><StatusBadge status={item.status} /></td>
                  <td className="table-cell text-gray-400">{item.time}</td>
                  <td className="table-cell text-gray-500">{item.user}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
