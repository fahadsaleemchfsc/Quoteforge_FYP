import { Plus, Database, RefreshCw, Settings, Link2, ChevronRight, Tag, Users, DollarSign, Package, Mail, Clock, Layers, Globe } from 'lucide-react';
import { StatusBadge } from '@components/common';
import { crmConnections, crmFieldMappings } from '@data/mockData';

const ICON_MAP = { Tag, Users, DollarSign, Package, Mail, Clock, Layers, Globe };

export default function CRMPage() {
  return (
    <div className="page-enter">
      {/* ─── Header ─── */}
      <div className="flex justify-between items-center mb-6">
        <p className="text-sm text-gray-500">Connect and manage your CRM platform integrations via OAuth 2.0</p>
        <button className="btn-primary"><Plus size={18} /> Add Connection</button>
      </div>

      {/* ─── Connection Cards ─── */}
      <div className="grid grid-cols-3 gap-5 mb-8">
        {crmConnections.map((crm) => (
          <div key={crm.id} className={`card ${crm.status === 'disconnected' ? 'border-red-200' : ''}`}>
            <div className="flex justify-between items-start mb-5">
              <div className="flex items-center gap-3.5">
                <div className={`w-[52px] h-[52px] rounded-2xl flex items-center justify-center ${crm.platform === 'Salesforce' ? 'bg-blue-50' : 'bg-orange-50'}`}>
                  <Database size={26} className={crm.platform === 'Salesforce' ? 'text-blue-600' : 'text-orange-500'} />
                </div>
                <div>
                  <h4 className="text-base font-bold text-gray-900">{crm.name}</h4>
                  <span className="text-sm text-gray-500">{crm.platform}</span>
                </div>
              </div>
              <StatusBadge status={crm.status} />
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="p-3.5 rounded-xl bg-gray-50">
                <div className="text-xl font-bold text-gray-900">{crm.deals.toLocaleString()}</div>
                <div className="text-xs text-gray-500">Active Deals</div>
              </div>
              <div className="p-3.5 rounded-xl bg-gray-50">
                <div className={`text-xl font-bold ${crm.health > 0 ? 'text-emerald-600' : 'text-red-600'}`}>{crm.health}%</div>
                <div className="text-xs text-gray-500">API Health</div>
              </div>
            </div>

            <div className="text-sm text-gray-400 mb-4">Last sync: {crm.lastSync}</div>

            <div className="flex gap-2.5">
              {crm.status === 'connected' ? (
                <>
                  <button className="btn-secondary flex-1 justify-center text-sm"><RefreshCw size={14} /> Sync Now</button>
                  <button className="btn-ghost"><Settings size={14} className="text-gray-500" /></button>
                </>
              ) : (
                <button className="btn-primary flex-1 justify-center text-sm"><Link2 size={14} /> Reconnect</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ─── Field Mapping ─── */}
      <div className="card">
        <h3 className="section-title mb-1">CRM Field Mapping</h3>
        <p className="section-subtitle mb-5">Map CRM data fields to the quote generation schema</p>
        <div className="grid grid-cols-4 gap-4">
          {crmFieldMappings.map((field) => {
            const Icon = ICON_MAP[field.icon];
            return (
              <div key={field.crm} className="p-4 rounded-xl border border-gray-100 bg-gray-50/50">
                <div className="flex items-center gap-2 mb-2.5">
                  <Icon size={16} className="text-brand-500" />
                  <span className="text-sm font-semibold text-gray-900">{field.crm}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <ChevronRight size={14} className="text-gray-400" />
                  <code className="text-xs text-brand-600 bg-brand-50 px-2 py-0.5 rounded">{field.maps}</code>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
