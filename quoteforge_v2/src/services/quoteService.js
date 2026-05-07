import api from './api';

/**
 * Quote & Proposal Generation API
 * Handles the end-to-end generation workflow.
 */
const quoteService = {
  /** Trigger quote generation from CRM deal data */
  generate:       (dealData)  => api.post('/quotes/generate', dealData),

  /** Get generation status by job ID */
  getStatus:      (jobId)     => api.get(`/quotes/status/${jobId}`),

  /** List all generated documents */
  listDocuments:  (params)    => api.get('/quotes/documents', { params }),

  /** Download a generated document */
  download:       (docId)     => api.get(`/quotes/documents/${docId}/download`, { responseType: 'blob' }),

  /** Re-send a document via email/CRM */
  resend:         (docId)     => api.post(`/quotes/documents/${docId}/resend`),

  /** Get dashboard metrics */
  getMetrics:     (params)    => api.get('/quotes/metrics', { params }),

  /** Get generation history chart data */
  getChartData:   (params)    => api.get('/quotes/chart', { params }),

  /** Get recent activity feed */
  getActivity:    (params)    => api.get('/quotes/activity', { params }),
};

export default quoteService;
