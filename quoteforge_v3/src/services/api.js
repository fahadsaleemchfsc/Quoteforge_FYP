import axios from 'axios';

/**
 * Base API client configured for the QuoteForge backend.
 *
 * The Vite dev server proxies /api → http://localhost:8000
 * so we can use relative URLs during development.
 *
 * In production, set VITE_API_BASE_URL to the deployed backend URL.
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request interceptor: attach JWT token ──────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('qf_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response interceptor: handle auth errors ───────────────────────
let isRedirecting = false;
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isRedirecting) {
      // Only redirect once — prevents the shivering/loop
      isRedirecting = true;
      localStorage.removeItem('qf_token');
      localStorage.removeItem('qf_session');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
