import {
  LayoutDashboard, FileText, DollarSign, Sparkles, Users,
  Link2, Send, Settings, Zap, Package, Clock, Shield, Brain, Link,
  TrendingUp,
} from 'lucide-react';

export const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',       path: '/',          icon: LayoutDashboard },
  { id: 'generate',   label: 'Generate',         path: '/generate',  icon: Zap },
  { id: 'templates',  label: 'Templates',        path: '/templates', icon: FileText },
  { id: 'products',   label: 'Products',         path: '/products',  icon: Package },
  { id: 'approvals',  label: 'Approvals',        path: '/approvals', icon: Clock },
  { id: 'guardrails', label: 'Guardrails',       path: '/guardrails', icon: Shield, adminOnly: true },
  { id: 'negotiations', label: 'Negotiations',   path: '/negotiations', icon: Brain },
  { id: 'share-links',  label: 'Share Links',    path: '/share-links',  icon: Link },
  { id: 'pricing',    label: 'Pricing & Rules',  path: '/pricing',   icon: DollarSign, adminOnly: true },
  { id: 'prompts',    label: 'AI Prompts',       path: '/prompts',   icon: Sparkles, adminOnly: true },
  { id: 'crm',        label: 'CRM Integrations', path: '/crm',       icon: Link2 },
  { id: 'documents',  label: 'Documents',        path: '/documents', icon: Send },
  { id: 'users',      label: 'Users & Access',   path: '/users',     icon: Users },
  { id: 'settings',   label: 'Settings',         path: '/settings',  icon: Settings, adminOnly: true },
];

export const PAGE_META = {
  '/':          { title: 'Dashboard',          subtitle: 'Overview of your quote generation pipeline' },
  '/generate':  { title: 'Generate Proposal',   subtitle: 'Select a CRM deal and generate a quote or proposal' },
  '/templates': { title: 'Template Management', subtitle: 'Manage proposal and quote templates' },
  '/products':  { title: 'Product Catalog',      subtitle: 'Manage SKUs and control which products buyer agents can see' },
  '/approvals': { title: 'Approval Queue',        subtitle: 'Review deals routed for human sign-off' },
  '/guardrails':{ title: 'Guardrail Policy',      subtitle: 'Deterministic rules every offer must pass' },
  '/negotiations':{title: 'Negotiations',         subtitle: 'AI retry chains and model behavior' },
  '/share-links':{ title: 'Buyer Share Links',    subtitle: 'Generate public quote-room URLs to send to buyers' },
  '/pricing':   { title: 'Pricing & Rules',     subtitle: 'Configure pricing rules and discounts' },
  '/prompts':   { title: 'AI Prompt Studio',    subtitle: 'Manage AI prompt templates and configurations' },
  '/crm':       { title: 'CRM Integrations',    subtitle: 'Manage CRM platform connections' },
  '/documents': { title: 'Documents & Delivery', subtitle: 'Track generated documents and delivery status' },
  '/users':     { title: 'Users & Access',      subtitle: 'Manage users and role-based access' },
  '/settings':  { title: 'Settings',            subtitle: 'System configuration and preferences' },
  '/insights/setup':  { title: 'Deal Insights — Setup',  subtitle: 'Map your Salesforce schema to the prediction model' },
  '/insights/models': { title: 'Deal Insights — Models', subtitle: 'Trained win-probability classifiers + metrics' },
  '/icp':             { title: 'ICP Builder',             subtitle: 'Define your ideal customer profile and score open deals against it' },
};
