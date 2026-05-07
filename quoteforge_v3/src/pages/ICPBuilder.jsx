import { useEffect, useMemo, useState } from 'react';
import { Plus, X, Check, Play, Trash2 } from 'lucide-react';
import { Panel, Pill, Mono, SegmentedControl, Slider } from '@/components/ui';
import api from '@/services/api';
import toast from 'react-hot-toast';

/*
 * ICP Builder — Phase 3 admin page.
 *
 *   Left column  — list of ICPs with create/activate/delete. Active badge.
 *   Right column — form: identity + hard filters + soft signals & weights.
 *                  Bottom of the form is a "Test panel" that takes an Opp Id
 *                  and renders the match score + reason list.
 */

const EMPTY_ICP = {
  name: '',
  description: '',
  included_industries: [],
  included_regions: [],
  min_amount: '',
  max_amount: '',
  min_employee_count: '',
  max_employee_count: '',
  required_lead_sources: [],
  min_engagement_score: '',
  weight_industry_match: 1.0,
  weight_region_match: 0.8,
  weight_amount_fit: 1.0,
  weight_engagement: 1.2,
  weight_lead_source: 0.7,
};

export default function ICPBuilder() {
  const [icps, setIcps] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(EMPTY_ICP);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testOppId, setTestOppId] = useState('006gL00000KlPp8QAF');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const res = await api.get('/icp');
      setIcps(res.data);
      if (res.data.length && !selectedId) {
        const active = res.data.find((i) => i.is_active) || res.data[0];
        loadIcp(active);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'failed to load ICPs');
    } finally { setLoading(false); }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);

  function loadIcp(icp) {
    setSelectedId(icp.id);
    setDraft({
      ...EMPTY_ICP,
      ...icp,
      min_amount: icp.min_amount ?? '',
      max_amount: icp.max_amount ?? '',
      min_employee_count: icp.min_employee_count ?? '',
      max_employee_count: icp.max_employee_count ?? '',
      min_engagement_score: icp.min_engagement_score ?? '',
    });
    setTestResult(null);
  }

  function newIcp() {
    setSelectedId(null);
    setDraft({ ...EMPTY_ICP });
    setTestResult(null);
  }

  async function save() {
    setSaving(true);
    try {
      const payload = {
        ...draft,
        min_amount: draft.min_amount === '' ? null : Number(draft.min_amount),
        max_amount: draft.max_amount === '' ? null : Number(draft.max_amount),
        min_employee_count: draft.min_employee_count === '' ? null : Number(draft.min_employee_count),
        max_employee_count: draft.max_employee_count === '' ? null : Number(draft.max_employee_count),
        min_engagement_score: draft.min_engagement_score === '' ? null : Number(draft.min_engagement_score),
      };
      delete payload.id;
      delete payload.tenant_id;
      delete payload.is_active;
      delete payload.created_at;
      delete payload.updated_at;
      let res;
      if (selectedId) res = await api.put(`/icp/${selectedId}`, payload);
      else res = await api.post('/icp', payload);
      toast.success(selectedId ? 'ICP updated' : 'ICP created');
      await refresh();
      loadIcp(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'save failed');
    } finally { setSaving(false); }
  }

  async function activate(id) {
    try {
      await api.post(`/icp/${id}/activate`);
      toast.success('activated');
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'activate failed'); }
  }

  async function remove(id) {
    if (!confirm('Delete this ICP?')) return;
    try {
      await api.delete(`/icp/${id}`);
      toast.success('deleted');
      newIcp();
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'delete failed'); }
  }

  async function runTest() {
    if (!testOppId.trim()) return;
    setTesting(true);
    try {
      const res = await api.get(`/icp/score/${testOppId.trim()}`);
      setTestResult(res.data);
    } catch (e) {
      setTestResult({ error: e.response?.data?.detail || 'score failed' });
    } finally { setTesting(false); }
  }

  return (
    <div className="page-enter">
      <div className="grid grid-cols-[280px_1fr] gap-4">
        {/* ── ICP list ────────────────────────────────── */}
        <Panel padded={false}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="text-[13px] font-semibold text-text-primary">ICPs</div>
            <button className="btn-primary" onClick={newIcp}>
              <Plus size={13} /> New
            </button>
          </div>
          {loading ? (
            <div className="p-6 text-center text-text-muted text-[12.5px]">loading…</div>
          ) : icps.length === 0 ? (
            <div className="p-6 text-center text-text-muted text-[12.5px]">
              No ICPs yet. Create one to start scoring deals.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {icps.map((i) => (
                <li key={i.id}>
                  <button
                    className="w-full text-left px-4 py-3 hover:bg-surface-raised"
                    onClick={() => loadIcp(i)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="text-[12.5px] font-medium text-text-primary truncate">
                        {i.name}
                      </div>
                      {i.is_active && <Pill variant="success">active</Pill>}
                    </div>
                    {i.description && (
                      <div className="text-[11px] text-text-muted truncate mt-0.5">
                        {i.description}
                      </div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* ── Editor + test panel ───────────────────── */}
        <div className="space-y-4">
          <Panel padded>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-[13.5px] font-semibold text-text-primary">
                  {selectedId ? 'Edit ICP' : 'Create ICP'}
                </div>
                <div className="text-[11.5px] text-text-muted">
                  Hard filters exclude deals outright. Soft signals contribute to match score.
                </div>
              </div>
              {selectedId && (
                <div className="flex gap-2">
                  {!draft.is_active && (
                    <button className="btn-secondary" onClick={() => activate(selectedId)}>
                      <Check size={13} /> Set active
                    </button>
                  )}
                  <button className="icon-btn" onClick={() => remove(selectedId)} title="Delete">
                    <Trash2 size={13} style={{ color: 'var(--danger)' }} />
                  </button>
                </div>
              )}
            </div>

            {/* Identity */}
            <Section title="Identity">
              <Row label="Name">
                <input className="input-field" value={draft.name}
                       onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                       placeholder="Enterprise SaaS" />
              </Row>
              <Row label="Description">
                <textarea className="input-field" rows={2} value={draft.description || ''}
                          onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
              </Row>
            </Section>

            {/* Hard filters */}
            <Section title="Hard filters (inclusion)">
              <Row label="Industries (comma-sep)">
                <input className="input-field font-mono"
                       value={draft.included_industries.join(', ')}
                       onChange={(e) => setDraft({ ...draft,
                         included_industries: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
              </Row>
              <Row label="Regions / countries">
                <input className="input-field font-mono"
                       value={draft.included_regions.join(', ')}
                       onChange={(e) => setDraft({ ...draft,
                         included_regions: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
              </Row>
              <div className="grid grid-cols-2 gap-3">
                <Row label="Min amount">
                  <input className="input-field font-mono" type="number"
                         value={draft.min_amount}
                         onChange={(e) => setDraft({ ...draft, min_amount: e.target.value })} />
                </Row>
                <Row label="Max amount">
                  <input className="input-field font-mono" type="number"
                         value={draft.max_amount}
                         onChange={(e) => setDraft({ ...draft, max_amount: e.target.value })} />
                </Row>
                <Row label="Min employees">
                  <input className="input-field font-mono" type="number"
                         value={draft.min_employee_count}
                         onChange={(e) => setDraft({ ...draft, min_employee_count: e.target.value })} />
                </Row>
                <Row label="Max employees">
                  <input className="input-field font-mono" type="number"
                         value={draft.max_employee_count}
                         onChange={(e) => setDraft({ ...draft, max_employee_count: e.target.value })} />
                </Row>
              </div>
            </Section>

            {/* Soft signals */}
            <Section title="Soft signals & weights">
              <Row label="Preferred lead sources">
                <input className="input-field font-mono"
                       value={draft.required_lead_sources.join(', ')}
                       onChange={(e) => setDraft({ ...draft,
                         required_lead_sources: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
              </Row>
              <Row label="Min engagement score (0-1)">
                <input className="input-field font-mono" type="number" step="0.05"
                       value={draft.min_engagement_score}
                       onChange={(e) => setDraft({ ...draft, min_engagement_score: e.target.value })} />
              </Row>
              <WeightRow label="Industry match" value={draft.weight_industry_match}
                         onChange={(v) => setDraft({ ...draft, weight_industry_match: v })} />
              <WeightRow label="Region match" value={draft.weight_region_match}
                         onChange={(v) => setDraft({ ...draft, weight_region_match: v })} />
              <WeightRow label="Amount fit" value={draft.weight_amount_fit}
                         onChange={(v) => setDraft({ ...draft, weight_amount_fit: v })} />
              <WeightRow label="Engagement" value={draft.weight_engagement}
                         onChange={(v) => setDraft({ ...draft, weight_engagement: v })} />
              <WeightRow label="Lead source" value={draft.weight_lead_source}
                         onChange={(v) => setDraft({ ...draft, weight_lead_source: v })} />
            </Section>

            <div className="flex justify-end gap-2 mt-4">
              <button className="btn-secondary" onClick={newIcp}>Cancel</button>
              <button className="btn-primary" onClick={save} disabled={saving || !draft.name}>
                {saving ? 'saving…' : selectedId ? 'Save changes' : 'Create ICP'}
              </button>
            </div>
          </Panel>

          {/* Test panel */}
          <Panel padded>
            <div className="text-[13px] font-semibold text-text-primary mb-1">Test this ICP</div>
            <div className="text-[11.5px] text-text-muted mb-3">
              Paste an Opportunity Id (or use the default Golden Opp) to see the score + reasons.
            </div>
            <div className="flex gap-2">
              <input className="input-field font-mono flex-grow" value={testOppId}
                     onChange={(e) => setTestOppId(e.target.value)}
                     placeholder="006..." />
              <button className="btn-primary" onClick={runTest} disabled={testing}>
                <Play size={13} /> {testing ? 'scoring…' : 'Score'}
              </button>
            </div>
            {testResult && (
              <div className="mt-3">
                {testResult.error ? (
                  <div className="p-3 rounded text-[12.5px]"
                       style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}>
                    {testResult.error}
                  </div>
                ) : (
                  <div>
                    <div className="flex items-baseline gap-3 mb-2">
                      <div className="text-[28px] font-bold font-mono text-text-primary">
                        {testResult.match_percent}%
                      </div>
                      <Pill variant={testResult.band === 'strong' ? 'success'
                                   : testResult.band === 'partial' ? 'warning' : 'danger'}>
                        {testResult.band} fit
                      </Pill>
                      <div className="text-[11.5px] text-text-muted">
                        against <span className="font-mono">{testResult.icp_name}</span>
                      </div>
                    </div>
                    <ul className="space-y-1">
                      {testResult.match_reasons.map((r, i) => (
                        <li key={i} className="flex items-start gap-2 text-[12px]">
                          <span className="font-mono text-text-muted uppercase tracking-wider text-[10.5px] w-[72px] flex-shrink-0 pt-0.5">
                            {r.factor}
                          </span>
                          <Pill variant={r.status === 'match' ? 'success'
                                        : r.status === 'partial' ? 'warning' : 'danger'}>
                            {r.status}
                          </Pill>
                          <span className="text-text-secondary">{r.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mb-4">
      <div className="section-label mb-2">{title}</div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <label className="grid grid-cols-[170px_1fr] gap-2 items-start">
      <div className="text-[12px] text-text-secondary pt-1">{label}</div>
      {children}
    </label>
  );
}

function WeightRow({ label, value, onChange }) {
  return (
    <label className="grid grid-cols-[170px_1fr_48px] gap-2 items-center">
      <div className="text-[12px] text-text-secondary">{label}</div>
      <input type="range" min="0" max="2" step="0.1" value={value}
             onChange={(e) => onChange(parseFloat(e.target.value))}
             className="w-full" />
      <div className="font-mono text-[12px] text-text-primary text-right">
        {Number(value).toFixed(1)}
      </div>
    </label>
  );
}
