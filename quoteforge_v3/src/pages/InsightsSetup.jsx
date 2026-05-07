import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, ArrowLeft, Plus, X, Database, Check, Brain } from 'lucide-react';
import { Panel, Pill, Mono, SegmentedControl } from '@/components/ui';
import api from '@/services/api';
import toast from 'react-hot-toast';

/*
 * Deal Insights — three-step mapping wizard.
 *
 *   1. Scan    — inspect the customer's Salesforce schema.
 *   2. Map     — admin reviews + edits auto-suggested field mapping.
 *                Can add custom features from their own schema.
 *   3. Exclude — record types to omit from training.
 *
 * Submit → POST /api/insights/mapping. A link to /insights/models appears on
 * completion; from there the admin triggers the first training run.
 */

const REQUIRED_FIELDS = [
  { key: 'amount_field',        label: 'Amount field',        hint: 'The currency column for deal size.' },
  { key: 'stage_field',         label: 'Stage field',         hint: 'Pipeline stage (picklist).' },
  { key: 'close_date_field',    label: 'Close date field',    hint: 'Expected close date.' },
  { key: 'created_date_field',  label: 'Created date field',  hint: 'Opportunity creation timestamp.' },
  { key: 'is_closed_field',     label: 'IsClosed flag',       hint: 'Boolean — is the Opportunity closed?' },
  { key: 'is_won_field',        label: 'IsWon flag',          hint: 'Boolean — was it closed won?' },
];

const OPTIONAL_FIELDS = [
  { key: 'industry_field',    label: 'Industry (Account)', hint: 'For categorical signal.' },
  { key: 'lead_source_field', label: 'Lead source',        hint: 'Channel attribution.' },
  { key: 'owner_field',       label: 'Owner ID',           hint: 'Per-rep effects.' },
  { key: 'record_type_field', label: 'Record type',        hint: 'Helps exclude test/demo Opps.' },
];

