import {
  LayoutDashboard, FileText, DollarSign, Sparkles, Users,
  Link2, Send, Settings,
} from 'lucide-react';

export const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',       path: '/',          icon: LayoutDashboard },
  { id: 'templates',  label: 'Templates',        path: '/templates', icon: FileText },
  { id: 'pricing',    label: 'Pricing & Rules',  path: '/pricing',   icon: DollarSign },
  { id: 'prompts',    label: 'AI Prompts',       path: '/prompts',   icon: Sparkles },
  { id: 'crm',        label: 'CRM Integrations', path: '/crm',       icon: Link2 },
  { id: 'documents',  label: 'Documents',        path: '/documents', icon: Send },
  { id: 'users',      label: 'Users & Access',   path: '/users',     icon: Users },
  { id: 'settings',   label: 'Settings',         path: '/settings',  icon: Settings },
];

export const PAGE_META = {
  '/':          { title: 'Dashboard',          subtitle: 'Overview of your quote generation pipeline' },
  '/templates': { title: 'Template Management', subtitle: 'Manage proposal and quote templates' },
  '/pricing':   { title: 'Pricing & Rules',     subtitle: 'Configure pricing rules, discounts, and compliance' },
  '/prompts':   { title: 'AI Prompt Studio',    subtitle: 'Manage AI prompt templates and configurations' },
  '/crm':       { title: 'CRM Integrations',    subtitle: 'Manage CRM platform connections' },
  '/documents': { title: 'Documents & Delivery', subtitle: 'Track generated documents and delivery status' },
  '/users':     { title: 'Users & Access',      subtitle: 'Manage users and role-based access' },
  '/settings':  { title: 'Settings',            subtitle: 'System configuration and preferences' },
};
