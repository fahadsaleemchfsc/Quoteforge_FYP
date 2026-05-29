import api from './api';

/**
 * Template Management API
 * Endpoints for managing quote/proposal templates.
 */
const templateService = {
  getAll:    (params)      => api.get('/templates', { params }),
  getById:   (id)          => api.get(`/templates/${id}`),
  create:    (data)        => api.post('/templates', data),
  update:    (id, data)    => api.put(`/templates/${id}`, data),
  delete:    (id)          => api.delete(`/templates/${id}`),
  preview:   (id)          => api.get(`/templates/${id}/preview`),
  duplicate: (id)          => api.post(`/templates/${id}/duplicate`),
  activate:  (id)          => api.patch(`/templates/${id}/activate`),
  archive:   (id)          => api.patch(`/templates/${id}/archive`),

  // Master HTML template — single per tenant, drives every PDF render.
  getMaster: ()            => api.get('/templates/master'),
  putMaster: (html_body)   => api.put('/templates/master', { html_body }),
};

export default templateService;
