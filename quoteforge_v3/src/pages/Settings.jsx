import { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Sparkles, Mail, Shield, Save, Gavel } from 'lucide-react';
import api from '@/services/api';

const SECTIONS = [
  {
    title: 'General Settings', icon: SettingsIcon,
    fields: [
      { label: 'Organization Name', type: 'text', defaultValue: 'Acme Corporation', desc: 'Your company name used in generated documents' },
      { label: 'Default Currency', type: 'select', defaultValue: 'USD', options: ['USD', 'PKR', 'EUR', 'GBP'], desc: 'Default currency for quotes' },
      { label: 'Default Buyer Region', type: 'select', defaultValue: 'US', options: ['US', 'EU', 'APAC', 'UK'], desc: 'Default region for new deals' },
    ],
  },
  {
    title: 'AI Configuration', icon: Sparkles,
    fields: [
      { label: 'AI Model', type: 'select', defaultValue: 'GPT-4o', options: ['GPT-4o', 'GPT-4o-mini', 'Claude 3.5 Sonnet'], desc: 'LLM used for content generation' },
      { label: 'Temperature', type: 'text', defaultValue: '0.3', desc: 'Controls creativity (0.0 = deterministic, 1.0 = creative)' },
      { label: 'Max Tokens', type: 'text', defaultValue: '2048', desc: 'Maximum output length per section' },
    ],
  },
  {
    title: 'Email & Delivery', icon: Mail,
    fields: [
      { label: 'SMTP Host', type: 'text', defaultValue: 'smtp.sendgrid.net', desc: 'SMTP server for document delivery' },
      { label: 'Sender Email', type: 'text', defaultValue: 'quotes@acmecorp.com', desc: 'From address on delivered documents' },
      { label: 'Auto-deliver on Generation', type: 'toggle', defaultValue: true, desc: 'Automatically send documents after generation' },
    ],
  },
  {
    title: 'Security', icon: Shield,
    fields: [
      { label: 'Session Timeout (minutes)', type: 'text', defaultValue: '30', desc: 'Auto-logout after inactivity' },
      { label: 'Two-Factor Authentication', type: 'toggle', defaultValue: true, desc: 'Require 2FA for all users' },
      { label: 'API Rate Limit (req/min)', type: 'text', defaultValue: '60', desc: 'Maximum API requests per minute' },
    ],
  },
];

function ToggleSwitch({ defaultChecked }) {
  const [on, setOn] = useState(defaultChecked);
  return (
    <div
      onClick={() => setOn(!on)}
      className={`w-12 h-[26px] rounded-full p-[3px] cursor-pointer transition-colors duration-200 flex items-center ${
        on ? 'bg-brand-600' : 'bg-border-strong'
      }`}
    >
      <div
        className={`w-5 h-5 rounded-full bg-white  transition-transform duration-200 ${
          on ? 'translate-x-[22px]' : 'translate-x-0'
        }`}
      />
    </div>
  );
}

