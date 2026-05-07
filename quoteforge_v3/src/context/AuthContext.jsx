import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

// ─── Mock User Database (fallback if backend is unavailable) ─────
const MOCK_USERS = [
  { id: 1, name: 'Agha Zain Nadir', email: 'admin@quoteforge.io', password: 'admin123', role: 'admin', avatar: 'AZ', department: 'Engineering', status: 'active', quotesGenerated: 342, lastLogin: 'Feb 12, 2026 — 10:23 AM' },
  { id: 2, name: 'Sarah Johnson', email: 'sarah@quoteforge.io', password: 'user123', role: 'user', avatar: 'SJ', department: 'Sales', status: 'active', quotesGenerated: 156, lastLogin: 'Feb 12, 2026 — 09:45 AM' },
  { id: 3, name: 'Mike Rodriguez', email: 'mike@quoteforge.io', password: 'user123', role: 'user', avatar: 'MR', department: 'Sales', status: 'active', quotesGenerated: 89, lastLogin: 'Feb 11, 2026 — 04:12 PM' },
  { id: 4, name: 'Faraz Ali', email: 'faraz@quoteforge.io', password: 'admin123', role: 'admin', avatar: 'FA', department: 'AI Engineering', status: 'active', quotesGenerated: 0, lastLogin: 'Feb 12, 2026 — 08:00 AM' },
  { id: 5, name: 'Lisa Kim', email: 'lisa@quoteforge.io', password: 'user123', role: 'user', avatar: 'LK', department: 'Sales', status: 'inactive', quotesGenerated: 201, lastLogin: 'Feb 10, 2026 — 11:30 AM' },
  { id: 6, name: 'Fahad Saleem', email: 'fahad@quoteforge.io', password: 'admin123', role: 'admin', avatar: 'FS', department: 'Backend', status: 'active', quotesGenerated: 0, lastLogin: 'Feb 11, 2026 — 09:00 AM' },
  { id: 7, name: 'Saad Khalid', email: 'saad@quoteforge.io', password: 'admin123', role: 'admin', avatar: 'SK', department: 'Frontend', status: 'active', quotesGenerated: 0, lastLogin: 'Feb 12, 2026 — 07:15 AM' },
];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('qf_session');
    if (saved) {
      try { return JSON.parse(saved); } catch { return null; }
    }
    return null;
  });

  const isAuthenticated = !!user;
  const isAdmin = user?.role === 'admin';

  const login = useCallback(async (email, password) => {
    try {
      // Try real backend first
      const res = await api.post('/auth/login', { email, password });
      const { access_token, user: userData } = res.data;

      // Store JWT token
      localStorage.setItem('qf_token', access_token);

      const sessionUser = { ...userData, loginTime: new Date().toISOString() };
      setUser(sessionUser);
      localStorage.setItem('qf_session', JSON.stringify(sessionUser));
      return sessionUser;
    } catch (err) {
      // If backend is down, fall back to mock auth
      if (err.code === 'ERR_NETWORK' || err.code === 'ECONNREFUSED') {
        console.warn('Backend unavailable, using mock auth');
        await new Promise((r) => setTimeout(r, 800));

        const found = MOCK_USERS.find(
          (u) => u.email.toLowerCase() === email.toLowerCase() && u.password === password
        );
        if (!found) throw new Error('Invalid email or password');
        if (found.status !== 'active') throw new Error('Account is deactivated. Contact your administrator.');

        const sessionUser = { ...found };
        delete sessionUser.password;
        sessionUser.loginTime = new Date().toISOString();
        setUser(sessionUser);
        localStorage.setItem('qf_session', JSON.stringify(sessionUser));
        return sessionUser;
      }

      // Backend returned an error
      const msg = err.response?.data?.detail || 'Invalid email or password';
      throw new Error(msg);
    }
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem('qf_session');
    localStorage.removeItem('qf_token');
    // Try to notify backend (fire-and-forget)
    api.post('/auth/logout').catch(() => {});
  }, []);

  const getAllUsers = useCallback(async () => {
    try {
      const res = await api.get('/users');
      return res.data;
    } catch {
      // Fallback to mock
      return MOCK_USERS.map(({ password, ...u }) => u);
    }
  }, []);

  const value = useMemo(
    () => ({ user, isAuthenticated, isAdmin, login, logout, getAllUsers }),
    [user, isAuthenticated, isAdmin, login, logout, getAllUsers]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
