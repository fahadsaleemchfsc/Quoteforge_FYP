import api from './api';

/**
 * CRM Integration API
 * Manages connections to Salesforce, HubSpot, etc.
 */
const crmService = {
  /** List all CRM connections */
  getConnections:   ()           => api.get('/crm/connections'),

  /** Initiate OAuth flow for a new CRM connection */
  connect:          (platform)   => api.post('/crm/connect', { platform }),

  /** Disconnect a CRM connection */
  disconnect:       (connId)     => api.delete(`/crm/connections/${connId}`),

  /** Trigger a manual sync */
  sync:             (connId)     => api.post(`/crm/connections/${connId}/sync`),

  /** Get connection health & status */
  getHealth:        (connId)     => api.get(`/crm/connections/${connId}/health`),

  /** Get field mappings */
  getFieldMappings: (connId)     => api.get(`/crm/connections/${connId}/mappings`),

  /** Update field mappings */
  updateMappings:   (connId, m)  => api.put(`/crm/connections/${connId}/mappings`, m),

  /** Fetch deals from CRM for testing */
  fetchDeals:       (connId, p)  => api.get(`/crm/connections/${connId}/deals`, { params: p }),
};

export default crmService;
