// ─── App Constants ────────────────────────────────────────────
export const APP_NAME = 'QuoteForge';
export const APP_VERSION = '1.0.0';

// Navigation items for the sidebar
export const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard' },
  { id: 'templates', label: 'Templates', path: '/templates', icon: 'FileText' },
  { id: 'pricing', label: 'Pricing & Rules', path: '/pricing', icon: 'DollarSign' },
  { id: 'prompts', label: 'AI Prompts', path: '/prompts', icon: 'Sparkles' },
  { id: 'crm', label: 'CRM Integrations', path: '/crm', icon: 'Link2' },
  { id: 'documents', label: 'Documents', path: '/documents', icon: 'Send' },
  { id: 'users', label: 'Users & Access', path: '/users', icon: 'Users' },
  { id: 'settings', label: 'Settings', path: '/settings', icon: 'Settings' },
];

// Page metadata (titles + subtitles)
export const PAGE_META = {
  '/dashboard': { title: 'Dashboard', subtitle: 'Overview of your quote generation pipeline' },
  '/templates': { title: 'Template Management', subtitle: 'Manage proposal and quote templates' },
  '/pricing': { title: 'Pricing & Rules', subtitle: 'Configure pricing rules, discounts, and compliance' },
  '/prompts': { title: 'AI Prompt Studio', subtitle: 'Manage AI prompt templates and configurations' },
  '/crm': { title: 'CRM Integrations', subtitle: 'Manage CRM platform connections' },
  '/documents': { title: 'Documents & Delivery', subtitle: 'Track generated documents and delivery status' },
  '/users': { title: 'Users & Access', subtitle: 'Manage users and role-based access' },
  '/settings': { title: 'Settings', subtitle: 'System configuration and preferences' },
};

// Status color configurations
export const STATUS_CONFIG = {
  active:       { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  connected:    { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  delivered:    { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' },
  generated:    { bg: 'bg-blue-100',  text: 'text-blue-800',  dot: 'bg-blue-500' },
  testing:      { bg: 'bg-amber-100', text: 'text-amber-800', dot: 'bg-amber-500' },
  pending:      { bg: 'bg-amber-100', text: 'text-amber-800', dot: 'bg-amber-500' },
  draft:        { bg: 'bg-gray-100',  text: 'text-gray-700',  dot: 'bg-gray-400' },
  inactive:     { bg: 'bg-gray-100',  text: 'text-gray-700',  dot: 'bg-gray-400' },
  disconnected: { bg: 'bg-red-100',   text: 'text-red-800',   dot: 'bg-red-500' },
  failed:       { bg: 'bg-red-100',   text: 'text-red-800',   dot: 'bg-red-500' },
  archived:     { bg: 'bg-gray-100',  text: 'text-gray-700',  dot: 'bg-gray-400' },
};

// User roles
export const ROLES = {
  ADMIN: 'Admin',
  SALES_MANAGER: 'Sales Manager',
  SALES_REP: 'Sales Rep',
};

// Compliance frameworks
export const COMPLIANCE = {
  SOC2: { label: 'SOC 2', region: 'US', color: 'brand' },
  GDPR: { label: 'GDPR', region: 'EU/US', color: 'cyan' },
  PPRA: { label: 'PPRA', region: 'PK', color: 'emerald' },
};

// Document formats
export const DOC_FORMATS = ['PDF', 'DOCX'];

// Prompt sections (for AI generation)
export const PROMPT_SECTIONS = [
  'Cover Letter',
  'Scope',
  'Pricing',
  'Deliverables',
  'Terms',
  'Summary',
];

// CRM platforms supported
export const CRM_PLATFORMS = ['Salesforce', 'HubSpot'];
