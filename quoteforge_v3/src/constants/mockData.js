import { FileText, Send, TrendingUp, Clock } from 'lucide-react';

// ─── Dashboard Metrics ────────────────────────────────────────
export const DASHBOARD_METRICS = [
  { label: 'Quotes Generated', value: '1,247', change: '+12.5%', up: true, icon: FileText, color: '#3576e8' },
  { label: 'Proposals Sent',   value: '834',   change: '+8.2%',  up: true, icon: Send, color: '#0891b2' },
  { label: 'Conversion Rate',  value: '67.3%', change: '+3.1%',  up: true, icon: TrendingUp, color: '#10b981' },
  { label: 'Avg. Gen Time',    value: '4.2s',  change: '-0.8s',  up: true, icon: Clock, color: '#f59e0b' },
];

// ─── Chart Data ───────────────────────────────────────────────
export const CHART_DATA = [
  { month: 'Jul', quotes: 145, proposals: 98,  conversions: 62 },
  { month: 'Aug', quotes: 178, proposals: 121, conversions: 79 },
  { month: 'Sep', quotes: 162, proposals: 108, conversions: 71 },
  { month: 'Oct', quotes: 201, proposals: 142, conversions: 95 },
  { month: 'Nov', quotes: 189, proposals: 131, conversions: 88 },
  { month: 'Dec', quotes: 223, proposals: 156, conversions: 104 },
  { month: 'Jan', quotes: 247, proposals: 172, conversions: 118 },
];

// ─── Recent Activity ──────────────────────────────────────────
export const RECENT_ACTIVITY = [
  { id: 1, type: 'quote',    client: 'Acme Corp',      deal: 'Enterprise License',  amount: '$45,000',  status: 'delivered', time: '2 min ago',  user: 'Sarah J.' },
  { id: 2, type: 'proposal', client: 'TechStart Inc',  deal: 'SaaS Platform',       amount: '$128,000', status: 'generated', time: '15 min ago', user: 'Mike R.' },
  { id: 3, type: 'quote',    client: 'Global Traders',  deal: 'Consulting Package',  amount: '$22,500',  status: 'pending',   time: '1 hr ago',   user: 'Lisa K.' },
  { id: 4, type: 'proposal', client: 'Nexus Systems',   deal: 'Infrastructure',      amount: '$89,000',  status: 'delivered', time: '2 hrs ago',  user: 'James W.' },
  { id: 5, type: 'quote',    client: 'Pinnacle Health', deal: 'Data Analytics',      amount: '$67,200',  status: 'failed',    time: '3 hrs ago',  user: 'Sarah J.' },
];

// ─── CRM Connections (used by Dashboard health panel) ─────────
export const CRM_CONNECTIONS = [
  { id: 1, platform: 'Salesforce', status: 'connected',    lastSync: '2 min ago', deals: 1247, health: 99.8 },
  { id: 2, platform: 'HubSpot',   status: 'connected',    lastSync: '5 min ago', deals: 342,  health: 98.2 },
  { id: 3, platform: 'Custom',    status: 'disconnected',  lastSync: '3 days ago', deals: 89,  health: 0 },
];

// ─── Templates ────────────────────────────────────────────────
export const TEMPLATES = [
  { id: 1, name: 'Enterprise Sales Proposal',  type: 'Proposal', format: 'PDF',  status: 'active',   lastModified: 'Jan 28, 2026', usageCount: 342, author: 'Admin' },
  { id: 2, name: 'Standard Quote Template',    type: 'Quote',    format: 'DOCX', status: 'active',   lastModified: 'Jan 25, 2026', usageCount: 891, author: 'Admin' },
  { id: 3, name: 'SaaS Renewal Template',      type: 'Proposal', format: 'PDF',  status: 'active',   lastModified: 'Jan 20, 2026', usageCount: 56,  author: 'System' },
  { id: 4, name: 'SaaS Subscription Quote',    type: 'Quote',    format: 'PDF',  status: 'draft',    lastModified: 'Jan 18, 2026', usageCount: 0,   author: 'Mike R.' },
  { id: 5, name: 'Consulting Services Proposal', type: 'Proposal', format: 'DOCX', status: 'active', lastModified: 'Jan 15, 2026', usageCount: 234, author: 'Admin' },
  { id: 6, name: 'Managed Services Quote',     type: 'Quote',    format: 'PDF',  status: 'archived', lastModified: 'Dec 12, 2025', usageCount: 178, author: 'Admin' },
];

