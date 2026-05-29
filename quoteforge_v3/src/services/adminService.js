import api from './api';

/**
 * Platform super-admin API client.
 * Backend endpoints are gated by SUPER_ADMIN_EMAILS env var — all three
 * 403 cleanly if the calling user isn't on the allowlist.
 */
const adminService = {
  stats:      ()      => api.get('/admin/stats'),
  tenants:    ()      => api.get('/admin/tenants'),
  tenant:     (id)    => api.get(`/admin/tenants/${id}`),
};

export default adminService;
