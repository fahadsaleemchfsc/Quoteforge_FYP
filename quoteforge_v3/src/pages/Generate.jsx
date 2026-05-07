import { useState, useEffect } from 'react';
import {
  Zap, RefreshCw, Cloud, Building2, DollarSign, Calendar, Tag,
  FileText, Download, Send, CheckCircle, AlertCircle, Loader2,
  ChevronRight, Globe, Shield, ArrowRight, ExternalLink,
} from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import api from '@/services/api';
import clsx from 'clsx';

const STEPS = [
  { num: 1, label: 'Select Deal' },
  { num: 2, label: 'Review & Configure' },
  { num: 3, label: 'Generate' },
  { num: 4, label: 'Deliver' },
];

export default function Generate() {
  const [step, setStep] = useState(1);
  const [crmConnected, setCrmConnected] = useState(false);
  const [deals, setDeals] = useState([]);
  const [loadingDeals, setLoadingDeals] = useState(false);
  const [selectedDeal, setSelectedDeal] = useState(null);
  const [outputFormat, setOutputFormat] = useState('PDF');
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  // Check CRM connection and load deals
  useEffect(() => {
    loadDeals();
  }, []);

  const loadDeals = async () => {
    setLoadingDeals(true);
    setError('');
    try {
      // Check for live Salesforce connection
      const sfRes = await api.get('/crm/salesforce/opportunities?limit=20');
      if (sfRes.data.opportunities?.length > 0) {
        setDeals(sfRes.data.opportunities);
        setCrmConnected(true);
      }
    } catch {
      // Try demo deals fallback
      try {
        const connRes = await api.get('/crm/connections');
        const sfConn = connRes.data.find(c => c.platform === 'Salesforce' && c.status === 'connected');
        if (sfConn) {
          const dealsRes = await api.get(`/crm/connections/${sfConn.id}/deals`);
          setDeals(dealsRes.data.deals || []);
          setCrmConnected(true);
        }
      } catch {
        setCrmConnected(false);
      }
    }
    setLoadingDeals(false);
  };

  const handleConnectSalesforce = async () => {
    try {
      const res = await api.get('/crm/salesforce/authorize?environment=production');
      window.location.href = res.data.authorization_url;
    } catch {
      setError('Failed to start Salesforce OAuth. Check backend configuration.');
    }
  };

  const handleGenerate = async () => {
    if (!selectedDeal) return;
    setGenerating(true);
    setError('');
    setResult(null);
    setStep(3);

    setGenProgress('Fetching deal data from Salesforce...');

    try {
      // If we have a Salesforce deal ID, use the direct SF endpoint
      if (selectedDeal.source === 'salesforce') {
        setGenProgress('Applying pricing rules...');
        setTimeout(() => setGenProgress('AI generating proposal sections...'), 2000);
        setTimeout(() => setGenProgress('Rendering document...'), 5000);

        const res = await api.post(
          `/crm/salesforce/generate-from-deal/${selectedDeal.deal_id}?output_format=${outputFormat}`
        );
        setResult(res.data);
        setStep(4);
      } else {
        // Use the general generate endpoint
        setGenProgress('Applying pricing rules...');

        const payload = {
          deal_id: selectedDeal.deal_id || '',
          client_name: selectedDeal.client_name,
          deal_name: selectedDeal.deal_name,
          deal_amount: selectedDeal.deal_amount || selectedDeal.amount || 0,
          contact_email: selectedDeal.contact_email || '',
          region: selectedDeal.region || 'US',
          output_format: outputFormat,
          line_items: (selectedDeal.line_items || []).map(item => ({
            product: item.product,
            quantity: item.quantity || 1,
            unit_price: item.unit_price || 0,
          })),
        };

        setTimeout(() => setGenProgress('AI generating proposal sections...'), 1500);
        setTimeout(() => setGenProgress('Rendering document...'), 4000);

        const res = await api.post('/quotes/generate', payload);
        setResult(res.data);
        setStep(4);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Generation failed. Check backend connection.');
      setStep(2);
    }
    setGenerating(false);
  };

  const handleDownload = async () => {
    if (!result?.doc_id) return;
    try {
      const res = await api.get(`/quotes/documents/${result.doc_id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${result.doc_id}.${outputFormat.toLowerCase()}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  };

  const handleSendToClient = async () => {
    if (!result?.doc_id) return;
    try {
      await api.post(`/quotes/documents/${result.doc_id}/resend`);
      setResult(prev => ({ ...prev, delivered: true }));
    } catch {}
  };

  return (
    <div className="page-enter">
      {/* ─── Progress Steps ─────────────────────── */}
      <div className="card p-4 mb-5">
        <div className="flex items-center justify-between">
          {STEPS.map((s, i) => (
            <div key={s.num} className="flex items-center flex-1">
              <div className="flex items-center gap-2.5">
                <div className={clsx(
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all',
                  step > s.num ? 'bg-success text-white' :
                  step === s.num ? 'bg-brand-500 text-white' :
                  'bg-muted text-text-secondary'
                )}>
                  {step > s.num ? <CheckCircle size={16} /> : s.num}
                </div>
                <span className={clsx(
                  'text-sm font-medium',
                  step >= s.num ? 'text-text-primary' : 'text-text-muted'
                )}>{s.label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={clsx(
                  'flex-1 h-px mx-4',
                  step > s.num ? 'bg-green-300' : 'bg-muted'
                )} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ─── Step 1: Select Deal ────────────────── */}
      {step === 1 && (
        <>
          {!crmConnected && !loadingDeals ? (
            <div className="card p-8 text-center">
              <div className="w-14 h-14 rounded bg-accent-muted flex items-center justify-center mx-auto mb-4">
                <Cloud size={28} className="text-brand-500" />
              </div>
              <h3 className="text-lg font-bold text-text-primary mb-2">Connect Your CRM</h3>
              <p className="text-sm text-text-secondary mb-5 max-w-md mx-auto">
                Connect your Salesforce or HubSpot account to pull live deals and generate proposals automatically.
              </p>
              <button onClick={handleConnectSalesforce} className="btn-primary mx-auto">
                <ExternalLink size={16} /> Connect Salesforce
              </button>
            </div>
          ) : (
            <>
              <div className="flex justify-between items-center mb-4">
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-success-muted text-xs font-semibold text-success">
                    <CheckCircle size={12} /> Salesforce Connected
                  </span>
                  <span className="text-sm text-text-secondary">{deals.length} open deals</span>
                </div>
                <button onClick={loadDeals} className="btn-secondary text-sm" disabled={loadingDeals}>
                  <RefreshCw size={14} className={loadingDeals ? 'animate-spin' : ''} />
                  {loadingDeals ? 'Loading...' : 'Refresh Deals'}
                </button>
              </div>

              {loadingDeals ? (
                <div className="card p-12 flex items-center justify-center gap-3">
                  <Loader2 size={20} className="animate-spin text-brand-500" />
                  <span className="text-sm text-text-secondary">Fetching deals from Salesforce...</span>
                </div>
              ) : (
                <div className="grid gap-3">
                  {deals.map((deal) => (
                    <div
                      key={deal.deal_id}
                      onClick={() => { setSelectedDeal(deal); setStep(2); }}
                      className={clsx(
                        'card p-4 cursor-pointer transition-all hover:border-brand-300 hover:',
                        selectedDeal?.deal_id === deal.deal_id && 'border-brand-500 ring-2 ring-brand-500/15'
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded bg-brand-50 flex items-center justify-center">
                            <FileText size={20} className="text-brand-500" />
                          </div>
                          <div>
                            <h4 className="text-[13px] font-bold text-text-primary">{deal.deal_name}</h4>
                            <div className="flex items-center gap-3 mt-1 text-xs text-text-secondary">
                              <span className="flex items-center gap-1"><Building2 size={12} /> {deal.client_name}</span>
                              <span className="flex items-center gap-1"><DollarSign size={12} /> ${(deal.deal_amount || deal.amount || 0).toLocaleString()}</span>
                              <span className="flex items-center gap-1"><Tag size={12} /> {deal.stage}</span>
                              {deal.close_date && <span className="flex items-center gap-1"><Calendar size={12} /> {deal.close_date}</span>}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={clsx(
                            'px-2.5 py-1 rounded text-xs font-semibold',
                            deal.region === 'PK' ? 'bg-success-muted text-success' :
                            deal.region === 'EU' ? 'bg-accent-muted text-accent' :
                            'bg-subtle text-text-primary'
                          )}>
                            <Globe size={10} className="inline mr-1" />{deal.region || 'US'}
                          </span>
                          <ChevronRight size={16} className="text-text-muted" />
                        </div>
                      </div>
                      {deal.line_items?.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-border flex gap-2 flex-wrap">
                          {deal.line_items.map((item, i) => (
                            <span key={i} className="text-xs bg-subtle text-text-secondary px-2 py-0.5 rounded">
                              {item.product} × {item.quantity}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* ─── Step 2: Review & Configure ─────────── */}
      {step === 2 && selectedDeal && (
        <div className="grid grid-cols-[2fr_1fr] gap-5">
          {/* Deal Summary */}
          <div className="card p-5">
            <h3 className="text-[13px] font-bold text-text-primary mb-4">Deal Summary</h3>

            <div className="grid grid-cols-2 gap-4 mb-5">
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Client</div>
                <div className="text-sm font-semibold text-text-primary">{selectedDeal.client_name}</div>
              </div>
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Deal</div>
                <div className="text-sm font-semibold text-text-primary">{selectedDeal.deal_name}</div>
              </div>
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Amount</div>
                <div className="text-lg font-bold text-text-primary">${(selectedDeal.deal_amount || selectedDeal.amount || 0).toLocaleString()}</div>
              </div>
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Stage</div>
                <div className="text-sm font-semibold text-text-primary">{selectedDeal.stage}</div>
              </div>
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Region</div>
                <div className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
                  <Globe size={14} /> {selectedDeal.region || 'US'}
                </div>
              </div>
              <div className="p-3.5 rounded bg-subtle">
                <div className="text-xs text-text-secondary mb-1">Close Date</div>
                <div className="text-sm font-semibold text-text-primary">{selectedDeal.close_date || 'Not set'}</div>
              </div>
            </div>

            {selectedDeal.line_items?.length > 0 && (
              <>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Line Items</h4>
                <table className="w-full mb-4">
                  <thead>
                    <tr className="bg-subtle">
                      <th className="table-header">Product</th>
                      <th className="table-header text-right">Qty</th>
                      <th className="table-header text-right">Unit Price</th>
                      <th className="table-header text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedDeal.line_items.map((item, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="table-cell font-medium text-text-primary">{item.product}</td>
                        <td className="table-cell text-right text-text-secondary">{item.quantity}</td>
                        <td className="table-cell text-right text-text-secondary">${item.unit_price?.toLocaleString()}</td>
                        <td className="table-cell text-right font-semibold text-text-primary">${((item.quantity || 1) * (item.unit_price || 0)).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}

            {selectedDeal.contact_email && (
              <div className="p-3 rounded bg-accent-muted text-sm text-accent">
                Contact: {selectedDeal.contact_name || ''} ({selectedDeal.contact_email})
              </div>
            )}
          </div>

          {/* Generation Config */}
          <div className="space-y-4">
            <div className="card p-5">
              <h3 className="text-[13px] font-bold text-text-primary mb-4">Output Settings</h3>

              <div className="mb-4">
                <label className="text-sm font-semibold text-text-primary block mb-2">Document Format</label>
                <div className="grid grid-cols-2 gap-2">
                  {['PDF', 'DOCX'].map(fmt => (
                    <button
                      key={fmt}
                      onClick={() => setOutputFormat(fmt)}
                      className={clsx(
                        'p-3 rounded border-2 text-sm font-medium transition-all text-center',
                        outputFormat === fmt
                          ? 'border-brand-500 bg-brand-50 text-brand-700'
                          : 'border-border text-text-secondary hover:border-border-strong'
                      )}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mb-4">
                <label className="text-sm font-semibold text-text-primary block mb-2">Auto-Applied Rules</label>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-text-secondary">
                    <DollarSign size={14} className="text-success" />
                    {(selectedDeal.deal_amount || 0) > 50000 ? '15% Enterprise Discount' : 'Standard Pricing'}
                  </div>
                  <div className="flex items-center gap-2 text-text-secondary">
                    <Globe size={14} className="text-success" />
                    {selectedDeal.region === 'EU' ? '20% EU VAT' : '7.5% US Sales Tax'}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <button onClick={() => { setStep(1); setSelectedDeal(null); }} className="btn-secondary flex-1 justify-center">
                Back
              </button>
              <button onClick={handleGenerate} className="btn-primary flex-1 justify-center">
                <Zap size={16} /> Generate {outputFormat}
              </button>
            </div>

            {error && (
              <div className="p-3 rounded bg-danger-muted border border-danger text-sm text-danger flex items-start gap-2">
                <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── Step 3: Generating ─────────────────── */}
      {step === 3 && generating && (
        <div className="card p-12 text-center">
          <div className="w-16 h-16 rounded-full bg-brand-50 flex items-center justify-center mx-auto mb-5">
            <Loader2 size={32} className="text-brand-500 animate-spin" />
          </div>
          <h3 className="text-lg font-bold text-text-primary mb-2">Generating Your Proposal</h3>
          <p className="text-sm text-text-secondary mb-6">{genProgress}</p>

          <div className="max-w-sm mx-auto space-y-3 text-left">
            {[
              { label: 'Fetch CRM deal data', done: true },
              { label: 'Apply pricing rules', done: genProgress.includes('AI') || genProgress.includes('Rendering') },
              { label: 'AI generating proposal sections', done: genProgress.includes('Rendering') },
              { label: 'Rendering document', done: false },
            ].map((s, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                {s.done ? (
                  <CheckCircle size={16} className="text-success" />
                ) : genProgress.toLowerCase().includes(s.label.toLowerCase().slice(0, 10)) ? (
                  <Loader2 size={16} className="text-brand-500 animate-spin" />
                ) : (
                  <div className="w-4 h-4 rounded-full border-2 border-border" />
                )}
                <span className={s.done ? 'text-text-primary' : 'text-text-muted'}>{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Step 4: Result & Deliver ───────────── */}
      {step === 4 && result && (
        <div className="grid grid-cols-[2fr_1fr] gap-5">
          {/* Success Card */}
          <div className="card p-5">
            <div className="flex items-center gap-4 mb-5">
              <div className="w-12 h-12 rounded bg-success-muted flex items-center justify-center">
                <CheckCircle size={28} className="text-success" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-text-primary">Proposal Generated!</h3>
                <p className="text-sm text-text-secondary">
                  {result.doc_id} • Generated in {result.generation_time}s
                  {result.salesforce_deal && ' • From live Salesforce data'}
                </p>
              </div>
            </div>

            {/* Pricing Breakdown */}
            {result.pricing && (
              <div className="mb-5">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Pricing Applied</h4>
                <div className="bg-subtle rounded p-4 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">Subtotal</span>
                    <span className="font-semibold text-text-primary">${result.pricing.subtotal?.toLocaleString()}</span>
                  </div>
                  {result.pricing.discount > 0 && (
                    <div className="flex justify-between text-sm">
                      <span className="text-success">Discount ({result.pricing.discount_details?.[0]?.percentage || ''})</span>
                      <span className="font-semibold text-success">-${result.pricing.discount?.toLocaleString()}</span>
                    </div>
                  )}
                  {result.pricing.tax > 0 && (
                    <div className="flex justify-between text-sm">
                      <span className="text-text-secondary">Tax ({result.pricing.tax_details?.[0]?.rate || ''})</span>
                      <span className="font-semibold text-text-primary">${result.pricing.tax?.toLocaleString()}</span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-border flex justify-between">
                    <span className="font-bold text-text-primary">Total</span>
                    <span className="text-lg font-bold text-text-primary">${result.pricing.total?.toLocaleString()}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Sections Generated */}
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Sections Generated</h4>
              <div className="flex flex-wrap gap-2">
                {(result.sections || []).map((sec) => (
                  <span key={sec} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-brand-50 text-xs font-medium text-brand-700">
                    <CheckCircle size={12} /> {sec}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="space-y-4">
            <div className="card p-5">
              <h3 className="text-[13px] font-bold text-text-primary mb-4">Actions</h3>
              <div className="space-y-3">
                <button onClick={handleDownload} className="btn-primary w-full justify-center">
                  <Download size={16} /> Download {outputFormat}
                </button>
                <button onClick={handleSendToClient} className="btn-secondary w-full justify-center" disabled={result.delivered}>
                  <Send size={16} /> {result.delivered ? 'Sent!' : 'Send to Client'}
                </button>
              </div>

              {result.delivered && (
                <div className="mt-3 p-3 rounded bg-success-muted text-sm text-success flex items-center gap-2">
                  <CheckCircle size={14} /> Document delivered
                </div>
              )}
            </div>

            <div className="card p-5">
              <h3 className="text-[13px] font-bold text-text-primary mb-3">Details</h3>
              <div className="space-y-2.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Document ID</span>
                  <span className="font-mono text-brand-500">{result.doc_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Format</span>
                  <span className="font-semibold">{result.format}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Gen Time</span>
                  <span className="font-semibold">{result.generation_time}s</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Source</span>
                  <span className="font-semibold">{result.source === 'salesforce_live' ? '🟢 Salesforce Live' : 'QuoteForge'}</span>
                </div>
              </div>
            </div>

            <button
              onClick={() => { setStep(1); setSelectedDeal(null); setResult(null); }}
              className="btn-secondary w-full justify-center"
            >
              <ArrowRight size={16} /> Generate Another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
