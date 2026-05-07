import { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from '@components/layout/Sidebar';
import TopBar from '@components/layout/TopBar';
import DashboardPage from '@pages/DashboardPage';
import TemplatesPage from '@pages/TemplatesPage';
import PricingPage from '@pages/PricingPage';
import PromptsPage from '@pages/PromptsPage';
import CRMPage from '@pages/CRMPage';
import DocumentsPage from '@pages/DocumentsPage';
import UsersPage from '@pages/UsersPage';
import SettingsPage from '@pages/SettingsPage';

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen">
      <Sidebar
        collapsed={sidebarCollapsed}
        setCollapsed={setSidebarCollapsed}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-8 overflow-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/prompts" element={<PromptsPage />} />
            <Route path="/crm" element={<CRMPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
