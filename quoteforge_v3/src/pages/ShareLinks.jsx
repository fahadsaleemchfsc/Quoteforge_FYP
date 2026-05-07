import { useEffect, useState } from 'react';
import { Link as LinkIcon, Plus, Copy, Check, Trash2, ExternalLink } from 'lucide-react';
import api from '@/services/api';
import clsx from 'clsx';

function timeAgo(iso) {
  if (!iso) return '—';
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return `${Math.floor(d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86_400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86_400)}d ago`;
}

function timeUntil(iso) {
  if (!iso) return '—';
  const d = (new Date(iso).getTime() - Date.now()) / 1000;
  if (d <= 0) return 'expired';
  if (d < 3600) return `${Math.floor(d / 60)}m`;
  if (d < 86_400) return `${Math.floor(d / 3600)}h`;
  return `${Math.floor(d / 86_400)}d`;
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  async function onCopy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button
      className="icon-btn"
      onClick={onCopy}
      title="Copy share URL"
    >
      {copied
        ? <Check size={14} className="text-success" />
        : <Copy size={14} className="text-text-secondary" />}
    </button>
  );
}

export default function ShareLinks() {
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [label, setLabel] = useState('Buyer quote request');

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('/share-tokens');
      setTokens(res.data.tokens);
      setError('');
    } catch (e) {
      setError(e.response?.data?.detail || 'failed to load share links');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function createLink() {
    setCreating(true);
    try {
      await api.post('/share-tokens', { label: label || 'Buyer quote request', expires_in_days: 7 });
      setLabel('Buyer quote request');
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || 'create failed');
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id) {
    if (!confirm('Revoke this share link? Buyers using it will get an expired error.')) return;
    try {
      await api.delete(`/share-tokens/${id}`);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || 'revoke failed');
    }
  }

  return (
    <div className="page-enter max-w-[1000px]">
      <div className="card p-5 mb-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded bg-brand-50 flex items-center justify-center">
            <LinkIcon size={20} className="text-brand-500" />
          </div>
          <h3 className="text-[13px] font-bold text-text-primary">Generate a new buyer link</h3>
        </div>
        <p className="text-xs text-text-secondary mb-3">
          Share the resulting URL with a buyer. It opens a chat-based quote room that talks to
          your guardrails through our Claude-mediated assistant. Links expire after 7 days.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Link label (e.g. 'Acme Corp renewal Q2')"
            className="input-field flex-1"
          />
          <button
            className="btn-primary"
            onClick={createLink}
            disabled={creating}
          >
            <Plus size={14} /> {creating ? 'generating…' : 'Generate buyer link'}
          </button>
        </div>
        {error && (
          <div className="mt-3 p-2 bg-danger-muted border border-danger text-danger text-sm rounded">
            {error}
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border">
          <h3 className="text-[13px] font-semibold text-text-primary">Active links</h3>
          <p className="text-[12px] text-text-secondary mt-0.5">{tokens.length} total</p>
        </div>
        <table className="w-full">
          <thead>
            <tr className="bg-subtle">
              <th className="table-header">Label</th>
              <th className="table-header">Share URL</th>
              <th className="table-header">Created</th>
              <th className="table-header">Last used</th>
              <th className="table-header">Expires in</th>
              <th className="table-header">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="table-cell text-center text-text-muted py-8">loading…</td></tr>
            ) : tokens.length === 0 ? (
              <tr><td colSpan={6} className="table-cell text-center text-text-muted py-8">no share links yet — generate one above</td></tr>
            ) : (
              tokens.map((t) => {
                const expired = timeUntil(t.expires_at) === 'expired';
                return (
                  <tr key={t.id} className="table-row">
                    <td className="table-cell font-semibold text-text-primary">{t.label}</td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <code className="font-mono text-xs text-text-secondary bg-subtle px-2 py-0.5 rounded border border-border truncate max-w-[300px]">
                          {t.share_url}
                        </code>
                        <CopyButton text={t.share_url} />
                        <a className="icon-btn" href={t.share_url} target="_blank" rel="noreferrer" title="Open">
                          <ExternalLink size={14} className="text-text-secondary" />
                        </a>
                      </div>
                    </td>
                    <td className="table-cell text-xs text-text-secondary">{timeAgo(t.created_at)}</td>
                    <td className="table-cell text-xs text-text-secondary">
                      {t.last_used_at ? timeAgo(t.last_used_at) : 'never'}
                    </td>
                    <td className="table-cell text-xs">
                      <span className={clsx(
                        'font-mono',
                        expired ? 'text-danger' : 'text-text-secondary',
                      )}>
                        {timeUntil(t.expires_at)}
                      </span>
                    </td>
                    <td className="table-cell">
                      <button className="icon-btn" onClick={() => revoke(t.id)} title="Revoke">
                        <Trash2 size={14} className="text-danger" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
