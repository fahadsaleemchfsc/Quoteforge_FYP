// ─── Dashboard Metrics ────────────────────────────────────────
export const dashboardMetrics = [
  { label: 'Quotes Generated', value: '1,247', change: '+12.5%', up: true, icon: 'FileText', color: '#6366f1' },
  { label: 'Proposals Sent', value: '834', change: '+8.2%', up: true, icon: 'Send', color: '#06b6d4' },
  { label: 'Conversion Rate', value: '67.3%', change: '+3.1%', up: true, icon: 'TrendingUp', color: '#10b981' },
  { label: 'Avg. Generation Time', value: '4.2s', change: '-0.8s', up: true, icon: 'Clock', color: '#f59e0b' },
];

// ─── Chart Data ───────────────────────────────────────────────
export const chartData = [
  { month: 'Jul', quotes: 145, proposals: 98, conversions: 62 },
  { month: 'Aug', quotes: 178, proposals: 121, conversions: 79 },
  { month: 'Sep', quotes: 162, proposals: 108, conversions: 71 },
  { month: 'Oct', quotes: 201, proposals: 142, conversions: 95 },
  { month: 'Nov', quotes: 189, proposals: 131, conversions: 88 },
  { month: 'Dec', quotes: 223, proposals: 156, conversions: 104 },
  { month: 'Jan', quotes: 247, proposals: 172, conversions: 118 },
];

// ─── Recent Activity ──────────────────────────────────────────
export const recentActivity = [
  { id: 1, type: 'quote', client: 'Acme Corp', deal: 'Enterprise License', amount: '$45,000', status: 'delivered', time: '2 min ago', user: 'Sarah J.' },
  { id: 2, type: 'proposal', client: 'TechStart Inc', deal: 'SaaS Platform', amount: '$128,000', status: 'generated', time: '15 min ago', user: 'Mike R.' },
  { id: 3, type: 'quote', client: 'Global Traders', deal: 'Consulting Package', amount: '$22,500', status: 'pending', time: '1 hr ago', user: 'Lisa K.' },
  { id: 4, type: 'proposal', client: 'Nexus Systems', deal: 'Infrastructure', amount: '$89,000', status: 'delivered', time: '2 hrs ago', user: 'James W.' },
  { id: 5, type: 'quote', client: 'Pinnacle Health', deal: 'Data Analytics', amount: '$67,200', status: 'failed', time: '3 hrs ago', user: 'Sarah J.' },
];

// ─── Templates ────────────────────────────────────────────────
export const templates = [
  { id: 1, name: 'Enterprise Sales Proposal', type: 'Proposal', format: 'PDF', status: 'active', lastModified: 'Jan 28, 2026', usageCount: 342, author: 'Admin' },
  { id: 2, name: 'Standard Quote Template', type: 'Quote', format: 'DOCX', status: 'active', lastModified: 'Jan 25, 2026', usageCount: 891, author: 'Admin' },
  { id: 3, name: 'Government Procurement (PPRA)', type: 'Proposal', format: 'PDF', status: 'active', lastModified: 'Jan 20, 2026', usageCount: 56, author: 'System' },
  { id: 4, name: 'SaaS Subscription Quote', type: 'Quote', format: 'PDF', status: 'draft', lastModified: 'Jan 18, 2026', usageCount: 0, author: 'Mike R.' },
  { id: 5, name: 'Consulting Services Proposal', type: 'Proposal', format: 'DOCX', status: 'active', lastModified: 'Jan 15, 2026', usageCount: 234, author: 'Admin' },
  { id: 6, name: 'Healthcare Compliance Quote', type: 'Quote', format: 'PDF', status: 'archived', lastModified: 'Dec 12, 2025', usageCount: 178, author: 'Admin' },
];

