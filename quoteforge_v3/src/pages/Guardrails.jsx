import { useEffect, useState } from 'react';
import { Save, PlayCircle, Plus, X } from 'lucide-react';
import { Panel, Pill, Mono, Slider, SegmentedControl } from '@/components/ui';
import api from '@/services/api';
import clsx from 'clsx';

/*
 * The product's signature page. Two-column cockpit:
 *   Left  — policy editor: sliders + chip inputs + simulator
 *   Right — impact preview: live deltas against last 7 days as sliders move
 *
 * Everything numeric is monospace + tabular. Verdict colors thread through
 * via the Pill + semantic tokens.
 */

const VERDICT_VARIANT = { pass: 'success', review: 'warning', block: 'danger' };

function ChipInput({ values, onChange, placeholder }) {
  const [draft, setDraft] = useState('');
  function add() {
    const v = draft.trim().toUpperCase();
    if (!v || values.includes(v)) { setDraft(''); return; }
    onChange([...values, v]); setDraft('');
  }
  return (
    <div
      className="flex flex-wrap gap-1.5 items-center p-2 border rounded bg-surface min-h-[36px]"
      style={{ borderColor: 'var(--border)' }}
    >
      {values.map((v) => (
        <span
          key={v}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono rounded-sm"
          style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
        >
          {v}
          <button
            type="button"
            onClick={() => onChange(values.filter((x) => x !== v))}
            className="hover:opacity-70"
            aria-label={`Remove ${v}`}
          >
            <X size={11} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); } }}
        onBlur={add}
        className="flex-1 min-w-[80px] outline-none text-[12.5px] font-mono bg-transparent"
      />
    </div>
  );
}

function PolicyEditor({ policy, setPolicy, onSave, saving, savedAt, error }) {
  return (
    <Panel
      title="Guardrail policy"
      subtitle="Deterministic rules every offer must pass. AI proposes, guardrails gate."
      actions={
        <div className="flex items-center gap-3">
          {savedAt && (
            <Mono className="text-[10.5px] text-text-muted">
              saved · {savedAt.toLocaleTimeString()}
            </Mono>
          )}
          <button className="btn-primary" onClick={onSave} disabled={saving}>
            <Save size={13} /> {saving ? 'saving…' : 'Save'}
          </button>
        </div>
      }
    >
      <div className="space-y-7">
        <section>
          <div className="section-label mb-3">MARGIN &amp; DISCOUNT</div>
          <div className="space-y-5">
            <Slider
              label="Min margin"
              value={Number(policy.min_margin_percent)}
              min={0} max={50} step={0.5}
              onChange={(v) => setPolicy({ ...policy, min_margin_percent: v })}
              format={(v) => `${v.toFixed(1)} %`}
            />
            <Slider
              label="Max discount (no approval)"
              value={Number(policy.max_discount_percent)}
              min={0} max={50} step={0.5}
              onChange={(v) => setPolicy({ ...policy, max_discount_percent: v })}
              format={(v) => `${v.toFixed(1)} %`}
            />
            <Slider
              label="Max discount (with approval)"
              value={Number(policy.max_discount_with_approval_percent)}
              min={0} max={75} step={0.5}
              onChange={(v) => setPolicy({ ...policy, max_discount_with_approval_percent: v })}
              format={(v) => `${v.toFixed(1)} %`}
            />
          </div>
        </section>

        <section>
          <div className="section-label mb-3">REGIONS &amp; CURRENCY</div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider mb-2">
                Allowed regions
              </div>
              <ChipInput
                values={policy.allowed_regions}
                onChange={(v) => setPolicy({ ...policy, allowed_regions: v })}
                placeholder="add region…"
              />
            </div>
            <div>
              <div className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider mb-2">
                Currency allowlist
              </div>
              <ChipInput
                values={policy.currency_allowlist}
                onChange={(v) => setPolicy({ ...policy, currency_allowlist: v })}
                placeholder="ISO code…"
              />
            </div>
          </div>
        </section>

        <section>
          <div className="section-label mb-3">DEAL SIZE</div>
          <div className="grid grid-cols-3 gap-4">
            <NumField
              label="Min deal size (USD)"
              value={(policy.min_deal_size_cents / 100).toString()}
              onChange={(v) => setPolicy({ ...policy, min_deal_size_cents: Math.round(Number(v) * 100) })}
            />
            <NumField
              label="Max deal size (USD)"
              placeholder="no ceiling"
              value={policy.max_deal_size_cents == null ? '' : (policy.max_deal_size_cents / 100).toString()}
              onChange={(v) => setPolicy({
                ...policy,
                max_deal_size_cents: v === '' ? null : Math.round(Number(v) * 100),
              })}
            />
            <NumField
              label="Require approval above (USD)"
              value={(policy.require_approval_above_cents / 100).toString()}
              onChange={(v) => setPolicy({ ...policy, require_approval_above_cents: Math.round(Number(v) * 100) })}
            />
          </div>
        </section>

        {error && (
          <div
            className="p-3 rounded text-[12.5px]"
            style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}
          >
            {error}
          </div>
        )}
      </div>
    </Panel>
  );
}

