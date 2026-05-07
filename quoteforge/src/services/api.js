import axios from 'axios';

// ─── Axios Instance ───────────────────────────────────────────
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request Interceptor (attach auth token) ──────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor (handle errors globally) ────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

// ─── Auth Service ─────────────────────────────────────────────
export const authService = {
  login: (credentials) => api.post('/auth/login', credentials),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
};

// ─── Templates Service ────────────────────────────────────────
export const templateService = {
  getAll: (params) => api.get('/templates', { params }),
  getById: (id) => api.get(`/templates/${id}`),
  create: (data) => api.post('/templates', data),
  update: (id, data) => api.put(`/templates/${id}`, data),
  delete: (id) => api.delete(`/templates/${id}`),
  preview: (id) => api.get(`/templates/${id}/preview`),
};

// ─── Pricing Rules Service ────────────────────────────────────
export const pricingService = {
  getAll: (params) => api.get('/pricing-rules', { params }),
  getById: (id) => api.get(`/pricing-rules/${id}`),
  create: (data) => api.post('/pricing-rules', data),
  update: (id, data) => api.put(`/pricing-rules/${id}`, data),
  delete: (id) => api.delete(`/pricing-rules/${id}`),
};

// ─── AI Prompts Service ───────────────────────────────────────
export const promptService = {
  getAll: (params) => api.get('/prompts', { params }),
  getById: (id) => api.get(`/prompts/${id}`),
  create: (data) => api.post('/prompts', data),
  update: (id, data) => api.put(`/prompts/${id}`, data),
  delete: (id) => api.delete(`/prompts/${id}`),
  test: (id, testData) => api.post(`/prompts/${id}/test`, testData),
};

// ─── CRM Service ──────────────────────────────────────────────
export const crmService = {
  getConnections: () => api.get('/crm/connections'),
  connect: (platform, credentials) => api.post(`/crm/connect/${platform}`, credentials),
  disconnect: (id) => api.post(`/crm/disconnect/${id}`),
  sync: (id) => api.post(`/crm/sync/${id}`),
  getFieldMappings: (id) => api.get(`/crm/${id}/field-mappings`),
  updateFieldMappings: (id, mappings) => api.put(`/crm/${id}/field-mappings`, mappings),
};

// ─── Documents Service ────────────────────────────────────────
export const documentService = {
  getAll: (params) => api.get('/documents', { params }),
  getById: (id) => api.get(`/documents/${id}`),
  generate: (dealId, options) => api.post('/documents/generate', { dealId, ...options }),
  download: (id) => api.get(`/documents/${id}/download`, { responseType: 'blob' }),
  deliver: (id, deliveryOptions) => api.post(`/documents/${id}/deliver`, deliveryOptions),
};

// ─── Users Service ────────────────────────────────────────────
export const userService = {
  getAll: (params) => api.get('/users', { params }),
  getById: (id) => api.get(`/users/${id}`),
  invite: (data) => api.post('/users/invite', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  deactivate: (id) => api.post(`/users/${id}/deactivate`),
  updateRole: (id, role) => api.put(`/users/${id}/role`, { role }),
};

// ─── Settings Service ─────────────────────────────────────────
export const settingsService = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
};

// ─── Dashboard / Analytics Service ────────────────────────────
export const analyticsService = {
  getMetrics: (params) => api.get('/analytics/metrics', { params }),
  getChartData: (params) => api.get('/analytics/chart', { params }),
  getRecentActivity: (params) => api.get('/analytics/activity', { params }),
};