// ─── Pricing Rules ────────────────────────────────────────────
export const pricingRules = [
  { id: 1, name: 'Volume Discount Tier 1', type: 'Discount', condition: 'Qty > 100', value: '10%', region: 'Global', status: 'active' },
  { id: 2, name: 'Enterprise Discount', type: 'Discount', condition: 'Deal > $50K', value: '15%', region: 'US', status: 'active' },
  { id: 3, name: 'Sales Tax - US', type: 'Tax', condition: 'Region = US', value: 'Variable', region: 'US', status: 'active' },
  { id: 4, name: 'GST Pakistan', type: 'Tax', condition: 'Region = PK', value: '17%', region: 'PK', status: 'active' },
  { id: 5, name: 'PPRA Compliance Clause', type: 'Compliance', condition: 'Region = PK', value: 'Required', region: 'PK', status: 'active' },
  { id: 6, name: 'GDPR Data Clause', type: 'Compliance', condition: 'Region = EU/US', value: 'Required', region: 'US/EU', status: 'active' },
  { id: 7, name: 'SOC 2 Security Terms', type: 'Compliance', condition: 'Always', value: 'Required', region: 'Global', status: 'active' },
];

// ─── AI Prompts ───────────────────────────────────────────────
export const aiPrompts = [
  { id: 1, name: 'Cover Letter Generator', section: 'Cover Letter', version: 'v3.2', status: 'active', tokens: '~450', lastUsed: '2 min ago' },
  { id: 2, name: 'Scope of Work Builder', section: 'Scope', version: 'v2.8', status: 'active', tokens: '~680', lastUsed: '15 min ago' },
  { id: 3, name: 'Pricing Notes Composer', section: 'Pricing', version: 'v4.1', status: 'active', tokens: '~320', lastUsed: '1 hr ago' },
  { id: 4, name: 'Deliverables Formatter', section: 'Deliverables', version: 'v2.0', status: 'active', tokens: '~520', lastUsed: '2 hrs ago' },
  { id: 5, name: 'Terms & Conditions Writer', section: 'Terms', version: 'v3.5', status: 'testing', tokens: '~780', lastUsed: '1 day ago' },
  { id: 6, name: 'Executive Summary', section: 'Summary', version: 'v1.2', status: 'draft', tokens: '~400', lastUsed: 'Never' },
];

// ─── CRM Connections ──────────────────────────────────────────
export const crmConnections = [
  { id: 1, name: 'Salesforce Production', platform: 'Salesforce', status: 'connected', lastSync: '2 min ago', deals: 1247, health: 99.8 },
  { id: 2, name: 'HubSpot Sandbox', platform: 'HubSpot', status: 'connected', lastSync: '5 min ago', deals: 342, health: 98.2 },
  { id: 3, name: 'Salesforce Sandbox', platform: 'Salesforce', status: 'disconnected', lastSync: '3 days ago', deals: 89, health: 0 },
];

// ─── Users ────────────────────────────────────────────────────
export const users = [
  { id: 1, name: 'Sarah Johnson', email: 'sarah.j@company.com', role: 'Admin', status: 'active', lastLogin: '2 min ago' },
  { id: 2, name: 'Mike Rodriguez', email: 'mike.r@company.com', role: 'Sales Manager', status: 'active', lastLogin: '1 hr ago' },
  { id: 3, name: 'Lisa Kim', email: 'lisa.k@company.com', role: 'Sales Rep', status: 'active', lastLogin: '3 hrs ago' },
  { id: 4, name: 'James Williams', email: 'james.w@company.com', role: 'Sales Rep', status: 'active', lastLogin: '1 day ago' },
  { id: 5, name: 'Emily Chen', email: 'emily.c@company.com', role: 'Sales Rep', status: 'inactive', lastLogin: '2 weeks ago' },
];

// ─── Document Logs ────────────────────────────────────────────
export const documentLogs = [
  { id: 'DOC-2401', client: 'Acme Corp', type: 'Quote', format: 'PDF', status: 'delivered', generatedAt: 'Feb 12, 10:23 AM', deliveredAt: 'Feb 12, 10:24 AM', user: 'Sarah J.' },
  { id: 'DOC-2400', client: 'TechStart Inc', type: 'Proposal', format: 'DOCX', status: 'generated', generatedAt: 'Feb 12, 10:08 AM', deliveredAt: '—', user: 'Mike R.' },
  { id: 'DOC-2399', client: 'Global Traders', type: 'Quote', format: 'PDF', status: 'pending', generatedAt: 'Feb 12, 09:45 AM', deliveredAt: '—', user: 'Lisa K.' },
  { id: 'DOC-2398', client: 'Nexus Systems', type: 'Proposal', format: 'PDF', status: 'delivered', generatedAt: 'Feb 12, 08:12 AM', deliveredAt: 'Feb 12, 08:13 AM', user: 'James W.' },
  { id: 'DOC-2397', client: 'Pinnacle Health', type: 'Quote', format: 'DOCX', status: 'failed', generatedAt: 'Feb 12, 07:30 AM', deliveredAt: '—', user: 'Sarah J.' },
];

