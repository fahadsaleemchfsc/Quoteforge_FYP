import api from './api';

// ─── AI Prompt Service ──────────────────────────────────────────────
export const promptService = {
  getAll:     (params)       => api.get('/prompts', { params }),
  getById:    (id)           => api.get(`/prompts/${id}`),
  create:     (data)         => api.post('/prompts', data),
  update:     (id, data)     => api.put(`/prompts/${id}`, data),
  delete:     (id)           => api.delete(`/prompts/${id}`),
  test:       (id, context)  => api.post(`/prompts/${id}/test`, context),
  activate:   (id)           => api.patch(`/prompts/${id}/activate`),
};

// ─── Pricing & Rules Service ────────────────────────────────────────
export const pricingService = {
  getRules:      (params)     => api.get('/pricing/rules', { params }),
  createRule:    (data)       => api.post('/pricing/rules', data),
  updateRule:    (id, data)   => api.put(`/pricing/rules/${id}`, data),
  deleteRule:    (id)         => api.delete(`/pricing/rules/${id}`),
  getCompliance: ()           => api.get('/pricing/compliance'),
};

// ─── Auth Service ───────────────────────────────────────────────────
export const authService = {
  login:        (creds)  => api.post('/auth/login', creds),
  logout:       ()       => api.post('/auth/logout'),
  me:           ()       => api.get('/auth/me'),
  refreshToken: ()       => api.post('/auth/refresh'),
};

// ─── User Management Service ────────────────────────────────────────
export const userService = {
  getAll:     (params)     => api.get('/users', { params }),
  getById:    (id)         => api.get(`/users/${id}`),
  invite:     (data)       => api.post('/users/invite', data),
  update:     (id, data)   => api.put(`/users/${id}`, data),
  deactivate: (id)         => api.patch(`/users/${id}/deactivate`),
  delete:     (id)         => api.delete(`/users/${id}`),
};

// ─── Settings Service ───────────────────────────────────────────────
export const settingsService = {
  get:    ()       => api.get('/settings'),
  update: (data)   => api.put('/settings', data),
};
