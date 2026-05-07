import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import { ThemeProvider } from './context/ThemeContext';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <App />
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 3000,
            style: {
              borderRadius: '4px',
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              fontSize: '13px',
            },
          }}
        />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
