import { useEffect, useRef, useState } from 'react';
import { Panel, Pill, Mono, StatRow, StatusBadge } from '@/components/ui';
import { Reveal, AnimatedCounter } from '@/components/marketing/visuals';
import api from '@/services/api';
import clsx from 'clsx';

// Count-up wrapper for KPI values. Animates integer values (e.g. "1,234",
// "42%", "12s") from 0 → target on view, preserving any prefix/suffix.
// Falls back to the raw string for decimals or non-numeric values.
function CountUpValue({ value }) {
  const raw = String(value);
  if (raw.includes('.')) return raw;
  const m = raw.match(/^(\D*)([\d,]+)(\D*)$/);
  if (!m) return raw;
  const num = parseInt(m[2].replace(/,/g, ''), 10);
  if (Number.isNaN(num)) return raw;
  return <AnimatedCounter to={num} prefix={m[1]} suffix={m[3]} duration={1100} />;
}

const POLL_MS = 5_000;

const DOT_COLOR = {
  green:  'var(--success)',
  amber:  'var(--warning)',
  red:    'var(--danger)',
  orange: 'var(--warning)',
  gray:   'var(--text-muted)',
};

function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}
function formatMoney(cents) {
  if (cents == null) return '';
  return `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/* Upcases the verb we want as an event type label. Defensive — new kinds
 * of events land as-is. */
function extractEventType(summary, kind) {
  const s = summary || '';
  if (kind === 'state') {
    const first = s.split(' ')[0];
    return first.toUpperCase();
  }
  if (kind === 'guardrail') {
    if (s.startsWith('guardrail=block'))  return 'GUARDRAIL_BLOCK';
    if (s.startsWith('guardrail=review')) return 'GUARDRAIL_REVIEW';
    if (s.startsWith('guardrail=pass'))   return 'GUARDRAIL_PASS';
    return 'GUARDRAIL';
  }
  if (kind === 'negotiation') return 'NEGOTIATION';
  return (kind || 'EVENT').toUpperCase();
}

function extractDetail(summary, kind) {
  const s = summary || '';
  if (kind === 'guardrail') {
    const after = s.split(' ').slice(1).join(' ');
    return after || '—';
  }
  if (kind === 'negotiation') {
    return s.replace(/^negotiation\s*/i, '');
  }
  if (kind === 'state') {
    const parts = s.split('·').map((x) => x.trim());
    return parts.slice(1).join(' · ') || parts[0] || '';
  }
  return s;
}

function FeedRow({ item, flash }) {
  const dotColor = DOT_COLOR[item.dot_color] || DOT_COLOR.gray;
  const eventType = extractEventType(item.summary, item.kind);
  const detail = extractDetail(item.summary, item.kind);
  return (
    <div
      className={clsx(
        'flex items-center gap-3 h-7 px-4 text-[12px] border-b',
        flash && 'qf-flash',
      )}
      style={{ borderColor: 'var(--border)' }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: dotColor }}
      />
      <Mono className="text-text-muted w-20 flex-shrink-0">{formatTime(item.timestamp)}</Mono>
      <span
        className="font-mono uppercase tracking-wider text-[10.5px] w-44 flex-shrink-0 truncate"
        style={{ color: 'var(--text-secondary)', letterSpacing: '0.06em' }}
      >
        {eventType}
      </span>
      <Mono className="text-text-secondary w-56 flex-shrink-0 truncate">{item.agent || '—'}</Mono>
      <span className="flex-1 truncate text-text-primary">{detail}</span>
      {item.total_cents != null && (
        <Mono className="text-text-primary font-semibold w-20 text-right flex-shrink-0">
          {formatMoney(item.total_cents)}
        </Mono>
      )}
      {item.offer_id && (
        <Mono className="text-text-muted w-32 text-right flex-shrink-0 truncate">
          {item.offer_id.slice(0, 20)}
        </Mono>
      )}
    </div>
  );
}

function LiveFeed() {
  const [items, setItems] = useState([]);
  const [flashIds, setFlashIds] = useState(new Set());
  const lastSeen = useRef(new Set());

  useEffect(() => {
    let cancelled = false;
    async function pull() {
      try {
        const res = await api.get('/activity/feed', { params: { limit: 20 } });
        if (cancelled) return;
        const data = res.data || [];
        const newIds = new Set();
        data.forEach((it) => { const k = `${it.timestamp}-${it.offer_id || it.agent}`; if (!lastSeen.current.has(k)) newIds.add(k); });
        data.forEach((it) => lastSeen.current.add(`${it.timestamp}-${it.offer_id || it.agent}`));
        setItems(data);
        if (newIds.size > 0) {
          setFlashIds(newIds);
          setTimeout(() => setFlashIds(new Set()), 450);
        }
      } catch { /* silent — keep prior */ }
    }
    pull();
    const t = setInterval(pull, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  return (
    <Panel
      padded={false}
      title="Live activity"
      subtitle="Buyer-agent traffic through the Gateway · polled every 5s"
      actions={
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-text-muted">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--success)' }} />
          LIVE
        </div>
      }
    >
      <div className="relative" style={{ minHeight: 340 }}>
        {items.length === 0 ? (
          <div className="py-16 text-center text-[13px] text-text-muted">
            no recent activity — send an MCP request to wake it up
          </div>
        ) : (
          items.slice(0, 20).map((it, i) => {
            const key = `${it.timestamp}-${it.offer_id || it.agent}-${i}`;
            return (
              <div key={key} style={{ opacity: Math.max(0.4, 1 - i * 0.03) }}>
                <FeedRow item={it} flash={flashIds.has(`${it.timestamp}-${it.offer_id || it.agent}`)} />
              </div>
            );
          })
        )}
        {items.length > 0 && (
          <div
            className="absolute bottom-0 left-0 right-0 h-12 pointer-events-none"
            style={{
              background: 'linear-gradient(to top, var(--bg-surface) 0%, transparent 100%)',
            }}
          />
        )}
      </div>
    </Panel>
  );
}

function KPIStrip({ metrics }) {
  return (
    <div
      className="card flex items-center gap-6 px-5 py-2.5"
      style={{ borderRadius: 4 }}
    >
      {metrics.map((m, i) => (
        <div key={i} className="flex items-center gap-6">
          {i > 0 && <span className="text-text-muted">·</span>}
          <StatRow label={m.label} value={<CountUpValue value={m.value} />} delta={m.delta} deltaDirection={m.direction} />
        </div>
      ))}
    </div>
  );
}

function RecentActivityTable({ rows }) {
  return (
    <Panel padded={false} title="Recent deals" subtitle="Last 10 generations">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-header">Client</th>
              <th className="table-header">Deal</th>
              <th className="table-header">Type</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Amount</th>
              <th className="table-header">Status</th>
              <th className="table-header">Time</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id || i} className="table-row">
                <td className="table-cell font-medium">{r.client}</td>
                <td className="table-cell text-text-secondary">{r.deal}</td>
                <td className="table-cell">
                  <Pill variant={r.type === 'quote' ? 'accent' : 'muted'}>{r.type}</Pill>
                </td>
                <td className="table-cell table-num font-medium">{r.amount}</td>
                <td className="table-cell"><StatusBadge status={r.status} /></td>
                <td className="table-cell text-text-muted text-[11.5px] font-mono">{r.time}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="table-cell text-center text-text-muted py-8">no activity yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function IntegrationHealth({ crms }) {
  return (
    <Panel title="Integration health" subtitle="CRM connection status">
      <div className="space-y-3">
        {crms.map((c) => (
          <div
            key={c.id}
            className="p-3 rounded border"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-subtle)' }}
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[13px] font-medium text-text-primary">{c.platform}</span>
              <StatusBadge status={c.status} />
            </div>
            {c.status === 'connected' && (
              <>
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-text-muted font-mono">uptime</span>
                  <Mono style={{ color: 'var(--success)' }}>{c.health}%</Mono>
                </div>
                <div
                  className="h-[3px] rounded-sm overflow-hidden"
                  style={{ background: 'var(--bg-muted)' }}
                >
                  <div
                    className="h-full rounded-sm"
                    style={{
                      width: `${c.health}%`,
                      background: c.health > 99 ? 'var(--success)' : 'var(--warning)',
                    }}
                  />
                </div>
                <div className="text-[10.5px] font-mono text-text-muted mt-1">
                  last sync · {c.lastSync}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState([
    { label: 'quotes',     value: '0' },
    { label: 'sent',       value: '0' },
    { label: 'conversion', value: '0%' },
    { label: 'avg gen',    value: '0s' },
  ]);
  const [activity, setActivity] = useState([]);
  const [crms, setCrms] = useState([
    { id: 1, platform: 'Salesforce', status: 'connected',    lastSync: '2 min ago', health: 99.8 },
    { id: 2, platform: 'HubSpot',    status: 'connected',    lastSync: '5 min ago', health: 98.2 },
    { id: 3, platform: 'Custom',     status: 'disconnected', lastSync: '—',         health: 0 },
  ]);

  useEffect(() => {
    async function load() {
      try {
        const [m, a, c] = await Promise.allSettled([
          api.get('/quotes/metrics'),
          api.get('/quotes/activity'),
          api.get('/crm/connections'),
        ]);
        if (m.status === 'fulfilled') {
          const d = m.value.data;
          setMetrics([
            { label: 'quotes',     value: String(d.quotesGenerated || 0), delta: '+12.5%', direction: 'up' },
            { label: 'sent',       value: String(d.proposalsSent || 0),   delta: '+8.2%',  direction: 'up' },
            { label: 'conversion', value: d.conversionRate || '0%',       delta: '+3.1%',  direction: 'up' },
            { label: 'avg gen',    value: d.avgGenTime || '0s',           delta: '-0.8s',  direction: 'up' },
          ]);
        }
        if (a.status === 'fulfilled') setActivity(a.value.data);
        if (c.status === 'fulfilled') {
          setCrms(c.value.data.map((x) => ({
            ...x, lastSync: x.lastSync ? new Date(x.lastSync).toLocaleString() : 'never',
          })));
        }
      } catch { /* keep defaults */ }
    }
    load();
  }, []);

  return (
    <div className="page-enter space-y-4">
      <LiveFeed />
      <Reveal delay={0}><KPIStrip metrics={metrics} /></Reveal>
      <Reveal delay={120}>
        <div className="grid gap-4" style={{ gridTemplateColumns: 'minmax(0, 65%) minmax(0, 35%)' }}>
          <RecentActivityTable rows={activity} />
          <IntegrationHealth crms={crms} />
        </div>
      </Reveal>
    </div>
  );
}
