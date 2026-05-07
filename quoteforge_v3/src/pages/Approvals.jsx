import { useEffect, useState } from 'react';
import { Clock, Check, X, Eye, RefreshCw, FileDown, Users as UsersIcon } from 'lucide-react';
import { Panel, Pill, Mono, SegmentedControl } from '@/components/ui';
import api from '@/services/api';
import clsx from 'clsx';

const TABS = [
  { value: 'pending',  label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'expired',  label: 'Expired' },
];

const STATUS_VARIANT = {
  pending:  'warning',
  approved: 'success',
  rejected: 'danger',
  expired:  'muted',
};

function formatMoney(cents) {
  return `$${((cents ?? 0) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function timeAgo(iso) {
  if (!iso) return '—';
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return `${Math.floor(d)}s`;
  if (d < 3600) return `${Math.floor(d / 60)}m`;
  if (d < 86_400) return `${Math.floor(d / 3600)}h`;
  return `${Math.floor(d / 86_400)}d`;
}

function countdown(iso) {
  if (!iso) return '—';
  const d = (new Date(iso).getTime() - Date.now()) / 1000;
  if (d <= 0) return 'expired';
  if (d < 3600) return `${Math.floor(d / 60)}m`;
  if (d < 86_400) return `${Math.floor(d / 3600)}h ${Math.floor((d % 3600) / 60)}m`;
  return `${Math.floor(d / 86_400)}d`;
}

export default function Approvals() {
  const [tab, setTab] = useState('pending');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [selected, setSelected] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState('');
  const [working, setWorking] = useState(false);

  async function refresh() {
    setLoading(true); setError('');
    try {
      const res = await api.get('/approvals', { params: { status: tab, per_page: 50 } });
      setRows(res.data.approvals);
      setPendingCount(res.data.pending_count);
    } catch (e) { setError(e.response?.data?.detail || 'failed to load'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function downloadPdf(offerId, docId) {
    try {
      const res = await api.get(`/offers/${offerId}/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `${docId || offerId}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { alert(e.response?.data?.detail || 'PDF download failed'); }
  }

  async function openDetail(row) {
    setNotes(''); setTranscript(null);
    try {
      const res = await api.get(`/approvals/${row.id}`);
      setSelected(res.data);
      api.get(`/approvals/${row.id}/transcript`)
        .then((tr) => setTranscript(tr.data))
        .catch(() => setTranscript({ via_buyer_room: false, messages: [] }));
    } catch (e) { alert(e.response?.data?.detail || 'failed to load detail'); }
  }

  function closeDrawer() { setSelected(null); setNotes(''); setTranscript(null); }

  async function doApprove() {
    if (!selected) return;
    setWorking(true);
    try {
      await api.post(`/approvals/${selected.id}/approve`, { reviewer_notes: notes || null });
      closeDrawer(); await refresh();
    } catch (e) { alert(e.response?.data?.detail || 'approve failed'); }
    finally { setWorking(false); }
  }

  async function doReject() {
    if (!selected) return;
    if (!notes.trim()) { alert('rejection requires reviewer notes'); return; }
    setWorking(true);
    try {
      await api.post(`/approvals/${selected.id}/reject`, { reviewer_notes: notes });
      closeDrawer(); await refresh();
    } catch (e) { alert(e.response?.data?.detail || 'reject failed'); }
    finally { setWorking(false); }
  }

  const tabOptions = TABS.map((t) => ({
    value: t.value, label: t.label,
    count: t.value === 'pending' && pendingCount > 0 ? pendingCount : undefined,
  }));

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <SegmentedControl options={tabOptions} active={tab} onChange={setTab} />
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
              <th className="table-header">Buyer agent</th>
              <th className="table-header">Source</th>
              <th className="table-header">Offer</th>
              <th className="table-header">Document</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Total</th>
              <th className="table-header">Created</th>
              <th className="table-header">Expires in</th>
              <th className="table-header">Status</th>
              <th className="table-header" style={{ width: 76 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="table-cell text-center text-text-muted py-10">loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="table-cell text-center text-text-muted py-10">no {tab} approvals</td></tr>
            ) : rows.map((r) => (
              <tr key={r.id} className="table-row cursor-pointer" onClick={() => openDetail(r)}>
                <td className="table-cell"><Mono className="text-[11.5px]">{r.buyer_agent_id}</Mono></td>
                <td className="table-cell">
                  {r.via_buyer_room
                    ? <Pill variant="accent">Buyer room</Pill>
                    : <Pill variant="muted">MCP agent</Pill>}
                </td>
                <td className="table-cell"><Mono className="text-[11.5px] text-text-secondary">{r.offer_id.slice(0, 20)}</Mono></td>
                <td className="table-cell"><Mono className="text-[11.5px] text-text-secondary">{r.document_id}</Mono></td>
                <td className="table-cell table-num font-semibold">{formatMoney(r.offer_total_cents)}</td>
                <td className="table-cell text-text-muted text-[11.5px] font-mono">{timeAgo(r.created_at)}</td>
                <td className="table-cell text-[11.5px]">
                  {r.status === 'pending' ? (
                    <span className="inline-flex items-center gap-1 text-text-secondary">
                      <Clock size={11} /> <Mono>{countdown(r.expires_at)}</Mono>
                    </span>
                  ) : <span className="text-text-muted">—</span>}
                </td>
                <td className="table-cell">
                  <Pill variant={STATUS_VARIANT[r.status] || 'muted'}>{r.status}</Pill>
                </td>
                <td className="table-cell" onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1">
                    <button className="icon-btn" onClick={() => openDetail(r)} title="Details">
                      <Eye size={12} className="text-text-muted" />
                    </button>
                    <button className="icon-btn" onClick={() => downloadPdf(r.offer_id, r.document_id)} title="Download PDF">
                      <FileDown size={12} className="text-text-muted" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {/* Slide-in drawer — right side, 560px. */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          onClick={(e) => { if (e.target === e.currentTarget) closeDrawer(); }}
          style={{ background: 'rgba(0,0,0,0.4)' }}
        >
          <div
            className="bg-surface border-l border-border h-full flex flex-col"
            style={{ width: 560, boxShadow: 'var(--shadow-pop)' }}
          >
            {/* Header with approve/reject always visible */}
            <div className="px-5 py-4 border-b border-border">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="section-label mb-0.5">APPROVAL · {selected.id.slice(0, 8)}</div>
                  <Mono className="text-[11.5px] text-text-secondary block truncate">{selected.offer_id}</Mono>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  {selected.status === 'pending' && (
                    <>
                      <button
                        className="btn-secondary"
                        style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
                        onClick={doReject} disabled={working}
                      >
                        <X size={13} /> Reject
                      </button>
                      <button className="btn-primary" onClick={doApprove} disabled={working}>
                        <Check size={13} /> Approve
                      </button>
                    </>
                  )}
                  <button className="icon-btn" onClick={closeDrawer}><X size={13} /></button>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3 text-[12.5px]">
                <Kv label="Buyer agent" value={<Mono>{selected.buyer_agent_id}</Mono>} />
                <Kv label="Document"    value={<Mono>{selected.document_id}</Mono>} />
                <Kv label="Client"      value={selected.offer_payload?.client_name} />
                <Kv label="Deal"        value={selected.offer_payload?.deal_name} />
                <Kv label="Region"      value={<Mono>{selected.offer_payload?.region}</Mono>} />
                <Kv label="Status"      value={<Pill variant={STATUS_VARIANT[selected.status]}>{selected.status}</Pill>} />
                <Kv label="Total"
                  value={<Mono className="font-semibold">{formatMoney(selected.offer_total_cents)}</Mono>}
                />
                <Kv label="Expires"     value={
                  selected.status === 'pending'
                    ? <Mono>{countdown(selected.expires_at)}</Mono>
                    : <span className="text-text-muted">—</span>
                } />
              </div>

              <div>
                <div className="section-label mb-2">LINE ITEMS</div>
                <table className="w-full text-[12.5px]">
                  <thead>
                    <tr style={{ color: 'var(--text-muted)' }}>
                      <th className="text-left pb-1 font-medium uppercase tracking-wider text-[10.5px]">SKU</th>
                      <th className="text-right pb-1 font-medium uppercase tracking-wider text-[10.5px]">Qty</th>
                      <th className="text-right pb-1 font-medium uppercase tracking-wider text-[10.5px]">Unit</th>
                      <th className="text-right pb-1 font-medium uppercase tracking-wider text-[10.5px]">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selected.offer_payload?.line_items || []).map((li, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="py-1.5 font-mono">{li.sku}</td>
                        <td className="py-1.5 text-right font-mono">{li.quantity}</td>
                        <td className="py-1.5 text-right font-mono">${Number(li.unit_price).toFixed(2)}</td>
                        <td className="py-1.5 text-right font-mono font-medium">${Number(li.line_total).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {selected.offer_payload?.pricing && (
                <div className="space-y-1 text-[12.5px] pt-2 border-t border-border">
                  <div className="flex justify-between text-text-secondary">
                    <span>Subtotal</span>
                    <Mono>${Number(selected.offer_payload.pricing.subtotal).toFixed(2)}</Mono>
                  </div>
                  <div className="flex justify-between" style={{ color: 'var(--success)' }}>
                    <span>Discount</span>
                    <Mono>-${Number(selected.offer_payload.pricing.discount).toFixed(2)}</Mono>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>Tax</span>
                    <Mono>${Number(selected.offer_payload.pricing.tax).toFixed(2)}</Mono>
                  </div>
                  <div className="flex justify-between font-semibold text-text-primary pt-1.5 border-t border-border">
                    <span>Total</span>
                    <Mono>${Number(selected.offer_payload.pricing.total).toFixed(2)}</Mono>
                  </div>
                </div>
              )}

              {selected.status !== 'pending' && selected.reviewer_notes && (
                <div className="p-3 rounded border border-border bg-subtle">
                  <div className="section-label mb-1">REVIEWER NOTES</div>
                  <div className="text-[12.5px] text-text-primary">{selected.reviewer_notes}</div>
                </div>
              )}

              {transcript?.via_buyer_room && transcript.messages?.length > 0 && (
                <div className="p-3 rounded border" style={{ borderColor: 'var(--accent)', background: 'var(--accent-muted)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <UsersIcon size={13} style={{ color: 'var(--accent)' }} />
                    <span className="text-[11.5px] font-semibold" style={{ color: 'var(--accent)' }}>
                      BUYER ROOM TRANSCRIPT
                    </span>
                    <Mono className="text-[10.5px] ml-auto" style={{ color: 'var(--accent)' }}>
                      {transcript.messages.length} messages
                    </Mono>
                  </div>
                  <div className="space-y-1.5 max-h-72 overflow-y-auto">
                    {transcript.messages.map((m, i) => (
                      <div
                        key={i}
                        className="p-2 rounded text-[11.5px]"
                        style={{
                          background: m.role === 'user' ? 'var(--accent)' : 'var(--bg-surface)',
                          color: m.role === 'user' ? 'var(--accent-fg)' : 'var(--text-primary)',
                          border: m.role === 'user' ? 'none' : '1px solid var(--border)',
                        }}
                      >
                        <div
                          className="font-mono uppercase tracking-wider text-[9.5px] mb-0.5"
                          style={{ opacity: 0.7 }}
                        >
                          {m.role === 'user' ? 'BUYER' : 'ASSISTANT'}
                        </div>
                        <div className="whitespace-pre-wrap">{m.content}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {selected.status === 'pending' && (
              <div className="p-4 border-t border-border bg-subtle">
                <textarea
                  rows={2}
                  placeholder="Reviewer notes (required for reject, optional for approve)"
                  className="input-field font-mono"
                  style={{ fontSize: 12.5, resize: 'vertical' }}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Kv({ label, value }) {
  return (
    <div>
      <div className="section-label mb-0.5">{label}</div>
      <div className="text-text-primary">{value ?? <span className="text-text-muted">—</span>}</div>
    </div>
  );
}