// ─── Role Permissions ─────────────────────────────────────────
export const rolePermissions = [
  { perm: 'Generate Quotes', admin: true, manager: true, rep: true },
  { perm: 'Manage Templates', admin: true, manager: true, rep: false },
  { perm: 'Configure Pricing Rules', admin: true, manager: false, rep: false },
  { perm: 'Manage AI Prompts', admin: true, manager: false, rep: false },
  { perm: 'CRM Integration Settings', admin: true, manager: false, rep: false },
  { perm: 'User Management', admin: true, manager: false, rep: false },
  { perm: 'View Audit Logs', admin: true, manager: true, rep: false },
];

// ─── CRM Field Mappings ───────────────────────────────────────
export const crmFieldMappings = [
  { crm: 'Opportunity Name', maps: 'deal_name', icon: 'Tag' },
  { crm: 'Account Name', maps: 'client_name', icon: 'Users' },
  { crm: 'Amount', maps: 'deal_amount', icon: 'DollarSign' },
  { crm: 'Line Items', maps: 'products[]', icon: 'Package' },
  { crm: 'Contact Email', maps: 'contact_email', icon: 'Mail' },
  { crm: 'Close Date', maps: 'close_date', icon: 'Clock' },
  { crm: 'Stage', maps: 'deal_stage', icon: 'Layers' },
  { crm: 'Region', maps: 'compliance_region', icon: 'Globe' },
];

// ─── Settings Config ──────────────────────────────────────────
export const settingsSections = [
  {
    title: 'General Settings',
    icon: 'Settings',
    fields: [
      { label: 'Organization Name', type: 'text', value: 'Acme Corporation', desc: 'Your company name used in generated documents' },
      { label: 'Default Currency', type: 'select', value: 'USD', options: ['USD', 'PKR', 'EUR', 'GBP'], desc: 'Default currency for quotes' },
      { label: 'Default Compliance Region', type: 'select', value: 'US (SOC 2 + GDPR)', options: ['US (SOC 2 + GDPR)', 'PK (PPRA)', 'EU (GDPR)'], desc: 'Default regulatory framework' },
    ],
  },
  {
    title: 'AI Configuration',
    icon: 'Sparkles',
    fields: [
      { label: 'AI Model', type: 'select', value: 'GPT-4o', options: ['GPT-4o', 'GPT-4o-mini', 'Claude 3.5 Sonnet'], desc: 'LLM used for content generation' },
      { label: 'Temperature', type: 'text', value: '0.3', desc: 'Controls creativity (0.0 = deterministic, 1.0 = creative)' },
      { label: 'Max Tokens', type: 'text', value: '2048', desc: 'Maximum output length per section' },
    ],
  },
  {
    title: 'Email & Delivery',
    icon: 'Mail',
    fields: [
      { label: 'SMTP Host', type: 'text', value: 'smtp.sendgrid.net', desc: 'SMTP server for document delivery' },
      { label: 'Sender Email', type: 'text', value: 'quotes@acmecorp.com', desc: 'From address on delivered documents' },
      { label: 'Auto-deliver on Generation', type: 'toggle', value: true, desc: 'Automatically send documents after generation' },
    ],
  },
  {
    title: 'Security',
    icon: 'Shield',
    fields: [
      { label: 'Session Timeout (minutes)', type: 'text', value: '30', desc: 'Auto-logout after inactivity' },
      { label: 'Two-Factor Authentication', type: 'toggle', value: true, desc: 'Require 2FA for all users' },
      { label: 'API Rate Limit (req/min)', type: 'text', value: '60', desc: 'Maximum API requests per minute' },
    ],
  },
];
