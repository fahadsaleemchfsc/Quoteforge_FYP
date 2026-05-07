import { createContext, useCallback, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext(null);
const STORAGE_KEY = 'qf-theme';

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolveEffective(theme) {
  if (theme === 'system') return systemPrefersDark() ? 'dark' : 'light';
  return theme;
}

function applyToRoot(effective) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', effective);
  document.documentElement.style.colorScheme = effective;
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    if (typeof window === 'undefined') return 'system';
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system';
  });

  const [effectiveTheme, setEffectiveTheme] = useState(() => resolveEffective(theme));

  // Apply to <html> on every theme change.
  useEffect(() => {
    const eff = resolveEffective(theme);
    setEffectiveTheme(eff);
    applyToRoot(eff);
  }, [theme]);

  // Watch system preference changes when theme==='system'.
  useEffect(() => {
    if (theme !== 'system' || typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => {
      const eff = e.matches ? 'dark' : 'light';
      setEffectiveTheme(eff);
      applyToRoot(eff);
    };
    mq.addEventListener?.('change', handler);
    return () => mq.removeEventListener?.('change', handler);
  }, [theme]);

  const setTheme = useCallback((next) => {
    if (!['light', 'dark', 'system'].includes(next)) return;
    window.localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, effectiveTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (ctx == null) {
    // Safe fallback — pages rendered outside the provider get light.
    return { theme: 'light', setTheme: () => {}, effectiveTheme: 'light' };
  }
  return ctx;
}

// Pre-hydration script to prevent FOUC. Inline in <head> via index.html if needed;
// safe to also re-run here in a module.
(function preHydrate() {
  if (typeof document === 'undefined') return;
  try {
    const stored = window.localStorage?.getItem(STORAGE_KEY);
    const theme = stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system';
    const eff = theme === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : theme;
    applyToRoot(eff);
  } catch { /* localStorage unavailable — let default kick in */ }
})();
