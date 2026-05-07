import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Send, Package, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import axios from 'axios';

// Public page — builds its own API client so it doesn't try to attach the
// admin's JWT (admin auth interceptor would redirect 401 → /login, which we
// don't want here).
const API = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
});

function moneyFmt(amount, currency = 'USD') {
  const symbol = currency === 'USD' ? '$' : '';
  if (amount == null) return '—';
  return `${symbol}${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ──────────── Left: seller + catalog ────────────

function SellerPanel({ sellerName, products }) {
  return (
    <aside className="bg-subtle border-r border-border p-6 flex flex-col overflow-y-auto">
      <div className="mb-6">
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Negotiating with</div>
        <h1 className="text-xl font-semibold text-text-primary leading-tight">{sellerName}</h1>
        <p className="text-[13px] text-text-secondary mt-1">Agent-mediated quote room</p>
      </div>

      <div className="flex-1">
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-3">Products available</div>
        {products.length === 0 ? (
          <div className="text-sm text-text-muted">(seller has no public catalog)</div>
        ) : (
          <ul className="space-y-3">
            {products.map((p) => (
              <li key={p.sku} className="p-3 bg-surface border border-border rounded-md">
                <div className="flex items-start gap-2 mb-1">
                  <Package size={14} className="text-text-muted mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold text-text-primary truncate">{p.name}</div>
                    <div className="text-[11px] text-text-muted font-mono">{p.sku}</div>
                  </div>
                </div>
                <div className="pl-6 text-[12px] text-text-secondary">
                  from {moneyFmt(p.base_price, p.currency)} / {p.unit}
                </div>
                {p.description && (
                  <div className="pl-6 text-[11px] text-text-secondary mt-1 line-clamp-2">{p.description}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-6 pt-4 border-t border-border text-[11px] text-text-muted">
        Powered by QuoteForge · Deal infrastructure for the agentic commerce era
      </div>
    </aside>
  );
}

// ──────────── Center: chat ────────────

function ChatPanel({ messages, onSend, sending, greeting }) {
  const [draft, setDraft] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length]);

  function submit(e) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setDraft('');
    onSend(text);
  }

  return (
    <section className="flex flex-col bg-surface">
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {greeting && messages.length === 0 && (
          <MessageBubble role="assistant" text={greeting} />
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} text={m.text} />
        ))}
        {sending && <TypingIndicator />}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="border-t border-border p-4 bg-subtle">
        <div className="flex gap-2 items-end">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit(e);
              }
            }}
            placeholder={sending ? "working on it…" : "Ask for a quote or tell them what you need…"}
            rows={2}
            className="flex-1 px-3 py-2 border border-border rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            className="px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-md flex items-center gap-1.5 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed h-[52px]"
          >
            <Send size={14} /> Send
          </button>
        </div>
        <div className="text-[11px] text-text-muted mt-2">
          Shift + Enter for a new line
        </div>
      </form>
    </section>
  );
}

function MessageBubble({ role, text }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] px-4 py-2.5 rounded-2xl ${
          isUser
            ? 'bg-accent text-white rounded-br-sm'
            : 'bg-subtle text-text-primary rounded-bl-sm'
        }`}
      >
        <div className="text-[13.5px] whitespace-pre-wrap leading-relaxed">{text}</div>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-subtle px-4 py-3 rounded-2xl rounded-bl-sm">
        <div className="flex gap-1">
          <div className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-1.5 h-1.5 bg-text-muted rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}

// ──────────── Right: current offer ────────────

