import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { FileCode2, Save, RotateCcw, Eye, Code2 } from 'lucide-react';
import clsx from 'clsx';
import templateService from '@/services/templateService';
import { useAuth } from '@/context/AuthContext';

// Sample variables used to render the live preview. Mirrors the keys the
// backend's render_pdf_from_html injects so what you see in the editor
// is close to what a real generated PDF looks like.
const SAMPLE_CONTEXT = {
  tenant_name: 'QuoteForge',
  doc_type: 'Proposal',
  doc_id: 'DOC-PREVIEW',
  deal_name: 'Q1 Platform License',
  deal_id: 'OPP-00184',
  client_name: 'Acme Corporation',
  region: 'US',
  seller_email: 'rep@quoteforge.io',
  currency_symbol: '$',
  generated_at: new Date(),
  valid_until: new Date(Date.now() + 30 * 86_400_000),
  compliance_framework: 'SOC 2',
  subtotal: 45000,
  discount: 2500,
  tax: 0,
  total: 42500,
  line_items: [
    { product: 'Platform License', quantity: 50, unit_price: 800 },
    { product: 'Onboarding & Training', quantity: 1, unit_price: 5000 },
  ],
};

// Approximate Jinja2 → JS rendering for the live preview. Real renders
// happen server-side via Jinja2 + xhtml2pdf, so this is a best-effort
// approximation that handles the patterns the default template uses:
//   {{ var }}          ─ value lookup
//   {{ var or 'x' }}   ─ fallback
//   {{ var.strftime(fmt) }} ─ date formatting (for Date objects)
//   {{ 'fmt'.format(x) }} ─ number formatting (only :,.2f honored)
//   {% for x in arr %}…{% else %}…{% endfor %}
//   {% if cond %}…{% endif %}
function renderJinjaApprox(html, ctx) {
  let s = html;

  // {% for item in line_items or [] %} … {% else %} … {% endfor %}
  s = s.replace(
    /\{%\s*for\s+(\w+)\s+in\s+([\w\s.|or\s\[\]]+?)\s*%\}([\s\S]*?)(?:\{%\s*else\s*%\}([\s\S]*?))?\{%\s*endfor\s*%\}/g,
    (_, varName, listExpr, body, elseBody = '') => {
      const listKey = listExpr.replace(/\s+or\s+\[\]/, '').trim();
      const list = ctx[listKey] || [];
      if (!list.length) return elseBody;
      return list
        .map((item) => {
          let bodyOut = body;
          // Replace {{ item.foo or 'x' }} and {{ item.foo }}
          bodyOut = bodyOut.replace(
            new RegExp(`\\{\\{\\s*${varName}\\.(\\w+)(?:\\s+or\\s+(?:'([^']*)'|"([^"]*)"|(\\d+)))?\\s*\\}\\}`, 'g'),
            (_m, prop, fb1, fb2, fb3) => {
              const v = item[prop];
              if (v !== undefined && v !== null && v !== '') return String(v);
              return fb1 ?? fb2 ?? fb3 ?? '';
            },
          );
          // Number-format helper: {{ '{:,.2f}'.format(item.unit_price or 0) }}
          bodyOut = bodyOut.replace(
            /\{\{\s*'\{:,\.2f\}'\.format\((?:\((\w+)\.(\w+)\s+or\s+(\d+)\)\s*\*\s*\((\w+)\.(\w+)\s+or\s+(\d+)\)|(\w+)\.(\w+)(?:\s+or\s+(\d+))?)\)\s*\}\}/g,
            (_m, va, vb, vd1, vc, vd, vd2, sa, sb, sd) => {
              const numFmt = (n) =>
                Number(n || 0).toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                });
              if (sa) return numFmt(item[sb] ?? sd);
              return numFmt((item[vb] ?? vd1) * (item[vd] ?? vd2));
            },
          );
          return bodyOut;
        })
        .join('');
    },
  );

  // {% if cond %} … {% endif %}  (very lightweight — only checks truthiness)
  s = s.replace(
    /\{%\s*if\s+([^%]+?)\s*%\}([\s\S]*?)\{%\s*endif\s*%\}/g,
    (_m, condExpr, body) => {
      // Evaluate `(varOrExpr or 0) > 0` and plain `varName` truthiness.
      const compMatch = condExpr.match(/^\(?\s*(\w+)(?:\s+or\s+0)?\)?\s*>\s*0\s*$/);
      if (compMatch) {
        const v = ctx[compMatch[1]];
        return v && v > 0 ? body : '';
      }
      return ctx[condExpr.trim()] ? body : '';
    },
  );

  // Number-format at top level: {{ '{:,.2f}'.format(total or 0) }}
  s = s.replace(
    /\{\{\s*'\{:,\.2f\}'\.format\((\w+)(?:\s+or\s+(\d+))?\)\s*\}\}/g,
    (_m, k, fb) => {
      const v = ctx[k];
      const n = v === undefined || v === null ? Number(fb || 0) : Number(v);
      return n.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    },
  );

  // Date formatting: {{ var.strftime('%B %d, %Y') if var else '' }}
  s = s.replace(
    /\{\{\s*(\w+)\.strftime\('([^']+)'\)(?:\s+if\s+\w+\s+else\s+'([^']*)')?\s*\}\}/g,
    (_m, k, fmt, fallback = '') => {
      const v = ctx[k];
      if (!(v instanceof Date)) return fallback;
      const months = [
        'January','February','March','April','May','June',
        'July','August','September','October','November','December',
      ];
      // Only %B %d, %Y is used by the default template.
      return `${months[v.getMonth()]} ${v.getDate()}, ${v.getFullYear()}`;
    },
  );

  // Filter: (var or 'x') | lower
  s = s.replace(
    /\{\{\s*\((\w+)(?:\s+or\s+'([^']*)')?\)\s*\|\s*lower\s*\}\}/g,
    (_m, k, fb) => String(ctx[k] ?? fb ?? '').toLowerCase(),
  );

  // {{ var or 'fallback' }} / {{ var or "fallback" }}
  s = s.replace(
    /\{\{\s*(\w+)\s+or\s+(?:'([^']*)'|"([^"]*)")\s*\}\}/g,
    (_m, k, fb1, fb2) => {
      const v = ctx[k];
      if (v === undefined || v === null || v === '') return fb1 ?? fb2 ?? '';
      return String(v);
    },
  );

  // {{ var }}
  s = s.replace(/\{\{\s*(\w+)\s*\}\}/g, (_m, k) => {
    const v = ctx[k];
    return v === undefined || v === null ? '' : String(v);
  });

  return s;
}

export default function MasterTemplateEditor() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [html, setHtml] = useState('');
  const [savedHtml, setSavedHtml] = useState('');
  const [meta, setMeta] = useState(null);
  const [view, setView] = useState('split'); // 'split' | 'code' | 'preview'

  useEffect(() => {
    templateService
      .getMaster()
      .then((res) => {
        setHtml(res.data.html_body || '');
        setSavedHtml(res.data.html_body || '');
        setMeta(res.data);
      })
      .catch((e) => {
        toast.error(`Couldn't load master template: ${e?.response?.data?.detail || e.message}`);
      })
      .finally(() => setLoading(false));
  }, []);

  const dirty = html !== savedHtml;

  const previewSrc = useMemo(() => renderJinjaApprox(html || '', SAMPLE_CONTEXT), [html]);

  const handleSave = async () => {
    if (!isAdmin) return;
    setSaving(true);
    try {
      const res = await templateService.putMaster(html);
      setSavedHtml(res.data.html_body);
      setMeta(res.data);
      toast.success('Master template saved. Next generated quote uses it.');
    } catch (e) {
      toast.error(`Save failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = () => {
    setHtml(savedHtml);
  };

  if (loading) {
    return (
      <div className="card p-6 mb-4">
        <div className="text-text-secondary text-sm">Loading master template…</div>
      </div>
    );
  }

  return (
    <div className="card p-0 mb-6 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-bg-subtle">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded bg-accent-muted flex items-center justify-center">
            <FileCode2 size={18} className="text-accent" />
          </div>
          <div>
            <div className="text-[13px] font-bold text-text-primary leading-tight">
              Master Template
              {meta?.is_default && (
                <span className="ml-2 text-[10px] uppercase tracking-wide font-semibold text-text-muted px-1.5 py-0.5 rounded bg-bg-muted">
                  Default · not yet saved
                </span>
              )}
            </div>
            <div className="text-xs text-text-secondary mt-0.5">
              Every quote PDF renders from this HTML. Capped at 2 pages by design.
              {meta?.usage_count ? ` Used in ${meta.usage_count} quote${meta.usage_count === 1 ? '' : 's'}.` : ''}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View switcher */}
          <div className="inline-flex rounded border border-border overflow-hidden">
            {[
              { v: 'split', icon: <FileCode2 size={13} />, label: 'Split' },
              { v: 'code', icon: <Code2 size={13} />, label: 'Code' },
              { v: 'preview', icon: <Eye size={13} />, label: 'Preview' },
            ].map(({ v, icon, label }) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={clsx(
                  'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium',
                  view === v
                    ? 'bg-accent text-accent-fg'
                    : 'bg-bg-surface text-text-secondary hover:text-text-primary',
                )}
              >
                {icon} {label}
              </button>
            ))}
          </div>

          {dirty && (
            <button
              onClick={handleRevert}
              className="icon-btn"
              title="Revert unsaved changes"
            >
              <RotateCcw size={14} className="text-text-secondary" />
            </button>
          )}

          <button
            onClick={handleSave}
            disabled={!isAdmin || !dirty || saving}
            className={clsx(
              'btn-primary',
              (!isAdmin || !dirty || saving) && 'opacity-50 cursor-not-allowed',
            )}
            title={!isAdmin ? 'Admin role required' : !dirty ? 'No changes to save' : ''}
          >
            <Save size={14} /> {saving ? 'Saving…' : dirty ? 'Save Master' : 'Saved'}
          </button>
        </div>
      </div>

      {/* Body */}
      <div
        className={clsx(
          'grid',
          view === 'split' && 'grid-cols-2',
          view === 'code' && 'grid-cols-1',
          view === 'preview' && 'grid-cols-1',
        )}
        style={{ minHeight: 560 }}
      >
        {(view === 'split' || view === 'code') && (
          <div className="border-r border-border">
            <textarea
              value={html}
              onChange={(e) => setHtml(e.target.value)}
              spellCheck={false}
              readOnly={!isAdmin}
              className="w-full h-full min-h-[560px] resize-none p-4 font-mono text-[12px] leading-[1.55] bg-bg-app text-text-primary outline-none focus:bg-bg-surface transition-colors"
              placeholder="<!DOCTYPE html>…"
            />
          </div>
        )}

        {(view === 'split' || view === 'preview') && (
          <div className="bg-white">
            <iframe
              key={previewSrc.length /* force reflow on change */}
              title="Master template preview"
              srcDoc={previewSrc}
              sandbox=""
              className="w-full h-full min-h-[560px] border-0"
            />
          </div>
        )}
      </div>

      {/* Footer hint */}
      {!isAdmin && (
        <div className="px-5 py-2 border-t border-border bg-bg-subtle text-xs text-text-muted">
          Read-only — only admin users can edit the master template.
        </div>
      )}
    </div>
  );
}
