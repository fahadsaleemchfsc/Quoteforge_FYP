import { useEffect, useState } from 'react';
import { FileJson, RefreshCw, ChevronRight, X } from 'lucide-react';
import { Panel, Pill, Mono, SegmentedControl } from '@/components/ui';
import api from '@/services/api';
import clsx from 'clsx';

/*
 * The retry-chain page. Signature visual: expand a row to reveal the full
 * chain — each attempt is a colored node on a vertical dotted line with
 * proposal details + verdict. This is the architecture's thesis made
 * visible: small model proposes, guardrail gates, retry, commit.
 */

const VERDICT_VARIANT = {
  pass: 'success', review: 'warning', block: 'danger',
  timeout: 'muted', parse_error: 'warning', backend_error: 'danger',
};

const OUTCOME_LABEL = {
  first_try: 'first try',
  retried:   'retried',
  fell_back: 'fell back',
  timed_out: 'timed out',
};

const OUTCOME_VARIANT = {
  first_try: 'success',
  retried:   'warning',
  fell_back: 'danger',
  timed_out: 'muted',
};

const TABS = [
  { value: 'all',       label: 'All' },
  { value: 'first_try', label: 'First try' },
  { value: 'retried',   label: 'Retried' },
  { value: 'fell_back', label: 'Fell back' },
  { value: 'timed_out', label: 'Timed out' },
];

