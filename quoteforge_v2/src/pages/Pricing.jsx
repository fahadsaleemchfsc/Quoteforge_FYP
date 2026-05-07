import { useState } from 'react';
import { Plus, Edit3, Trash2, Globe, Shield, Lock, CheckCircle } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { PRICING_RULES } from '@/constants/mockData';
import clsx from 'clsx';

const TYPE_STYLES = {
  Discount:   { bg: 'bg-green-100', text: 'text-green-800' },
  Tax:        { bg: 'bg-amber-100', text: 'text-amber-800' },
  Compliance: { bg: 'bg-blue-100',  text: 'text-blue-800' },
};

const COMPLIANCE_CARDS = [
  {
    title: 'SOC 2', desc: 'U.S. security compliance', icon: Shield, color: '#6366f1',
    items: ['Data encryption in transit', 'Access logging enabled', 'No PII persistence'],
  },
  {
    title: 'GDPR', desc: 'EU data protection', icon: Lock, color: '#06b6d4',
    items: ['Consent tracking', 'Data minimization', 'Right to deletion'],
  },
  {
    title: 'PPRA', desc: 'Pakistan procurement', icon: Globe, color: '#10b981',
    items: ['Procurement clauses', 'Tax compliance (17% GST)', 'Transparency requirements'],
  },
];

export default function Pricing() {
  const [tab, setTab] = useState('all');
  const types = ['all', 'Discount', 'Tax', 'Compliance'];
  const filtered = tab === 'all' ? PRICING_RULES : PRICING_RULES.filter((r) => r.type === tab);

  return (
    <div className="page-enter">
      {/* ─── Filters & Actions ───────────────── */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex gap-2">
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx('filter-btn capitalize', t === tab ? 'filter-btn-active' : 'filter-btn-inactive')}
            >
              {t === 'all' ? 'All Rules' : t}
            </button>
          ))}
        </div>
        <button className="btn-primary">
          <Plus size={18} /> Add Rule
        </button>
      </div>

      {/* ─── Rules Table ─────────────────────── */}
      <div className="card overflow-hidden mb-6">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50">
              {['Rule Name', 'Type', 'Condition', 'Value', 'Region', 'Status', 'Actions'].map((h) => (
                <th key={h} className="table-header">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((rule, i) => {
              const ts = TYPE_STYLES[rule.type];
              return (
                <tr key={rule.id} className="table-row animate-slide-up" style={{ animationDelay: `${i * 0.04}s` }}>
                  <td className="table-cell font-semibold text-gray-900">{rule.name}</td>
                  <td className="table-cell">
                    <span className={clsx('px-2.5 py-0.5 rounded-md text-xs font-medium', ts.bg, ts.text)}>
                      {rule.type}
                    </span>
                  </td>
                  <td className="table-cell text-gray-500 font-mono text-sm">{rule.condition}</td>
                  <td className="table-cell font-semibold text-gray-900">{rule.value}</td>
                  <td className="table-cell">
                    <span className="inline-flex items-center gap-1.5 text-sm text-gray-500">
                      <Globe size={14} /> {rule.region}
                    </span>
                  </td>
                  <td className="table-cell"><StatusBadge status={rule.status} /></td>
                  <td className="table-cell">
                    <div className="flex gap-1.5">
                      <button className="icon-btn"><Edit3 size={14} className="text-gray-500" /></button>
                      <button className="icon-btn"><Trash2 size={14} className="text-red-500" /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ─── Compliance Cards ────────────────── */}
      <div className="grid grid-cols-3 gap-5">
        {COMPLIANCE_CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <div key={c.title} className="card p-6">
              <div className="flex items-center gap-3 mb-4">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: c.color + '18' }}
                >
                  <Icon size={20} color={c.color} />
                </div>
                <div>
                  <h4 className="text-[15px] font-bold text-gray-900">{c.title}</h4>
                  <p className="text-xs text-gray-500">{c.desc}</p>
                </div>
              </div>
              {c.items.map((item) => (
                <div key={item} className="flex items-center gap-2 py-2 text-sm text-gray-700">
                  <CheckCircle size={16} className="text-green-500 flex-shrink-0" /> {item}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
