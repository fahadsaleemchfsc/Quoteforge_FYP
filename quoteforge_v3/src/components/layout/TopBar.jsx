import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, ChevronDown, LogOut, Zap } from 'lucide-react';
import { useAuth } from '@context/AuthContext';
import { CommandPalette, ThemeToggle } from '@components/ui';

/*
 * Top bar — 56px, always visible.
 *   Left:   QuoteForge wordmark + tenant crumb
 *   Center: command palette trigger (pseudo search input, Cmd+K)
 *   Right:  theme toggle · user avatar + dropdown
 *
 * Intentionally no notification bell — unused and was a visual noise source.
 */

const TENANT_DISPLAY = 'Default Org';  // wire to /api/tenant/config in a later pass

export default function TopBar({ title, subtitle }) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Cmd/Ctrl+K opens palette.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  function handleLogout() { logout(); navigate('/login'); }

  return (
    <>
      <header
        className="h-14 flex items-center justify-between border-b glass-surface sticky top-0 z-30 px-5"
        style={{ borderColor: 'var(--border)' }}
      >
        {/* Left: crumb */}
        <div className="flex items-center gap-2.5 min-w-0 flex-shrink-0" style={{ width: 260 }}>
          <div className="font-semibold text-text-primary text-[13.5px] tracking-tight">QuoteForge</div>
          <span className="text-text-muted">/</span>
          <div className="text-[13px] text-text-secondary truncate">{TENANT_DISPLAY}</div>
        </div>

        {/* Center: command palette trigger */}
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="flex items-center gap-2 h-8 px-3 rounded border bg-subtle transition-colors"
          style={{ borderColor: 'var(--border)', minWidth: 340 }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-strong)'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
        >
          <Search size={13} className="text-text-muted flex-shrink-0" />
          <span className="text-[12.5px] text-text-muted flex-1 text-left">Search or press</span>
          <kbd className="font-mono text-[10px] text-text-muted bg-surface border border-border rounded px-1.5 py-0.5">⌘K</kbd>
        </button>

        {/* Right: controls */}
        <div className="flex items-center gap-2.5 justify-end flex-shrink-0" style={{ width: 260 }}>
          <ThemeToggle />

          <div className="w-px h-5 bg-border mx-1" />

          <div className="relative">
            <button
              onClick={() => setDropdownOpen((v) => !v)}
              className="flex items-center gap-2 px-2 py-1 rounded transition-colors hover:bg-subtle"
            >
              <div
                className="w-6 h-6 rounded flex items-center justify-center text-[10.5px] font-semibold"
                style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
              >
                {user?.avatar || 'U'}
              </div>
              <span className="text-[12.5px] font-medium text-text-primary">
                {user?.name?.split(' ')[0] || 'User'}
              </span>
              <ChevronDown size={11} className="text-text-muted" />
            </button>

            {dropdownOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setDropdownOpen(false)} />
                <div
                  className="absolute right-0 top-full mt-1 w-56 bg-surface border border-border rounded z-50 overflow-hidden"
                  style={{ boxShadow: 'var(--shadow-pop)' }}
                >
                  <div className="px-3 py-2.5 border-b border-border">
                    <div className="text-[13px] font-medium text-text-primary truncate">{user?.name}</div>
                    <div className="text-[11px] text-text-secondary truncate">{user?.email}</div>
                    <div
                      className="mt-1.5 inline-block font-mono text-[10px] px-1.5 rounded-sm"
                      style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
                    >
                      {isAdmin ? 'ADMIN' : 'USER'}
                    </div>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2 text-[13px] transition-colors"
                    style={{ color: 'var(--danger)' }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'var(--danger-muted)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                  >
                    <LogOut size={13} /> Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Page header row below the crumb bar */}
      {(title || subtitle) && (
        <div className="px-8 pt-6 pb-3 bg-app">
          {title && (
            <h1 className="text-[22px] font-semibold text-text-primary tracking-tight leading-tight">
              {title}
            </h1>
          )}
          {subtitle && (
            <p className="text-[13px] text-text-secondary mt-1">{subtitle}</p>
          )}
        </div>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
