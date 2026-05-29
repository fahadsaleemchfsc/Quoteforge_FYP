import { useState, useEffect } from 'react';
import { Plus, Edit3, Trash2, Globe } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { PRICING_RULES } from '@/constants/mockData';
import api from '@/services/api';
import clsx from 'clsx';

const TYPE_STYLES = {
  Discount:   { bg: 'bg-success-muted', text: 'text-success' },
  Tax:        { bg: 'bg-warning-muted', text: 'text-warning' },
};
const DEFAULT_TYPE_STYLE = { bg: 'bg-subtle', text: 'text-text-secondary' };

export default function Pricing() {
  const [tab, setTab] = useState('all');
  const [rules, setRules] = useState(PRICING_RULES);
  const types = ['all', 'Discount', 'Tax'];

  useEffect(() => {
    api.get('/pricing/rules').then(res => setRules(res.data)).catch(() => {});
  }, []);

  const filtered = tab === 'all' ? rules : rules.filter((r) => r.type === tab);

  return (
    <div className="page-enter">
      {/* ─── Filters & Actions ───────────────── */}
      <div className="flex justify-between items-center mb-4">
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
      <div className="card overflow-hidden mb-4">
        <table className="w-full">
          <thead>
            <tr className="bg-subtle">
              {['Rule Name', 'Type', 'Condition', 'Value', 'Region', 'Status', 'Actions'].map((h) => (
                <th key={h} className="table-header">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((rule, i) => {
              const ts = TYPE_STYLES[rule.type] || DEFAULT_TYPE_STYLE;
              return (
                <tr key={rule.id} className="table-row " >
                  <td className="table-cell font-semibold text-text-primary">{rule.name}</td>
                  <td className="table-cell">
                    <span className={clsx('px-2.5 py-0.5 rounded text-xs font-medium', ts.bg, ts.text)}>
                      {rule.type}
                    </span>
                  </td>
                  <td className="table-cell text-text-secondary font-mono text-sm">{rule.condition}</td>
                  <td className="table-cell font-semibold text-text-primary">{rule.value}</td>
                  <td className="table-cell">
                    <span className="inline-flex items-center gap-1.5 text-sm text-text-secondary">
                      <Globe size={14} /> {rule.region}
                    </span>
                  </td>
                  <td className="table-cell"><StatusBadge status={rule.status} /></td>
                  <td className="table-cell">
                    <div className="flex gap-1.5">
                      <button className="icon-btn"><Edit3 size={14} className="text-text-secondary" /></button>
                      <button className="icon-btn"><Trash2 size={14} className="text-danger" /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

    </div>
  );
}