function NumField({ label, value, onChange, placeholder }) {
  return (
    <div>
      <div className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider mb-2">
        {label}
      </div>
      <input
        type="number"
        step="0.01"
        min="0"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="input-field font-mono"
      />
    </div>
  );
}

function ImpactPreview({ policy }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!policy) return undefined;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.post('/tenant/guardrails/impact-preview', {
          min_margin_percent: Number(policy.min_margin_percent),
          max_discount_percent: Number(policy.max_discount_percent),
          max_discount_with_approval_percent: Number(policy.max_discount_with_approval_percent),
          allowed_regions: policy.allowed_regions,
          currency_allowlist: policy.currency_allowlist,
          min_deal_size_cents: policy.min_deal_size_cents,
          max_deal_size_cents: policy.max_deal_size_cents,
          require_approval_above_cents: policy.require_approval_above_cents,
          window_days: 7,
        });
        setResult(res.data); setError('');
      } catch (e) {
        setError(e.response?.data?.detail || 'preview failed');
      } finally { setLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    policy.min_margin_percent, policy.max_discount_percent,
    policy.max_discount_with_approval_percent, policy.min_deal_size_cents,
    policy.max_deal_size_cents, policy.require_approval_above_cents,
    JSON.stringify(policy.allowed_regions), JSON.stringify(policy.currency_allowlist),
  ]);

  return (
    <Panel
      title="Impact preview"
      subtitle="Last 7 days · re-evaluated against proposed policy"
      actions={loading ? <Mono className="text-[10.5px] text-text-muted">recomputing…</Mono> : null}
    >
      {error && (
        <div
          className="p-2.5 rounded text-[12px] mb-3"
          style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}
        >
          {error}
        </div>
      )}
      {!result ? (
        <div className="py-10 text-center text-text-muted text-[12.5px]">
          move a slider to evaluate
        </div>
      ) : result.events_evaluated === 0 ? (
        <div className="py-10 text-center text-text-muted text-[12.5px]">
          no recent activity to evaluate
        </div>
      ) : (
        <>
          <div className="space-y-2 mb-5">
            <StatDelta label="Would PASS"   current={result.current_pass}   proposed={result.would_pass}   delta={result.delta_pass}   variant="success" />
            <StatDelta label="Would REVIEW" current={result.current_review} proposed={result.would_review} delta={result.delta_review} variant="warning" />
            <StatDelta label="Would BLOCK"  current={result.current_block}  proposed={result.would_block}  delta={result.delta_block}  variant="danger" />
          </div>

          <div className="py-3 border-t border-border flex items-center justify-between">
            <span className="section-label">REVENUE IMPACT</span>
            <Mono
              className="text-[18px] font-semibold"
              style={{ color: result.revenue_impact < 0 ? 'var(--danger)' : 'var(--success)' }}
            >
              {result.revenue_impact < 0 ? '-' : '+'}${Math.abs(result.revenue_impact).toLocaleString()}
            </Mono>
          </div>

          {result.examples.length > 0 && (
            <div className="pt-3 border-t border-border">
              <div className="section-label mb-2">DEALS THAT WOULD CHANGE</div>
              <div className="space-y-1.5">
                {result.examples.map((ex) => {
                  const [from, to] = ex.change.split('→').map((s) => s.trim());
                  return (
                    <div key={ex.offer_id} className="flex items-center justify-between text-[12px]">
                      <span className="text-text-primary truncate flex-1 mr-2">
                        {ex.client_name || ex.offer_id.slice(0, 16)}
                      </span>
                      <Mono className="text-text-secondary mr-3 w-20 text-right">
                        ${(ex.total_cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </Mono>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono uppercase tracking-wider">
                        <span style={{ color: `var(--${VERDICT_VARIANT[from] || 'text-muted'})` }}>{from}</span>
                        <span className="text-text-muted">→</span>
                        <span style={{ color: `var(--${VERDICT_VARIANT[to] || 'text-muted'})` }}>{to}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function StatDelta({ label, current, proposed, delta, variant }) {
  const dirColor = delta > 0 ? 'var(--danger)' : delta < 0 ? 'var(--success)' : 'var(--text-muted)';
  return (
    <div className="flex items-center gap-3 text-[12.5px]">
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: `var(--${variant})` }}
      />
      <span className="flex-1 text-text-secondary">{label}</span>
      <Mono className="w-10 text-right text-text-primary font-semibold">{proposed}</Mono>
      <Mono className="w-10 text-right text-[11px]" style={{ color: dirColor }}>
        {delta > 0 ? `+${delta}` : delta === 0 ? '—' : delta}
      </Mono>
    </div>
  );
}

function Simulator() {
  // Kept as a collapsed utility panel — previously heavier; trimming since
  // the new Impact Preview carries the demo weight.
  const [region, setRegion] = useState('US');
  const [useAi, setUseAi] = useState(false);
  const [dealName, setDealName] = useState('');
  const [items, setItems] = useState([{ sku: '', quantity: 1, unit_price: '' }]);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  function setItem(i, k, v) { setItems(items.map((it, j) => j === i ? { ...it, [k]: v } : it)); }

  async function run() {
    setError(''); setResult(null); setRunning(true);
    try {
      const payload = {
        buyer_region: region, currency: 'USD', use_ai: useAi, buyer_deal_name: dealName,
        line_items: items.filter((it) => it.sku && (useAi || it.unit_price !== ''))
          .map((it) => ({ sku: it.sku, quantity: Number(it.quantity), unit_price: Number(it.unit_price || 0) })),
      };
      if (!payload.line_items.length) { setError('add at least one line item'); setRunning(false); return; }
      const res = await api.post('/tenant/guardrails/simulate', payload);
      setResult(res.data);
    } catch (e) {
      setError(e.response?.data?.detail ? JSON.stringify(e.response.data.detail) : 'simulate failed');
    } finally { setRunning(false); }
  }

  const verdict = result && (
    <Pill variant={VERDICT_VARIANT[result.verdict] || 'muted'}>{result.verdict}</Pill>
  );

  return (
    <Panel
      title="Simulator"
      subtitle="Evaluate a hypothetical deal against the current draft policy. Does not persist."
      actions={
        <button className="btn-primary" onClick={run} disabled={running}>
          <PlayCircle size={13} /> {running ? 'evaluating…' : 'Evaluate'}
        </button>
      }
    >
      <div className="grid grid-cols-2 gap-3 mb-3">
        <NumField label="Buyer region" value={region} onChange={setRegion} />
        <div>
          <div className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider mb-2">
            Use AI first
          </div>
          <SegmentedControl
            size="sm"
            options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]}
            active={useAi ? 'on' : 'off'}
            onChange={(v) => setUseAi(v === 'on')}
          />
        </div>
      </div>

      {useAi && (
        <div className="mb-3">
          <div className="text-[11.5px] text-text-secondary font-medium uppercase tracking-wider mb-2">
            Deal name (passes to AI / stub markers)
          </div>
          <input
            className="input-field font-mono"
            value={dealName}
            onChange={(e) => setDealName(e.target.value)}
            placeholder="stub:pass · stub:retry · stub:fail · stub:timeout"
          />
        </div>
      )}

      <div className="space-y-1.5 mb-2">
        {items.map((it, i) => (
          <div key={i} className="grid gap-2" style={{ gridTemplateColumns: '2fr 1fr 1.5fr auto' }}>
            <input className="input-field font-mono" placeholder="SKU"
              value={it.sku} onChange={(e) => setItem(i, 'sku', e.target.value)} />
            <input type="number" min="1" className="input-field font-mono" placeholder="qty"
              value={it.quantity} onChange={(e) => setItem(i, 'quantity', e.target.value)} />
            <input type="number" step="0.01" min="0" className="input-field font-mono" placeholder="unit price"
              value={it.unit_price} onChange={(e) => setItem(i, 'unit_price', e.target.value)} />
            <button className="icon-btn" onClick={() => setItems(items.filter((_, j) => j !== i))} disabled={items.length === 1}>
              <X size={13} className="text-text-muted" />
            </button>
          </div>
        ))}
      </div>
      <button
        className="text-[12px] text-accent hover:text-accent-hover inline-flex items-center gap-1"
        onClick={() => setItems([...items, { sku: '', quantity: 1, unit_price: '' }])}
      >
        <Plus size={13} /> add line
      </button>

      {error && (
        <div className="mt-3 p-2.5 rounded text-[12px]"
          style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}>{error}</div>
      )}

      {result && (
        <div className="mt-4 pt-4 border-t border-border space-y-3">
          <div className="flex items-center gap-3">
            {verdict}
            <Mono className="text-text-secondary text-[11.5px] ml-auto">
              total · ${(result.total_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </Mono>
          </div>

          {result.ai_attempts?.length > 0 && (
            <div>
              <div className="section-label mb-2">
                AI ATTEMPT CHAIN · {result.ai_backend}{result.ai_fell_back ? ' · fell back to base' : ''}
              </div>
              <div className="space-y-1.5">
                {result.ai_attempts.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11.5px]">
                    <Mono className="text-text-muted w-6">#{a.attempt_number}</Mono>
                    <Pill variant={VERDICT_VARIANT[a.verdict] || 'muted'}>{a.verdict}</Pill>
                    <Mono className="text-text-muted">{a.backend}</Mono>
                    <Mono className="text-text-muted ml-auto">{a.latency_ms}ms</Mono>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            {result.check_results.map((cr) => (
              <div key={cr.name}
                className="flex items-start gap-2.5 p-2 rounded"
                style={{ background: 'var(--bg-subtle)' }}>
                <Pill variant={VERDICT_VARIANT[cr.verdict] || 'muted'}>{cr.verdict}</Pill>
                <div className="flex-1 min-w-0">
                  <Mono className="text-[12px] text-text-primary font-medium">{cr.name}</Mono>
                  <div className="text-[11.5px] text-text-secondary">{cr.reason_internal}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

export default function Guardrails() {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try { const res = await api.get('/tenant/guardrails'); setPolicy(res.data); }
    catch (e) { setError(e.response?.data?.detail || 'failed to load policy'); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function save() {
    if (!policy) return;
    setError(''); setSaving(true);
    try {
      const res = await api.put('/tenant/guardrails', {
        min_margin_percent: Number(policy.min_margin_percent),
        max_discount_percent: Number(policy.max_discount_percent),
        max_discount_with_approval_percent: Number(policy.max_discount_with_approval_percent),
        allowed_regions: policy.allowed_regions,
        currency_allowlist: policy.currency_allowlist,
        min_deal_size_cents: policy.min_deal_size_cents,
        max_deal_size_cents: policy.max_deal_size_cents,
        require_approval_above_cents: policy.require_approval_above_cents,
      });
      setPolicy(res.data); setSavedAt(new Date());
    } catch (e) { setError(e.response?.data?.detail || 'save failed'); }
    finally { setSaving(false); }
  }

  if (loading) return <div className="text-[13px] text-text-muted">loading…</div>;
  if (!policy) return <div className="text-[13px] text-danger">{error || 'no policy'}</div>;

  return (
    <div className="page-enter grid gap-4" style={{ gridTemplateColumns: 'minmax(0, 60%) minmax(0, 40%)' }}>
      <div className="space-y-4 min-w-0">
        <PolicyEditor
          policy={policy} setPolicy={setPolicy}
          onSave={save} saving={saving} savedAt={savedAt} error={error}
        />
        <Simulator />
      </div>
      <div className="min-w-0">
        <div className="sticky top-6">
          <ImpactPreview policy={policy} />
        </div>
      </div>
    </div>
  );
}