function OfferPanel({ offer, onAccept, accepting, error, committed }) {
  if (committed) {
    return (
      <aside className="bg-success-muted border-l border-success p-6 flex flex-col">
        <div className="flex items-center gap-2 text-success mb-4">
          <CheckCircle2 size={18} />
          <h2 className="text-[14px] font-semibold">Deal committed</h2>
        </div>
        <p className="text-[13px] text-text-secondary mb-2">
          Document ID: <span className="font-mono">{committed.document_id}</span>
        </p>
        <p className="text-[13px] text-text-secondary">
          Total: <span className="font-semibold">{moneyFmt(committed.total_cents / 100, committed.currency)}</span>
        </p>
        <p className="text-[12px] text-text-secondary mt-4">
          You'll receive a confirmation shortly.
        </p>
      </aside>
    );
  }

  if (!offer) {
    return (
      <aside className="bg-subtle border-l border-border p-6 text-center text-text-muted text-[13px] flex items-center justify-center">
        <div>
          <Package className="mx-auto mb-3 text-text-muted" size={32} />
          No active quote yet.<br />
          Tell the assistant what you need.
        </div>
      </aside>
    );
  }

  const pricing = offer.pricing || {};
  return (
    <aside className="bg-subtle border-l border-border p-6 flex flex-col overflow-y-auto">
      <div className="mb-4">
        <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Current quote</div>
        <h2 className="text-[14px] font-semibold text-text-primary font-mono">{offer.offer_id}</h2>
      </div>

      <div className="bg-surface border border-border rounded-md p-4 mb-4">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-text-muted">
              <th className="pb-2 font-medium">SKU</th>
              <th className="pb-2 text-right font-medium">Qty</th>
              <th className="pb-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {(offer.line_items || []).map((li, i) => (
              <tr key={i} className="border-t border-border">
                <td className="py-1.5 font-mono">{li.sku}</td>
                <td className="py-1.5 text-right">{li.quantity}</td>
                <td className="py-1.5 text-right font-medium">{moneyFmt(li.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="pt-3 mt-2 border-t border-border space-y-1 text-[12px]">
          <div className="flex justify-between text-text-secondary"><span>Subtotal</span><span>{moneyFmt(pricing.subtotal)}</span></div>
          {pricing.discount > 0 && (
            <div className="flex justify-between text-success"><span>Discount</span><span>-{moneyFmt(pricing.discount)}</span></div>
          )}
          <div className="flex justify-between font-semibold text-text-primary pt-1 border-t border-border">
            <span>Total</span><span>{moneyFmt(pricing.total, pricing.currency)}</span>
          </div>
        </div>
      </div>

      {offer.requires_approval && (
        <div className="p-3 bg-warning-muted border border-warning rounded-md mb-4 flex gap-2">
          <Clock size={14} className="text-warning mt-0.5 flex-shrink-0" />
          <div className="text-[12px] text-warning">
            Seller approval required before this commits. Once you accept, it goes to their review queue.
          </div>
        </div>
      )}

      {error && (
        <div className="p-3 bg-danger-muted border border-danger rounded-md mb-3 flex gap-2">
          <AlertCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
          <div className="text-[12px] text-danger">{error}</div>
        </div>
      )}

      <button
        className="w-full py-2.5 bg-success hover:opacity-90 text-white rounded-md text-sm font-medium disabled:opacity-50"
        onClick={onAccept}
        disabled={accepting}
      >
        {accepting ? 'Submitting…' : offer.requires_approval ? 'Accept & submit for approval' : 'Accept'}
      </button>
    </aside>
  );
}

// ──────────── Page ────────────

export default function BuyerRoom() {
  const { token } = useParams();
  const [ctx, setCtx] = useState(null);           // { session_id, seller_name, products, greeting }
  const [loadErr, setLoadErr] = useState('');
  const [messages, setMessages] = useState([]);   // {role, text}
  const [offer, setOffer] = useState(null);
  const [sending, setSending] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [acceptErr, setAcceptErr] = useState('');
  const [committed, setCommitted] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await API.get(`/buyer-room/${token}/context`);
        if (!cancelled) setCtx(res.data);
      } catch (e) {
        if (!cancelled) setLoadErr(e.response?.data?.detail || 'share link invalid');
      }
    }
    load();
    return () => { cancelled = true; };
  }, [token]);

  async function sendMessage(text) {
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setSending(true);
    try {
      const res = await API.post(`/buyer-room/${token}/message`, {
        session_id: ctx.session_id,
        content: text,
      });
      const reply = res.data.assistant_text;
      setMessages((prev) => [...prev, { role: 'assistant', text: reply }]);
      if (res.data.offer_state) setOffer(res.data.offer_state);

      // Detect commit from the server-side reply — the scripted/LLM reply
      // text announces doc IDs with the pattern "Document ID DOC-...".
      const docMatch = reply.match(/Document ID ([A-Z0-9-]+)/);
      if (docMatch) {
        const totalMatch = reply.match(/\$([\d,]+\.?\d*)/);
        setCommitted({
          document_id: docMatch[1],
          total_cents: totalMatch ? parseFloat(totalMatch[1].replace(/,/g, '')) * 100 : 0,
          currency: 'USD',
        });
      }
    } catch (e) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: `(something went wrong — ${e.response?.data?.detail || 'server unreachable'})`,
      }]);
    } finally {
      setSending(false);
    }
  }

  async function accept() {
    setAcceptErr('');
    setAccepting(true);
    // Route through the mediator with an explicit accept message — keeps
    // transcript coherent and the scripted/real mediator both handle it.
    await sendMessage('Yes, accept it.');
    setAccepting(false);
  }

  if (loadErr) {
    return (
      <div className="min-h-screen bg-subtle flex items-center justify-center p-6">
        <div className="max-w-md text-center">
          <AlertCircle className="mx-auto mb-4 text-danger" size={48} />
          <h1 className="text-xl font-semibold text-text-primary mb-2">Link unavailable</h1>
          <p className="text-text-secondary">{loadErr}</p>
          <p className="text-[12px] text-text-muted mt-6">Ask the seller for a fresh share link.</p>
        </div>
      </div>
    );
  }

  if (!ctx) {
    return (
      <div className="min-h-screen bg-subtle flex items-center justify-center">
        <div className="text-text-muted">Opening your quote room…</div>
      </div>
    );
  }

  return (
    <div
      className="h-screen grid"
      style={{
        gridTemplateColumns: '340px minmax(0, 1fr) 340px',
        fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
      }}
    >
      <SellerPanel sellerName={ctx.seller_name} products={ctx.products} />
      <ChatPanel
        messages={messages}
        greeting={ctx.greeting}
        onSend={sendMessage}
        sending={sending}
      />
      <OfferPanel
        offer={offer}
        onAccept={accept}
        accepting={accepting}
        error={acceptErr}
        committed={committed}
      />
    </div>
  );
}