// ─── Pricing Rules ────────────────────────────────────────────
export const PRICING_RULES = [
  { id: 1, name: 'Volume Discount Tier 1',   type: 'Discount',   condition: 'Qty > 100',     value: '10%',      region: 'Global', status: 'active' },
  { id: 2, name: 'Enterprise Discount',      type: 'Discount',   condition: 'Deal > $50K',   value: '15%',      region: 'US',     status: 'active' },
  { id: 3, name: 'Sales Tax — US',           type: 'Tax',        condition: 'Region = US',    value: 'Variable', region: 'US',     status: 'active' },
  { id: 4, name: 'VAT — EU',                 type: 'Tax',        condition: 'Region = EU',    value: '20%',      region: 'EU',     status: 'active' },
];

// ─── AI Prompts ───────────────────────────────────────────────
export const AI_PROMPTS = [
  { id: 1, name: 'Cover Letter Generator',   section: 'Cover Letter',  version: 'v3.2', status: 'active',  tokens: '~450', lastUsed: '2 min ago' },
  { id: 2, name: 'Scope of Work Builder',    section: 'Scope',         version: 'v2.8', status: 'active',  tokens: '~680', lastUsed: '15 min ago' },
  { id: 3, name: 'Pricing Notes Composer',   section: 'Pricing',       version: 'v4.1', status: 'active',  tokens: '~320', lastUsed: '1 hr ago' },
  { id: 4, name: 'Deliverables Formatter',   section: 'Deliverables',  version: 'v2.0', status: 'active',  tokens: '~520', lastUsed: '2 hrs ago' },
  { id: 5, name: 'Terms & Conditions Writer', section: 'Terms',        version: 'v3.5', status: 'testing', tokens: '~780', lastUsed: '1 day ago' },
  { id: 6, name: 'Executive Summary',        section: 'Summary',       version: 'v1.2', status: 'draft',   tokens: '~400', lastUsed: 'Never' },
];

// ─── Document Logs ────────────────────────────────────────────
export const DOCUMENT_LOGS = [
  { id: 'DOC-2401', client: 'Acme Corp',      type: 'Quote',    format: 'PDF',  status: 'delivered', generatedAt: 'Feb 12, 10:23 AM', deliveredAt: 'Feb 12, 10:24 AM', user: 'Sarah J.' },
  { id: 'DOC-2400', client: 'TechStart Inc',  type: 'Proposal', format: 'DOCX', status: 'generated', generatedAt: 'Feb 12, 10:08 AM', deliveredAt: '—',                user: 'Mike R.' },
  { id: 'DOC-2399', client: 'Global Traders',  type: 'Quote',    format: 'PDF',  status: 'pending',   generatedAt: 'Feb 12, 09:45 AM', deliveredAt: '—',                user: 'Lisa K.' },
  { id: 'DOC-2398', client: 'Nexus Systems',   type: 'Proposal', format: 'PDF',  status: 'delivered', generatedAt: 'Feb 12, 08:12 AM', deliveredAt: 'Feb 12, 08:13 AM', user: 'James W.' },
  { id: 'DOC-2397', client: 'Pinnacle Health', type: 'Quote',    format: 'DOCX', status: 'failed',    generatedAt: 'Feb 12, 07:30 AM', deliveredAt: '—',                user: 'Sarah J.' },
];