function NegotiationSection() {
  const [autoCommit, setAutoCommit] = useState(true);
  const [mode, setMode] = useState('deterministic');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('/tenant/config');
      setAutoCommit(!!res.data.auto_commit_enabled);
      setMode(res.data.negotiation_mode || 'deterministic');
    } catch (e) {
      setError(e.response?.data?.detail || 'failed to load tenant config');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function save() {
    setError('');
    setSaving(true);
    try {
      const res = await api.put('/tenant/config', {
        auto_commit_enabled: autoCommit,
        negotiation_mode: mode,
      });
      setAutoCommit(!!res.data.auto_commit_enabled);
      setMode(res.data.negotiation_mode || 'deterministic');
      setSavedAt(new Date());
    } catch (e) {
      setError(e.response?.data?.detail || 'save failed');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card p-5 mb-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded bg-brand-50 flex items-center justify-center">
          <Gavel size={20} className="text-brand-500" />
        </div>
        <h3 className="text-[13px] font-bold text-text-primary">Negotiation — Kill Switch</h3>
      </div>
      <p className="text-xs text-text-secondary mb-4">
        Per-SKU pricing rules — margin floors, discount ceilings, allowed regions — live on
        the <a href="/guardrails" className="text-brand-600 hover:text-brand-800 underline">Guardrail Policy</a> page.
        This section is the top-level kill switch that forces every deal into the approval queue.
      </p>

      {loading ? (
        <div className="text-sm text-text-muted">loading…</div>
      ) : (
        <>
          <div className="flex flex-col gap-4">
            <div className="flex justify-between items-center gap-8">
              <div className="flex-1">
                <label className="text-sm font-semibold text-text-primary block mb-0.5">Negotiation mode</label>
                <span className="text-xs text-text-muted">
                  <code>ai_first</code> routes quotes through the Negotiation AI with guardrail retries.
                  <code className="mx-1">deterministic</code> prices at catalog base — emergency kill switch.
                </span>
              </div>
              <div className="w-[280px] flex-shrink-0">
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="input-field w-full bg-white"
                >
                  <option value="deterministic">deterministic (catalog base prices)</option>
                  <option value="ai_first">ai_first (Negotiation AI)</option>
                </select>
              </div>
            </div>
            <div className="flex justify-between items-center gap-8">
              <div className="flex-1">
                <label className="text-sm font-semibold text-text-primary block mb-0.5">Auto-commit enabled</label>
                <span className="text-xs text-text-muted">
                  When off, every deal routes to approval regardless of amount.
                </span>
              </div>
              <div className="w-[280px] flex-shrink-0 flex justify-end">
                <div
                  onClick={() => setAutoCommit(!autoCommit)}
                  className={`w-12 h-[26px] rounded-full p-[3px] cursor-pointer transition-colors duration-200 flex items-center ${
                    autoCommit ? 'bg-brand-600' : 'bg-border-strong'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-full bg-white  transition-transform duration-200 ${
                      autoCommit ? 'translate-x-[22px]' : 'translate-x-0'
                    }`}
                  />
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="mt-3 p-2 bg-danger-muted border border-danger text-danger text-sm rounded">
              {error}
            </div>
          )}

          <div className="flex justify-end items-center gap-3 mt-4 border-t border-border pt-3">
            {savedAt && (
              <span className="text-xs text-text-muted">saved {savedAt.toLocaleTimeString()}</span>
            )}
            <button className="btn-primary" onClick={save} disabled={saving}>
              <Save size={14} /> {saving ? 'saving…' : 'Save'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function Settings() {
  return (
    <div className="page-enter max-w-[800px]">
      <NegotiationSection />
      {SECTIONS.map((section, si) => {
        const Icon = section.icon;
        return (
          <div
            key={si}
            className="card p-5 mb-4 "
            
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 rounded bg-brand-50 flex items-center justify-center">
                <Icon size={20} className="text-brand-500" />
              </div>
              <h3 className="text-[13px] font-bold text-text-primary">{section.title}</h3>
            </div>

            <div className="flex flex-col gap-4">
              {section.fields.map((field) => (
                <div key={field.label} className="flex justify-between items-center gap-8">
                  <div className="flex-1">
                    <label className="text-sm font-semibold text-text-primary block mb-0.5">{field.label}</label>
                    <span className="text-xs text-text-muted">{field.desc}</span>
                  </div>
                  <div className="w-[280px] flex-shrink-0">
                    {field.type === 'toggle' ? (
                      <div className="flex justify-end">
                        <ToggleSwitch defaultChecked={field.defaultValue} />
                      </div>
                    ) : field.type === 'select' ? (
                      <select defaultValue={field.defaultValue} className="input-field bg-white">
                        {field.options.map((o) => <option key={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input defaultValue={field.defaultValue} className="input-field" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Save Actions */}
      <div className="flex justify-end gap-3 mt-2">
        <button className="btn-secondary">Cancel</button>
        <button className="btn-primary">
          <Save size={16} /> Save All Changes
        </button>
      </div>
    </div>
  );
}