function timeAgo(iso) {
  if (!iso) return '—';
  const delta = (Date.now() - new Date(iso).getTime()) / 1000;
  if (delta < 60) return `${Math.floor(delta)}s`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m`;
  if (delta < 86_400) return `${Math.floor(delta / 3600)}h`;
  return `${Math.floor(delta / 86_400)}d`;
}

function money(cents) {
  return `$${((cents ?? 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function AttemptNode({ attempt, isLast }) {
  const variant = VERDICT_VARIANT[attempt.verdict] || 'muted';
  const dotColor = `var(--${variant === 'muted' ? 'text-muted' : variant})`;

  return (
    <div className="relative pl-9">
      {/* dotted connector */}
      {!isLast && (
        <div
          className="absolute top-4 left-[11px] w-0 h-[calc(100%+12px)]"
          style={{ borderLeft: '1px dashed var(--border-strong)' }}
        />
      )}
      {/* node */}
      <div
        className="absolute left-[4px] top-1 w-[14px] h-[14px] rounded-full flex items-center justify-center"
        style={{ background: 'var(--bg-surface)', border: `2px solid ${dotColor}` }}
      >
        <div className="w-[6px] h-[6px] rounded-full" style={{ background: dotColor }} />
      </div>

      <div className="pb-5">
        <div className="flex items-center gap-3 mb-1.5">
          <Mono className="text-[11px] text-text-muted">
            ATTEMPT&nbsp;{String(attempt.attempt_number).padStart(2, '0')}
          </Mono>
          <Pill variant={variant}>{attempt.verdict}</Pill>
          <Mono className="text-[11px] text-text-muted">model={attempt.backend}</Mono>
          {attempt.latency_ms > 0 && (
            <Mono className="text-[11px] text-text-muted ml-auto">{attempt.latency_ms}ms</Mono>
          )}
          {attempt.fell_back && <Pill variant="danger">FALLBACK</Pill>}
        </div>

        {attempt.proposed_lines?.length > 0 && (
          <div className="ml-0 space-y-0.5">
            {attempt.proposed_lines.map((pl, i) => (
              <div key={i} className="flex items-center gap-3 text-[12.5px]">
                <span className="text-text-muted">proposed</span>
                <Mono className="text-text-primary">{pl.sku}</Mono>
                <span className="text-text-muted">@</span>
                <Mono className="text-text-primary font-medium">{money(pl.proposed_unit_price_cents)}</Mono>
                {pl.quantity > 1 && (
                  <Mono className="text-text-muted">× {pl.quantity}</Mono>
                )}
              </div>
            ))}
          </div>
        )}

        {attempt.rationale && (
          <div className="text-[11.5px] text-text-secondary italic mt-1 leading-relaxed">
            {attempt.rationale}
          </div>
        )}

        {attempt.blocking_check_names?.length > 0 && (
          <div className="mt-1.5 flex items-center gap-2 text-[11.5px]">
            <span className="text-text-muted">blocked by</span>
            {attempt.blocking_check_names.map((n) => (
              <Mono key={n} style={{ color: 'var(--danger)' }}>{n}</Mono>
            ))}
          </div>
        )}

        {attempt.error && (
          <div className="text-[11.5px] mt-1" style={{ color: 'var(--warning)' }}>
            {attempt.error}
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineDrawer({ row }) {
  return (
    <div
      className="px-5 py-4 border-t"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-subtle)' }}
    >
      <div className="flex items-center gap-4 mb-4 pb-3 border-b border-border">
        <div>
          <div className="section-label mb-0.5">NEGOTIATION</div>
          <Mono className="text-[12.5px] text-text-primary">{row.offer_id}</Mono>
        </div>
        <div className="flex-1" />
        <Mono className="text-[11px] text-text-muted">
          {row.attempt_count} attempt{row.attempt_count === 1 ? '' : 's'}
          {' · '}total {row.total_latency_ms}ms
        </Mono>
        <Pill variant={VERDICT_VARIANT[row.final_verdict] || 'muted'}>{row.final_verdict}</Pill>
      </div>
      <div>
        {row.attempts.map((a, i) => (
          <AttemptNode key={i} attempt={a} isLast={i === row.attempts.length - 1} />
        ))}
      </div>
    </div>
  );
}

export default function Negotiations() {
  const [tab, setTab] = useState('all');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(new Set());
  const [ucpOffer, setUcpOffer] = useState(null);
  const [ucpLoading, setUcpLoading] = useState(false);

  async function refresh() {
    setLoading(true); setError('');
    try {
      const res = await api.get('/negotiations', { params: { outcome: tab, per_page: 50 } });
      setRows(res.data.rows);
    } catch (e) { setError(e.response?.data?.detail || 'failed to load'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  function toggle(id) {
    const next = new Set(expanded);
    next.has(id) ? next.delete(id) : next.add(id);
    setExpanded(next);
  }

  async function viewUcp(offerId) {
    setUcpLoading(true);
    setUcpOffer({ offer_id: offerId, payload: null });
    try {
      const res = await api.get(`/offers/${offerId}/ucp`);
      setUcpOffer({ offer_id: offerId, payload: res.data });
    } catch (e) {
      setUcpOffer({ offer_id: offerId, payload: { error: e.response?.data?.detail || 'failed' } });
    } finally { setUcpLoading(false); }
  }

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <SegmentedControl
          options={TABS.map((t) => ({ value: t.value, label: t.label }))}
          active={tab}
          onChange={setTab}
        />
        <button className="btn-secondary" onClick={refresh} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-3 p-2.5 rounded text-[12.5px]"
          style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}>{error}</div>
      )}

      <Panel padded={false}>
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-header" style={{ width: 28 }}></th>
              <th className="table-header">Offer</th>
              <th className="table-header">Age</th>
              <th className="table-header">Attempts</th>
              <th className="table-header">Final</th>
              <th className="table-header">Outcome</th>
              <th className="table-header">Backend</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Confidence</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Latency</th>
              <th className="table-header" style={{ width: 44 }}>UCP</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} className="table-cell text-center text-text-muted py-10">loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={10} className="table-cell text-center text-text-muted py-10">
                no {tab.replace('_', ' ')} negotiations
              </td></tr>
            ) : rows.map((r) => {
              const open = expanded.has(r.offer_id);
              return (
                <>
                  <tr
                    key={r.offer_id}
                    className="table-row cursor-pointer"
                    onClick={() => toggle(r.offer_id)}
                  >
                    <td className="table-cell">
                      <ChevronRight
                        size={13}
                        className="text-text-muted transition-transform"
                        style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
                      />
                    </td>
                    <td className="table-cell"><Mono className="text-[11.5px] text-text-secondary">{r.offer_id}</Mono></td>
                    <td className="table-cell text-text-muted text-[11.5px] font-mono">{timeAgo(r.last_attempt_at)}</td>
                    <td className="table-cell">
                      <Mono className="text-[12px] font-medium">{r.attempt_count}</Mono>
                    </td>
                    <td className="table-cell">
                      <Pill variant={VERDICT_VARIANT[r.final_verdict] || 'muted'}>{r.final_verdict}</Pill>
                    </td>
                    <td className="table-cell">
                      <Pill variant={OUTCOME_VARIANT[r.outcome] || 'muted'}>
                        {OUTCOME_LABEL[r.outcome] || r.outcome}
                      </Pill>
                    </td>
                    <td className="table-cell"><Mono className="text-[11.5px] text-text-secondary">{r.backend}</Mono></td>
                    <td className="table-cell table-num text-text-secondary">
                      {r.best_confidence != null ? r.best_confidence.toFixed(2) : '—'}
                    </td>
                    <td className="table-cell table-num text-text-secondary">{r.total_latency_ms}ms</td>
                    <td className="table-cell">
                      <button
                        className="icon-btn"
                        onClick={(e) => { e.stopPropagation(); viewUcp(r.offer_id); }}
                        title="UCP JSON"
                      >
                        <FileJson size={12} className="text-text-muted" />
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr key={`${r.offer_id}-exp`}>
                      <td colSpan={10} style={{ padding: 0 }}>
                        <TimelineDrawer row={r} />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </Panel>

      {/* UCP JSON modal */}
      {ucpOffer && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setUcpOffer(null); }}
          style={{ background: 'rgba(0,0,0,0.4)' }}
        >
          <div
            className="bg-surface border border-border rounded w-full max-w-[640px] max-h-[80vh] flex flex-col"
            style={{ boxShadow: 'var(--shadow-pop)' }}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div>
                <div className="section-label">UCP 2026-01 OFFER</div>
                <Mono className="text-[11.5px] text-text-secondary mt-0.5">{ucpOffer.offer_id}</Mono>
              </div>
              <button className="icon-btn" onClick={() => setUcpOffer(null)}><X size={13} /></button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {ucpLoading && !ucpOffer.payload ? (
                <div className="text-[12.5px] text-text-muted">loading…</div>
              ) : (
                <pre className="text-[11px] font-mono text-text-primary whitespace-pre-wrap">
                  {JSON.stringify(ucpOffer.payload, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
