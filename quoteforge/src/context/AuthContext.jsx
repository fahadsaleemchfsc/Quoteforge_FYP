import { createContext, useContext, useState, useCallback } from 'react';

const AuthContext = createContext(null);

/**
 * AuthProvider wraps the app and provides authentication state.
 * Currently uses mock data — replace with real API calls later.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState({
    id: 1,
    name: 'Admin User',
    email: 'admin@quoteforge.com',
    role: 'Admin',
  });
  const [isAuthenticated, setIsAuthenticated] = useState(true);

  const login = useCallback(async (email, password) => {
    // TODO: Replace with authService.login()
    setUser({ id: 1, name: 'Admin User', email, role: 'Admin' });
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    // TODO: Replace with authService.logout()
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('access_token');
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export default AuthContext;
