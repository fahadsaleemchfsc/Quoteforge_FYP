import { useState } from 'react';
import { Plus, FileText, Eye, Edit3, Copy } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { TEMPLATES } from '@/constants/mockData';
import clsx from 'clsx';

export default function Templates() {
  const [filter, setFilter] = useState('all');
  const filtered = filter === 'all' ? TEMPLATES : TEMPLATES.filter((t) => t.status === filter);
  const filters = ['all', 'active', 'draft', 'archived'];

  return (
    <div className="page-enter">
      {/* ─── Header ──────────────────────────── */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex gap-2">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={clsx('filter-btn capitalize', f === filter ? 'filter-btn-active' : 'filter-btn-inactive')}
            >
              {f === 'all' ? `All (${TEMPLATES.length})` : f}
            </button>
          ))}
        </div>
        <button className="btn-primary">
          <Plus size={18} /> New Template
        </button>
      </div>

      {/* ─── Template Grid ───────────────────── */}
      <div className="grid grid-cols-3 gap-5">
        {filtered.map((t, i) => (
          <div
            key={t.id}
            className="card card-hover p-6 cursor-pointer animate-slide-up"
            style={{ animationDelay: `${i * 0.05}s` }}
          >
            <div className="flex justify-between items-start mb-4">
              <div
                className={clsx(
                  'w-12 h-12 rounded-xl flex items-center justify-center',
                  t.type === 'Proposal' ? 'bg-purple-50' : 'bg-brand-50'
                )}
              >
                <FileText size={24} className={t.type === 'Proposal' ? 'text-purple-600' : 'text-brand-500'} />
              </div>
              <StatusBadge status={t.status} />
            </div>

            <h4 className="text-[15px] font-bold text-gray-900 mb-1.5">{t.name}</h4>
            <div className="flex gap-3 mb-4 text-xs text-gray-500">
              <span>{t.type}</span>
              <span className="text-gray-300">•</span>
              <span>{t.format}</span>
              <span className="text-gray-300">•</span>
              <span>Used {t.usageCount}x</span>
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-gray-100">
              <span className="text-xs text-gray-400">Modified {t.lastModified}</span>
              <div className="flex gap-1.5">
                <button className="icon-btn"><Eye size={14} className="text-gray-500" /></button>
                <button className="icon-btn"><Edit3 size={14} className="text-gray-500" /></button>
                <button className="icon-btn"><Copy size={14} className="text-gray-500" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