export default function InsightsSetup() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [schema, setSchema] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [customModalOpen, setCustomModalOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [sRes, mRes] = await Promise.all([
          api.get('/insights/schema'),
          api.get('/insights/mapping'),
        ]);
        setSchema(sRes.data);
        setMapping(mRes.data);
      } catch (e) {
        toast.error(e.response?.data?.detail || 'Failed to load schema');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const fieldOptions = useMemo(() => {
    if (!schema) return [];
    return schema.opportunity_fields.map((f) => ({
      value: f.api_name,
      label: `${f.api_name} — ${f.label} (${f.type})`,
    }));
  }, [schema]);

  function updateField(key, val) {
    setMapping((m) => ({ ...m, [key]: val === '' ? null : val }));
  }

  async function handleSubmit() {
    setSaving(true);
    try {
      const payload = {
        ...mapping,
        auto_suggested: false,
        custom_fields: (mapping.custom_fields || []).map((cf) => ({
          sf_field: cf.sf_field,
          feature_name: cf.feature_name,
          type: cf.type,
        })),
      };
      delete payload.id;
      delete payload.tenant_id;
      delete payload.suggestions;
      const res = await api.post('/insights/mapping', payload);
      setMapping(res.data);
      toast.success('Mapping saved. Head to Models to train.');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save mapping');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page-enter">
        <Panel padded>
          <div className="flex items-center gap-3 py-8 justify-center text-text-muted">
            <Database className="animate-pulse" size={16} />
            <span className="text-[12.5px]">Scanning your Salesforce schema…</span>
          </div>
        </Panel>
      </div>
    );
  }
  if (!schema || !mapping) {
    return (
      <div className="page-enter">
        <Panel padded>
          <div className="py-8 text-center text-text-muted">
            Unable to load schema. Connect Salesforce on the CRM page first.
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="page-enter">
      {/* ── Wizard stepper header ─────────────────────────── */}
      <div className="mb-4">
        <SegmentedControl
          options={[
            { value: 1, label: '1 · Scan',     count: undefined },
            { value: 2, label: '2 · Map',      count: undefined },
            { value: 3, label: '3 · Exclude',  count: undefined },
          ]}
          active={step}
          onChange={setStep}
        />
      </div>

      {step === 1 && (
        <ScanStep schema={schema} onNext={() => setStep(2)} />
      )}

      {step === 2 && (
        <MapStep
          schema={schema}
          mapping={mapping}
          fieldOptions={fieldOptions}
          onChange={updateField}
          onAddCustom={() => setCustomModalOpen(true)}
          onRemoveCustom={(idx) => setMapping((m) => ({
            ...m, custom_fields: m.custom_fields.filter((_, i) => i !== idx),
          }))}
          onBack={() => setStep(1)}
          onNext={() => setStep(3)}
        />
      )}

      {step === 3 && (
        <ExcludeStep
          schema={schema}
          mapping={mapping}
          onToggle={(rtId, included) => setMapping((m) => ({
            ...m,
            excluded_record_types: included
              ? m.excluded_record_types.filter((x) => x !== rtId)
              : [...m.excluded_record_types, rtId],
          }))}
          onBack={() => setStep(2)}
          onSubmit={handleSubmit}
          saving={saving}
        />
      )}

      {customModalOpen && (
        <CustomFieldModal
          schema={schema}
          onClose={() => setCustomModalOpen(false)}
          onAdd={(cf) => {
            setMapping((m) => ({ ...m, custom_fields: [...(m.custom_fields || []), cf] }));
            setCustomModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

// ─── Step 1 — Scan ────────────────────────────────────────────

function ScanStep({ schema, onNext }) {
  return (
    <Panel padded>
      <div className="flex items-start gap-4">
        <div
          className="flex-shrink-0 w-10 h-10 rounded flex items-center justify-center"
          style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
        >
          <Database size={18} />
        </div>
        <div className="flex-grow">
          <div className="text-[13.5px] font-semibold text-text-primary mb-1">
            Schema inspection complete
          </div>
          <div className="text-[12.5px] text-text-secondary mb-3">
            {schema.connected
              ? 'Connected to your Salesforce org.'
              : 'No active Salesforce connection — using stock Opportunity schema as a working draft.'}
          </div>

          <div className="grid grid-cols-4 gap-3 mb-4">
            <SummaryBlock label="Opportunities" value={schema.opportunity_count.toLocaleString()} />
            <SummaryBlock label="Total fields"  value={schema.opportunity_fields.length} />
            <SummaryBlock label="Custom fields" value={schema.custom_fields.length} />
            <SummaryBlock label="Record types"  value={schema.record_types.length} />
          </div>

          <div className="flex justify-end">
            <button className="btn-primary" onClick={onNext}>
              Continue to mapping <ArrowRight size={13} />
            </button>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function SummaryBlock({ label, value }) {
  return (
    <div
      className="p-3 rounded"
      style={{ background: 'var(--surface-raised)', border: '1px solid var(--border)' }}
    >
      <div className="text-[10.5px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className="text-[17px] font-semibold text-text-primary mt-1 font-mono">{value}</div>
    </div>
  );
}

// ─── Step 2 — Map ────────────────────────────────────────────

function MapStep({
  schema, mapping, fieldOptions, onChange,
  onAddCustom, onRemoveCustom, onBack, onNext,
}) {
  const suggestionsByField = Object.fromEntries(
    (mapping.suggestions || []).map((s) => [s.field, s]),
  );

  return (
    <div className="space-y-4">
      <Panel padded>
        <div className="text-[13.5px] font-semibold text-text-primary mb-1">
          Required fields
        </div>
        <div className="text-[12px] text-text-muted mb-4">
          These drive the training target + core features. Defaults come from auto-suggest.
        </div>
        <div className="space-y-3">
          {REQUIRED_FIELDS.map((f) => (
            <MappingRow
              key={f.key}
              field={f}
              value={mapping[f.key] || ''}
              options={fieldOptions}
              suggestion={suggestionsByField[f.key]}
              onChange={(v) => onChange(f.key, v)}
            />
          ))}
        </div>
      </Panel>

      <Panel padded>
        <div className="text-[13.5px] font-semibold text-text-primary mb-1">
          Optional feature fields
        </div>
        <div className="text-[12px] text-text-muted mb-4">
          Used as one-hot categoricals. Leave blank to omit from the model.
        </div>
        <div className="space-y-3">
          {OPTIONAL_FIELDS.map((f) => (
            <MappingRow
              key={f.key}
              field={f}
              value={mapping[f.key] || ''}
              options={[{ value: '', label: '— none —' }, ...fieldOptions]}
              suggestion={suggestionsByField[f.key]}
              onChange={(v) => onChange(f.key, v)}
            />
          ))}
        </div>
      </Panel>

      <Panel padded>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[13.5px] font-semibold text-text-primary">Custom features</div>
            <div className="text-[12px] text-text-muted">
              Pull any custom field from your schema into the model.
            </div>
          </div>
          <button className="btn-secondary" onClick={onAddCustom}>
            <Plus size={13} /> Add custom feature
          </button>
        </div>
        {(mapping.custom_fields || []).length === 0 ? (
          <div className="text-[12px] text-text-muted py-3">
            No custom features yet.
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-header">Salesforce field</th>
                <th className="table-header">Feature name</th>
                <th className="table-header">Type</th>
                <th className="table-header" style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {mapping.custom_fields.map((cf, i) => (
                <tr key={`${cf.sf_field}-${i}`} className="table-row">
                  <td className="table-cell"><Mono>{cf.sf_field}</Mono></td>
                  <td className="table-cell font-medium">{cf.feature_name}</td>
                  <td className="table-cell">
                    <Pill variant="info">{cf.type}</Pill>
                  </td>
                  <td className="table-cell">
                    <button className="icon-btn" onClick={() => onRemoveCustom(i)} title="Remove">
                      <X size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="flex items-center justify-between">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft size={13} /> Back
        </button>
        <button className="btn-primary" onClick={onNext}>
          Continue <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
}

function MappingRow({ field, value, options, suggestion, onChange }) {
  return (
    <div className="grid grid-cols-[220px_1fr] gap-3 items-start">
      <div>
        <div className="text-[12.5px] font-medium text-text-primary">
          {field.label}
          {suggestion && suggestion.confidence >= 0.7 && (
            <span className="ml-2 text-[10.5px] font-mono"
                  style={{ color: 'var(--accent)' }}>
              auto · {Math.round(suggestion.confidence * 100)}%
            </span>
          )}
        </div>
        <div className="text-[11px] text-text-muted mt-0.5">{field.hint}</div>
      </div>
      <div>
        <select
          className="input-field font-mono w-full"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {suggestion?.reason && (
          <div className="text-[10.5px] text-text-muted mt-1">{suggestion.reason}</div>
        )}
      </div>
    </div>
  );
}

// ─── Step 3 — Exclude ────────────────────────────────────────

function ExcludeStep({ schema, mapping, onToggle, onBack, onSubmit, saving }) {
  const hasRecordTypes = schema.record_types.length > 0;
  return (
    <div className="space-y-4">
      <Panel padded>
        <div className="text-[13.5px] font-semibold text-text-primary mb-1">
          Record type exclusions
        </div>
        <div className="text-[12px] text-text-muted mb-4">
          Uncheck any record type you don't want included in training
          (e.g. internal / demo Opportunities).
        </div>
        {!hasRecordTypes ? (
          <div className="py-3 text-[12px] text-text-muted">
            No record types detected in your org — nothing to exclude.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {schema.record_types.map((rt) => {
              const included = !mapping.excluded_record_types.includes(rt.id);
              return (
                <label
                  key={rt.id}
                  className="flex items-start gap-2 p-2 rounded cursor-pointer"
                  style={{ background: 'var(--surface-raised)', border: '1px solid var(--border)' }}
                >
                  <input
                    type="checkbox"
                    checked={included}
                    onChange={() => onToggle(rt.id, included)}
                  />
                  <div>
                    <div className="text-[12.5px] font-medium">{rt.name}</div>
                    <div className="text-[10.5px] text-text-muted font-mono">{rt.id}</div>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </Panel>

      <div className="flex items-center justify-between">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft size={13} /> Back
        </button>
        <button className="btn-primary" onClick={onSubmit} disabled={saving}>
          {saving ? 'saving…' : (
            <>Save mapping <Check size={13} /></>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Custom feature modal ────────────────────────────────────

function CustomFieldModal({ schema, onClose, onAdd }) {
  const [sfField, setSfField] = useState(schema.custom_fields[0]?.api_name || '');
  const [featureName, setFeatureName] = useState('');
  const [type, setType] = useState('categorical');

  const selectable = schema.custom_fields.length > 0 ? schema.custom_fields : schema.opportunity_fields;

  function submit(e) {
    e.preventDefault();
    if (!sfField || !featureName) return;
    onAdd({ sf_field: sfField, feature_name: featureName.trim(), type });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ background: 'rgba(0,0,0,0.4)' }}
    >
      <form
        onSubmit={submit}
        className="bg-surface border border-border rounded w-full max-w-[460px]"
        style={{ boxShadow: 'var(--shadow-pop)' }}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="text-[13px] font-semibold text-text-primary">Add custom feature</div>
          <button type="button" className="icon-btn" onClick={onClose}><X size={13} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <div className="section-label mb-1.5">Salesforce field</div>
            <select
              className="input-field font-mono w-full"
              value={sfField}
              onChange={(e) => setSfField(e.target.value)}
            >
              {selectable.map((f) => (
                <option key={f.api_name} value={f.api_name}>
                  {f.api_name} — {f.label} ({f.type})
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="section-label mb-1.5">Feature name (used inside the model)</div>
            <input
              className="input-field font-mono w-full"
              value={featureName}
              onChange={(e) => setFeatureName(e.target.value.replace(/[^a-zA-Z0-9_]/g, '_'))}
              placeholder="priority"
              required
            />
          </div>
          <div>
            <div className="section-label mb-1.5">Type</div>
            <SegmentedControl
              options={[
                { value: 'numeric',     label: 'Numeric' },
                { value: 'categorical', label: 'Categorical' },
                { value: 'boolean',     label: 'Boolean' },
              ]}
              active={type}
              onChange={setType}
            />
          </div>
        </div>
        <div className="px-5 py-3 border-t border-border flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary">Add feature</button>
        </div>
      </form>
    </div>
  );
}
