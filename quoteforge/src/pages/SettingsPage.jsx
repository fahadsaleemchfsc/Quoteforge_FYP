import { useState } from 'react';
import { Settings, Sparkles, Mail, Shield, Save } from 'lucide-react';
import { settingsSections } from '@data/mockData';

const ICON_MAP = { Settings, Sparkles, Mail, Shield };

function ToggleSwitch({ defaultValue }) {
  const [on, setOn] = useState(defaultValue);
  return (
    <div className="flex justify-end">
      <button
        onClick={() => setOn(!on)}
        className={`w-12 h-[26px] rounded-full p-[3px] cursor-pointer transition-colors duration-200 ${on ? 'bg-brand-500' : 'bg-gray-300'}`}
      >
        <div className={`w-5 h-5 rounded-full bg-white shadow transition-transform duration-200 ${on ? 'translate-x-[22px]' : 'translate-x-0'}`} />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className="page-enter max-w-3xl">
      {settingsSections.map((section, si) => {
        const Icon = ICON_MAP[section.icon];
        return (
          <div key={si} className="card mb-5">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center">
                <Icon size={20} className="text-brand-500" />
              </div>
              <h3 className="section-title">{section.title}</h3>
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
                      <ToggleSwitch defaultValue={field.value} />
                    ) : field.type === 'select' ? (
                      <select defaultValue={field.value} className="input bg-white">
                        {field.options.map((o) => <option key={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input defaultValue={field.value} className="input" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* ─── Save ─── */}
      <div className="flex justify-end gap-3 mt-2">
        <button className="btn-secondary">Cancel</button>
        <button className="btn-primary"><Save size={16} /> Save All Changes</button>
      </div>
    </div>
  );
}
