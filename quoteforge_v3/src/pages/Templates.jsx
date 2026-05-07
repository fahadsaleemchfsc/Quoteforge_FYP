import { useState, useEffect } from 'react';
import { Plus, FileText, Eye, Edit3, Copy } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { TEMPLATES } from '@/constants/mockData';
import api from '@/services/api';
import clsx from 'clsx';

export default function Templates() {
  const [filter, setFilter] = useState('all');
  const [templates, setTemplates] = useState(TEMPLATES);
  const filters = ['all', 'active', 'draft', 'archived'];

  useEffect(() => {
    api.get('/templates').then(res => setTemplates(res.data)).catch(() => {});
  }, []);

  const filtered = filter === 'all' ? templates : templates.filter((t) => t.status === filter);

  return (
    <div className="page-enter">
      {/* ─── Header ──────────────────────────── */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-2">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={clsx('filter-btn capitalize', f === filter ? 'filter-btn-active' : 'filter-btn-inactive')}
            >
              {f === 'all' ? `All (${templates.length})` : f}
            </button>
          ))}
        </div>
        <button className="btn-primary">
          <Plus size={18} /> New Template
        </button>
      </div>

      {/* ─── Template Grid ───────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        {filtered.map((t, i) => (
          <div
            key={t.id}
            className="card card-hover p-4 cursor-pointer "
            
          >
            <div className="flex justify-between items-start mb-4">
              <div
                className={clsx(
                  'w-9 h-9 rounded flex items-center justify-center',
                  t.type === 'Proposal' ? 'bg-accent-muted' : 'bg-brand-50'
                )}
              >
                <FileText size={24} className={t.type === 'Proposal' ? 'text-accent' : 'text-brand-500'} />
              </div>
              <StatusBadge status={t.status} />
            </div>

            <h4 className="text-[13px] font-bold text-text-primary mb-1.5">{t.name}</h4>
            <div className="flex gap-3 mb-4 text-xs text-text-secondary">
              <span>{t.type}</span>
              <span className="text-text-muted">•</span>
              <span>{t.format}</span>
              <span className="text-text-muted">•</span>
              <span>Used {t.usageCount}x</span>
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-border">
              <span className="text-xs text-text-muted">Modified {t.lastModified}</span>
              <div className="flex gap-1.5">
                <button className="icon-btn"><Eye size={14} className="text-text-secondary" /></button>
                <button className="icon-btn"><Edit3 size={14} className="text-text-secondary" /></button>
                <button className="icon-btn"><Copy size={14} className="text-text-secondary" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
