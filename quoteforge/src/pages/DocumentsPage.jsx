import { FileText, CheckCircle, Clock, XCircle, Search, Filter, Download, Eye, Send } from 'lucide-react';
import { StatusBadge } from '@components/common';
import { documentLogs } from '@data/mockData';

const stats = [
  { label: 'Total Generated', value: '2,401', icon: FileText, color: '#6366f1' },
  { label: 'Delivered', value: '2,198', icon: CheckCircle, color: '#22c55e' },
  { label: 'Pending', value: '156', icon: Clock, color: '#f59e0b' },
  { label: 'Failed', value: '47', icon: XCircle, color: '#ef4444' },
];

export default function DocumentsPage() {
  return (
    <div className="page-enter">
      {/* ─── Quick Stats ─── */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="card flex items-center gap-4 !p-5">
            <div className="w-[42px] h-[42px] rounded-xl flex items-center justify-center" style={{ background: `${s.color}15` }}>
              <s.icon size={20} style={{ color: s.color }} />
            </div>
            <div>
              <div className="text-xl font-bold text-gray-900">{s.value}</div>
              <div className="text-xs text-gray-500">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ─── Search & Filters ─── */}
      <div className="flex gap-3 mb-5">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input placeholder="Search documents by ID, client, or user..." className="input pl-10 h-10" />
        </div>
        <button className="btn-secondary"><Filter size={15} /> Filters</button>
        <button className="btn-secondary"><Download size={15} /> Export</button>
      </div>

      {/* ─── Documents Table ─── */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr>{['Doc ID', 'Client', 'Type', 'Format', 'Status', 'Generated', 'Delivered', 'User', 'Actions'].map((h) => (
              <th key={h} className="table-header">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {documentLogs.map((doc) => (
              <tr key={doc.id} className="table-row">
                <td className="table-cell font-semibold text-brand-500 font-mono text-xs">{doc.id}</td>
                <td className="table-cell font-semibold text-gray-900">{doc.client}</td>
                <td className="table-cell">
                  <span className={`badge ${doc.type === 'Quote' ? 'bg-brand-50 text-brand-700' : 'bg-purple-50 text-purple-700'}`}>
                    {doc.type}
                  </span>
                </td>
                <td className="table-cell text-gray-500">{doc.format}</td>
                <td className="table-cell"><StatusBadge status={doc.status} /></td>
                <td className="table-cell text-gray-500">{doc.generatedAt}</td>
                <td className="table-cell text-gray-500">{doc.deliveredAt}</td>
                <td className="table-cell text-gray-500">{doc.user}</td>
                <td className="table-cell">
                  <div className="flex gap-1.5">
                    <button className="btn-ghost w-[30px] h-[30px]"><Eye size={13} className="text-gray-500" /></button>
                    <button className="btn-ghost w-[30px] h-[30px]"><Download size={13} className="text-gray-500" /></button>
                    <button className="btn-ghost w-[30px] h-[30px]"><Send size={13} className="text-gray-500" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="flex justify-between items-center px-5 py-4 border-t border-gray-100">
          <span className="text-sm text-gray-500">Showing 1–5 of 2,401 documents</span>
          <div className="flex gap-1.5">
            {[1, 2, 3, '...', 480].map((p, i) => (
              <button
                key={i}
                className={`w-[34px] h-[34px] rounded-lg border text-sm font-medium flex items-center justify-center ${
                  p === 1 ? 'border-brand-500 bg-brand-500 text-white' : 'border-gray-200 bg-white text-gray-500'
                } ${typeof p === 'number' ? 'cursor-pointer hover:bg-gray-50' : ''}`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
