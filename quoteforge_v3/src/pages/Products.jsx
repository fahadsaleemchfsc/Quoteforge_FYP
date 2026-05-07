import { useEffect, useState } from 'react';
import { Plus, Trash2, X, CloudDownload } from 'lucide-react';
import { Panel, Pill, Mono, SegmentedControl, Toggle } from '@/components/ui';
import api from '@/services/api';
import toast from 'react-hot-toast';

const EMPTY_FORM = {
  sku: '', name: '', description: '', category: '',
  base_price: '', min_price_floor: '',
  currency: 'USD', unit: 'license', agent_exposed: false,
};

function formatMoney(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function Products() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [exposureFilter, setExposureFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [importing, setImporting] = useState(false);
  const [sfConnected, setSfConnected] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    setLoading(true); setError('');
    try {
      const params = {};
      if (search) params.search = search;
      if (exposureFilter !== 'all') params.agent_exposed = exposureFilter === 'exposed';
      const res = await api.get('/products', { params });
      setProducts(res.data);
    } catch (e) { setError(e.response?.data?.detail || 'failed to load'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, exposureFilter]);

  useEffect(() => {
    // Is Salesforce connected? If yes, show the import button.
    api.get('/crm/connections')
      .then((res) => {
        const sf = (res.data || []).find((c) => c.platform === 'Salesforce' && c.status === 'connected');
        setSfConnected(!!sf);
      })
      .catch(() => setSfConnected(false));
  }, []);

  async function importFromSalesforce() {
    setImporting(true);
    const tid = toast.loading('Importing Pricebook from Salesforce…');
    try {
      const res = await api.post('/crm/salesforce/import-products');
      toast.success(
        `Imported ${res.data.imported}, updated ${res.data.updated}, skipped ${res.data.skipped}`,
        { id: tid },
      );
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Import failed', { id: tid });
    } finally {
      setImporting(false);
    }
  }

  async function toggleExposure(p) {
    const next = !p.agent_exposed;
    setProducts((prev) => prev.map((x) => (x.id === p.id ? { ...x, agent_exposed: next } : x)));
    try {
      await api.patch(`/products/${p.id}/agent-exposure`, { agent_exposed: next });
    } catch (e) {
      setProducts((prev) => prev.map((x) => (x.id === p.id ? { ...x, agent_exposed: !next } : x)));
      alert(e.response?.data?.detail || 'toggle failed');
    }
  }

  async function deleteProduct(p) {
    if (!confirm(`Delete ${p.sku}?`)) return;
    try {
      await api.delete(`/products/${p.id}`);
      setProducts((prev) => prev.filter((x) => x.id !== p.id));
    } catch (e) { alert(e.response?.data?.detail || 'delete failed'); }
  }

  async function submitForm(e) {
    e.preventDefault(); setFormError('');
    if (Number(form.min_price_floor) > Number(form.base_price)) {
      setFormError('min_price_floor must be ≤ base_price'); return;
    }
    setSubmitting(true);
    try {
      await api.post('/products', {
        ...form,
        base_price: Number(form.base_price),
        min_price_floor: Number(form.min_price_floor),
        description: form.description || null,
        category: form.category || null,
      });
      setShowForm(false); setForm(EMPTY_FORM); await refresh();
    } catch (e) { setFormError(e.response?.data?.detail || 'create failed'); }
    finally { setSubmitting(false); }
  }

  const exposedCount = products.filter((p) => p.agent_exposed).length;
  const tabs = [
    { value: 'all',      label: 'All',            count: products.length },
    { value: 'exposed',  label: 'Agent-exposed',  count: exposedCount },
    { value: 'internal', label: 'Internal-only',  count: products.length - exposedCount },
  ];

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="flex items-center gap-3">
          <SegmentedControl options={tabs} active={exposureFilter} onChange={setExposureFilter} />
          <input
            type="text"
            placeholder="Search SKU or name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field font-mono"
            style={{ width: 240 }}
          />
        </div>
        <div className="flex items-center gap-2">
          {sfConnected && (
            <button
              className="btn-secondary"
              onClick={importFromSalesforce}
              disabled={importing}
              title="UPSERT Salesforce Pricebook entries into this catalog"
            >
              <CloudDownload size={13} />
              {importing ? 'importing…' : 'Import from Salesforce'}
            </button>
          )}
          <button className="btn-primary" onClick={() => setShowForm(true)}>
            <Plus size={13} /> Add product
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2.5 rounded text-[12.5px]"
          style={{ background: 'var(--danger-muted)', color: 'var(--danger)' }}>{error}</div>
      )}

      <Panel padded={false}>
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-header">SKU</th>
              <th className="table-header">Name</th>
              <th className="table-header">Category</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Base</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Floor</th>
              <th className="table-header">Unit</th>
              <th className="table-header">Agent</th>
              <th className="table-header" style={{ width: 48 }}></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="table-cell text-center text-text-muted py-10">loading…</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={8} className="table-cell text-center text-text-muted py-10">
                no products — click "Add product" to create one
              </td></tr>
            ) : products.map((p) => (
              <tr key={p.id} className="table-row">
                <td className="table-cell"><Mono className="font-medium">{p.sku}</Mono></td>
                <td className="table-cell font-medium text-text-primary">{p.name}</td>
                <td className="table-cell text-text-secondary">{p.category || '—'}</td>
                <td className="table-cell table-num">{formatMoney(p.base_price)}</td>
                <td className="table-cell table-num text-text-secondary">{formatMoney(p.min_price_floor)}</td>
                <td className="table-cell text-text-secondary font-mono text-[11.5px]">{p.unit}</td>
                <td className="table-cell">
                  <div className="flex items-center gap-2">
                    <Toggle
                      checked={p.agent_exposed}
                      onChange={() => toggleExposure(p)}
                      ariaLabel="Toggle agent exposure"
                    />
                    <span className="text-[10.5px] font-mono uppercase tracking-wider"
                      style={{ color: p.agent_exposed ? 'var(--accent)' : 'var(--text-muted)' }}>
                      {p.agent_exposed ? 'ON' : 'OFF'}
                    </span>
                  </div>
                </td>
                <td className="table-cell">
                  <button className="icon-btn" onClick={() => deleteProduct(p)} title="Delete">
                    <Trash2 size={12} style={{ color: 'var(--danger)' }} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {/* Add product modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) { setShowForm(false); setForm(EMPTY_FORM); setFormError(''); } }}
          style={{ background: 'rgba(0,0,0,0.4)' }}
        >
          <form
            onSubmit={submitForm}
            className="bg-surface border border-border rounded w-full max-w-[540px]"
            style={{ boxShadow: 'var(--shadow-pop)' }}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <div className="text-[13px] font-semibold text-text-primary">Add product</div>
              <button
                type="button"
                className="icon-btn"
                onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setFormError(''); }}
              ><X size={13} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-3">
              <FormField label="SKU" required>
                <input required className="input-field font-mono"
                  value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
              </FormField>
              <FormField label="Name" required>
                <input required className="input-field"
                  value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </FormField>
              <FormField label="Description" span={2}>
                <textarea rows={2} className="input-field"
                  value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </FormField>
              <FormField label="Category">
                <input className="input-field"
                  value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
              </FormField>
              <FormField label="Unit">
                <input className="input-field font-mono"
                  value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
              </FormField>
              <FormField label="Base price" required>
                <input required type="number" step="0.01" min="0" className="input-field font-mono"
                  value={form.base_price} onChange={(e) => setForm({ ...form, base_price: e.target.value })} />
              </FormField>
              <FormField label="Min price floor" required>
                <input required type="number" step="0.01" min="0" className="input-field font-mono"
                  value={form.min_price_floor} onChange={(e) => setForm({ ...form, min_price_floor: e.target.value })} />
              </FormField>
              <FormField label="Currency">
                <input maxLength={3} className="input-field font-mono uppercase"
                  value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
              </FormField>
              <div className="flex items-center gap-2 mt-6">
                <Toggle
                  checked={form.agent_exposed}
                  onChange={(v) => setForm({ ...form, agent_exposed: v })}
                  ariaLabel="Expose to buyer agents"
                />
                <span className="text-[12.5px] text-text-primary">Expose to buyer agents</span>
              </div>
            </div>
            {formError && (
              <div className="px-5 pb-2 text-[12.5px]" style={{ color: 'var(--danger)' }}>{formError}</div>
            )}
            <div className="px-5 py-3 border-t border-border flex justify-end gap-2">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setFormError(''); }}
              >Cancel</button>
              <button type="submit" className="btn-primary" disabled={submitting}>
                {submitting ? 'creating…' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function FormField({ label, required, span = 1, children }) {
  return (
    <div className={span === 2 ? 'col-span-2' : ''}>
      <div className="section-label mb-1.5">
        {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
      </div>
      {children}
    </div>
  );
}
