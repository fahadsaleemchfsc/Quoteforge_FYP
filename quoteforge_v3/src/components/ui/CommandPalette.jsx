import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';

// Cmd+K palette. Uses inline styles for every theme-aware surface so it
// renders correctly even if Tailwind's JIT hasn't compiled new color
// utilities yet (e.g. right after adding this file without a dev restart).

const COMMANDS = [
  { label: 'Go to Dashboard',        path: '/',             hint: 'D' },
  { label: 'Go to Negotiations',     path: '/negotiations', hint: 'N' },
  { label: 'Go to Approvals',        path: '/approvals',    hint: 'A' },
  { label: 'Go to Buyer Links',      path: '/share-links',  hint: null },
  { label: 'Go to Products',         path: '/products',     hint: 'P' },
  { label: 'Go to Guardrails',       path: '/guardrails',   hint: 'G' },
  { label: 'Go to Settings',         path: '/settings',     hint: null },
  { label: 'Go to CRM Integrations', path: '/crm',          hint: null },
  { label: 'Go to Documents',        path: '/documents',    hint: null },
  { label: 'Go to Users',            path: '/users',        hint: null },
  { label: 'Go to Templates',        path: '/templates',    hint: null },
];

const KBD_STYLE = {
  background: 'var(--bg-subtle)',
  color: 'var(--text-muted)',
  border: '1px solid var(--border)',
  borderRadius: 3,
  padding: '1px 5px',
  fontSize: 10,
  fontFamily: 'JetBrains Mono, ui-monospace, monospace',
};

export default function CommandPalette({ open, onClose }) {
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setQuery('');
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? COMMANDS.filter((c) => c.label.toLowerCase().includes(q)) : COMMANDS;
  }, [query]);

  function run(idx) {
    const c = filtered[idx];
    if (!c) return;
    navigate(c.path);
    onClose();
  }

  function handleKey(e) {
    if (e.key === 'Escape')    { e.preventDefault(); onClose(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, filtered.length - 1)); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); return; }
    if (e.key === 'Enter')     { e.preventDefault(); run(cursor); }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh] px-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ background: 'rgba(0, 0, 0, 0.5)' }}
    >
      <div
        className="w-full max-w-[560px] overflow-hidden"
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          boxShadow: '0 20px 40px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.04)',
        }}
      >
        {/* Search input row */}
        <div
          className="flex items-center gap-2.5 px-4"
          style={{ height: 48, borderBottom: '1px solid var(--border)' }}
        >
          <Search size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
            onKeyDown={handleKey}
            placeholder="Search commands or pages…"
            className="flex-1 outline-none text-[14px]"
            style={{
              background: 'transparent',
              color: 'var(--text-primary)',
              border: 'none',
            }}
          />
          <kbd style={KBD_STYLE}>ESC</kbd>
        </div>

        {/* Results list */}
        <ul
          className="overflow-y-auto"
          style={{
            background: 'var(--bg-surface)',
            maxHeight: 340,
            padding: '6px 0',
            margin: 0,
            listStyle: 'none',
          }}
        >
          {filtered.length === 0 ? (
            <li
              className="text-center py-6 text-[13px]"
              style={{ color: 'var(--text-muted)' }}
            >
              No matches
            </li>
          ) : filtered.map((c, i) => {
            const active = i === cursor;
            return (
              <li
                key={c.label}
                onMouseEnter={() => setCursor(i)}
                onClick={() => run(i)}
                className="flex items-center justify-between cursor-pointer text-[13px]"
                style={{
                  padding: '8px 16px',
                  background: active ? 'var(--accent-muted)' : 'transparent',
                  color: active ? 'var(--accent)' : 'var(--text-primary)',
                  fontWeight: active ? 500 : 400,
                }}
              >
                <span>{c.label}</span>
                {c.hint && (
                  <kbd
                    style={{
                      ...KBD_STYLE,
                      background: active ? 'var(--bg-surface)' : 'var(--bg-subtle)',
                      color: active ? 'var(--accent)' : 'var(--text-muted)',
                    }}
                  >
                    {c.hint}
                  </kbd>
                )}
              </li>
            );
          })}
        </ul>

        {/* Footer hint bar */}
        <div
          className="flex items-center justify-between px-4 text-[11px]"
          style={{
            background: 'var(--bg-subtle)',
            borderTop: '1px solid var(--border)',
            color: 'var(--text-muted)',
            padding: '6px 16px',
            fontFamily: 'JetBrains Mono, ui-monospace, monospace',
          }}
        >
          <span><kbd style={KBD_STYLE}>↑↓</kbd> navigate</span>
          <span><kbd style={KBD_STYLE}>↵</kbd> open</span>
          <span><kbd style={KBD_STYLE}>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
