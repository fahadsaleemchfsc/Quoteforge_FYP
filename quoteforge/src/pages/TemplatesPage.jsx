import { useState } from 'react';
import { Plus, FileText, Eye, Edit3, Copy } from 'lucide-react';
import { StatusBadge } from '@components/common';
import { templates } from '@data/mockData';
import { cn } from '@utils/helpers';

export default function TemplatesPage() {
  const [filter, setFilter] = useState('all');
  const filtered = filter === 'all' ? templates : templates.filter((t) => t.status === filter);

  return (
    <div className="page-enter">
      {/* ─── Header ─── */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex gap-2">
          {['all', 'active', 'draft', 'archived'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                'px-4 py-2 rounded-lg border text-sm font-medium capitalize transition-all',
                filter === f
                  ? 'border-brand-500 bg-brand-50 text-brand-700'
                  : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
              )}
            >
              {f === 'all' ? `All (${templates.length})` : f}
            </button>
          ))}
        </div>
        <button className="btn-primary">
          <Plus size={18} /> New Template
        </button>
      </div>

      {/* ─── Template Cards Grid ─── */}
      <div className="grid grid-cols-3 gap-5">
        {filtered.map((t) => (
          <div key={t.id} className="card card-hover cursor-pointer group">
            <div className="flex justify-between items-start mb-4">
              <div className={cn(
                'w-12 h-12 rounded-xl flex items-center justify-center',
                t.type === 'Proposal' ? 'bg-purple-50' : 'bg-brand-50'
              )}>
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
                <button className="btn-ghost"><Eye size={14} className="text-gray-500" /></button>
                <button className="btn-ghost"><Edit3 size={14} className="text-gray-500" /></button>
                <button className="btn-ghost"><Copy size={14} className="text-gray-500" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
