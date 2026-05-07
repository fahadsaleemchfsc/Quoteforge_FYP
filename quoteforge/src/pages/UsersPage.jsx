import { Plus, Edit3, Lock, Trash2, CheckCircle, XCircle } from 'lucide-react';
import { StatusBadge } from '@components/common';
import { users, rolePermissions } from '@data/mockData';
import { getInitials, stringToColor } from '@utils/helpers';

const ROLE_STYLES = {
  'Admin':         { bg: 'bg-red-100',   text: 'text-red-800' },
  'Sales Manager': { bg: 'bg-amber-100', text: 'text-amber-800' },
  'Sales Rep':     { bg: 'bg-brand-50',  text: 'text-brand-700' },
};

export default function UsersPage() {
  return (
    <div className="page-enter">
      {/* ─── Header ─── */}
      <div className="flex justify-between items-center mb-6">
        <div className="badge bg-brand-50 text-brand-700 font-semibold px-3.5 py-1.5">
          {users.filter((u) => u.status === 'active').length} Active Users
        </div>
        <button className="btn-primary"><Plus size={18} /> Invite User</button>
      </div>

      {/* ─── Users Table ─── */}
      <div className="card p-0 overflow-hidden mb-6">
        <table className="w-full">
          <thead>
            <tr>{['User', 'Role', 'Status', 'Last Login', 'Actions'].map((h) => (
              <th key={h} className="table-header">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const colors = stringToColor(user.name);
              const rs = ROLE_STYLES[user.role] || ROLE_STYLES['Sales Rep'];
              return (
                <tr key={user.id} className="table-row">
                  <td className="table-cell">
                    <div className="flex items-center gap-3.5">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold"
                        style={{ background: colors.bg, color: colors.text }}
                      >
                        {getInitials(user.name)}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-gray-900">{user.name}</div>
                        <div className="text-xs text-gray-400">{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="table-cell">
                    <span className={`badge ${rs.bg} ${rs.text} font-semibold`}>{user.role}</span>
                  </td>
                  <td className="table-cell"><StatusBadge status={user.status} /></td>
                  <td className="table-cell text-gray-500">{user.lastLogin}</td>
                  <td className="table-cell">
                    <div className="flex gap-1.5">
                      <button className="btn-ghost"><Edit3 size={14} className="text-gray-500" /></button>
                      <button className="btn-ghost"><Lock size={14} className="text-gray-500" /></button>
                      <button className="btn-ghost"><Trash2 size={14} className="text-red-500" /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ─── Permissions Matrix ─── */}
      <div className="card">
        <h3 className="section-title mb-5">Role Permissions Matrix</h3>
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500">Permission</th>
              {['Admin', 'Sales Manager', 'Sales Rep'].map((r) => (
                <th key={r} className="text-center px-5 py-3 text-xs font-semibold text-gray-500">{r}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rolePermissions.map((row) => (
              <tr key={row.perm} className="border-t border-gray-100">
                <td className="px-5 py-3 text-sm font-medium text-gray-700">{row.perm}</td>
                {[row.admin, row.manager, row.rep].map((v, i) => (
                  <td key={i} className="text-center px-5 py-3">
                    {v ? <CheckCircle size={18} className="text-emerald-500 mx-auto" /> : <XCircle size={18} className="text-gray-200 mx-auto" />}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
