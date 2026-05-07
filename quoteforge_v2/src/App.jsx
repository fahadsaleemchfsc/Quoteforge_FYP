import { useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from '@context/AuthContext';
import { Sidebar, TopBar } from '@components/layout';
import { PAGE_META } from '@constants/navigation';
import {
  Dashboard, Templates, Pricing, Prompts,
  CRM, Documents, Users, Settings, Login,
} from '@pages';

// ─── Protected Route Wrapper ────────────────────────────────
function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

// ─── Admin-Only Route ───────────────────────────────────────
function RequireAdmin({ children, fallback }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return fallback || <Navigate to="/" replace />;
  return children;
}

// ─── Authenticated App Shell (Sidebar + TopBar + Routes) ────
function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const location = useLocation();
  const meta = PAGE_META[location.pathname] || { title: 'QuoteForge', subtitle: '' };

  return (
    <div className="flex min-h-screen">
      <Sidebar collapsed={sidebarCollapsed} setCollapsed={setSidebarCollapsed} />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        <main className="flex-1 p-8 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/crm" element={<CRM />} />
            <Route path="/documents" element={<Documents />} />

            {/* Admin-only routes */}
            <Route path="/pricing" element={<RequireAdmin><Pricing /></RequireAdmin>} />
            <Route path="/prompts" element={<RequireAdmin><Prompts /></RequireAdmin>} />
            <Route path="/users" element={<Users />} />
            <Route path="/settings" element={<RequireAdmin><Settings /></RequireAdmin>} />

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

// ─── Root App Component ─────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public route */}
        <Route path="/login" element={<LoginGuard />} />

        {/* All other routes are protected */}
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}

// ─── Redirect away from login if already authenticated ──────
function LoginGuard() {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <Login />;
}
