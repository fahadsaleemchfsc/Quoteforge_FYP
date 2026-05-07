import { useState } from 'react';
import { Settings as SettingsIcon, Sparkles, Mail, Shield, Save } from 'lucide-react';

const SECTIONS = [
  {
    title: 'General Settings', icon: SettingsIcon,
    fields: [
      { label: 'Organization Name', type: 'text', defaultValue: 'Acme Corporation', desc: 'Your company name used in generated documents' },
      { label: 'Default Currency', type: 'select', defaultValue: 'USD', options: ['USD', 'PKR', 'EUR', 'GBP'], desc: 'Default currency for quotes' },
      { label: 'Default Compliance Region', type: 'select', defaultValue: 'US (SOC 2 + GDPR)', options: ['US (SOC 2 + GDPR)', 'PK (PPRA)', 'EU (GDPR)'], desc: 'Default regulatory framework' },
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
        on ? 'bg-brand-500' : 'bg-gray-300'
      }`}
    >
      <div
        className={`w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          on ? 'translate-x-[22px]' : 'translate-x-0'
        }`}
      />
    </div>
  );
}

export default function Settings() {
  return (
    <div className="page-enter max-w-[800px]">
      {SECTIONS.map((section, si) => {
        const Icon = section.icon;
        return (
          <div
            key={si}
            className="card p-7 mb-5 animate-slide-up"
            style={{ animationDelay: `${si * 0.1}s` }}
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center">
                <Icon size={20} className="text-brand-500" />
              </div>
              <h3 className="text-base font-bold text-gray-900">{section.title}</h3>
            </div>

            <div className="flex flex-col gap-5">
              {section.fields.map((field) => (
                <div key={field.label} className="flex justify-between items-center gap-8">
                  <div className="flex-1">
                    <label className="text-sm font-semibold text-gray-700 block mb-0.5">{field.label}</label>
                    <span className="text-xs text-gray-400">{field.desc}</span>
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
