import { useState, useEffect } from 'react';
import { FileText, CheckCircle, Clock, XCircle, Search, Filter, Download, Eye, Send } from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import { DOCUMENT_LOGS } from '@/constants/mockData';
import api from '@/services/api';

export default function Documents() {
  const [documents, setDocuments] = useState(DOCUMENT_LOGS);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');

  const stats = [
    { label: 'Total Generated', value: total || documents.length, icon: FileText, color: 'var(--accent)' },
    { label: 'Delivered', value: documents.filter(d => d.status === 'delivered').length, icon: CheckCircle, color: '#22c55e' },
    { label: 'Pending', value: documents.filter(d => d.status === 'pending' || d.status === 'generated').length, icon: Clock, color: '#f59e0b' },
    { label: 'Failed', value: documents.filter(d => d.status === 'failed').length, icon: XCircle, color: '#ef4444' },
  ];

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/quotes/documents', { params: { page, per_page: 10, search } });
        setDocuments(res.data.documents);
        setTotal(res.data.total);
      } catch {}
    };
    load();
  }, [page, search]);

  const handleDownload = async (docId) => {
    try {
      const res = await api.get(`/quotes/documents/${docId}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${docId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  };

  const handleResend = async (docId) => {
    try {
      await api.post(`/quotes/documents/${docId}/resend`);
      // Refresh
      const res = await api.get('/quotes/documents', { params: { page, per_page: 10 } });
      setDocuments(res.data.documents);
    } catch {}
  };

  return (
    <div className="page-enter">
      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="card p-4 flex items-center gap-4">
              <div
                className="w-8 h-8 rounded flex items-center justify-center"
                style={{ background: s.color + '18' }}
              >
                <Icon size={20} color={s.color} />
              </div>
              <div>
                <div className="text-lg font-bold text-text-primary">{s.value}</div>
                <div className="text-xs text-text-secondary">{s.label}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Search & Filters */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            placeholder="Search documents by ID, client, or user..."
            className="input-field pl-10 h-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className="btn-secondary">
          <Filter size={15} /> Filters
        </button>
        <button className="btn-secondary">
          <Download size={15} /> Export
        </button>
      </div>

      {/* Document Table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-subtle">
              {['Doc ID', 'Client', 'Type', 'Format', 'Status', 'Generated', 'Delivered', 'User', 'Actions'].map((h) => (
                <th key={h} className="table-header">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {documents.map((doc, i) => (
              <tr key={doc.id} className="table-row">
                <td className="table-cell font-semibold text-brand-500 font-mono">{doc.id}</td>
                <td className="table-cell font-semibold text-text-primary">{doc.client}</td>
                <td className="table-cell">
                  <span className={`px-2.5 py-0.5 rounded text-xs font-medium ${
                    doc.type === 'Quote' ? 'bg-brand-50 text-brand-700' : 'bg-accent-muted text-accent'
                  }`}>
                    {doc.type}
                  </span>
                </td>
                <td className="table-cell text-text-secondary">{doc.format}</td>
                <td className="table-cell"><StatusBadge status={doc.status} /></td>
                <td className="table-cell text-text-secondary">{doc.generatedAt}</td>
                <td className="table-cell text-text-secondary">{doc.deliveredAt || '—'}</td>
                <td className="table-cell text-text-secondary">{doc.user}</td>
                <td className="table-cell">
                  <div className="flex gap-1.5">
                    <button className="icon-btn w-[30px] h-[30px]"><Eye size={13} className="text-text-secondary" /></button>
                    <button className="icon-btn w-[30px] h-[30px]" onClick={() => handleDownload(doc.id)}><Download size={13} className="text-text-secondary" /></button>
                    <button className="icon-btn w-[30px] h-[30px]" onClick={() => handleResend(doc.id)}><Send size={13} className="text-text-secondary" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="flex justify-between items-center px-5 py-4 border-t border-border">
          <span className="text-sm text-text-secondary">Showing {(page-1)*10+1}-{Math.min(page*10, total)} of {total} documents</span>
          <div className="flex gap-1.5">
            {page > 1 && (
              <button onClick={() => setPage(p => p-1)} className="w-[34px] h-[34px] rounded border border-border bg-white text-text-secondary text-sm font-medium flex items-center justify-center cursor-pointer hover:bg-subtle">&lt;</button>
            )}
            <button className="w-[34px] h-[34px] rounded border border-brand-500 bg-brand-500 text-white text-sm font-medium flex items-center justify-center">{page}</button>
            {page * 10 < total && (
              <button onClick={() => setPage(p => p+1)} className="w-[34px] h-[34px] rounded border border-border bg-white text-text-secondary text-sm font-medium flex items-center justify-center cursor-pointer hover:bg-subtle">&gt;</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
