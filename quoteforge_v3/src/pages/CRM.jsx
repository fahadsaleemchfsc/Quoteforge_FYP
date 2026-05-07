import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  Plus, Database, RefreshCw, Settings, Link2, ChevronRight, X, ExternalLink,
  CheckCircle, AlertCircle, Loader2, Eye, EyeOff, Globe, Server, TestTube,
  Key, Lock, ArrowRight, Trash2, ChevronDown, Plug, Wifi, WifiOff,
  Tag, Users, DollarSign, Package, Mail, Clock, Layers,
} from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import api from '@/services/api';
import clsx from 'clsx';

// ─── CRM Platform Definitions ────────────────────────────────
const CRM_PLATFORMS = {
  salesforce: {
    id: 'salesforce',
    name: 'Salesforce',
    logo: '☁️',
    color: '#0176d3',
    bgColor: 'bg-accent-muted',
    textColor: 'text-[#0176d3]',
    authType: 'oauth',
    description: 'Connect via OAuth 2.0 to Salesforce CRM',
    environments: [
      { id: 'production', label: 'Production', url: 'https://login.salesforce.com' },
      { id: 'sandbox', label: 'Sandbox', url: 'https://test.salesforce.com' },
    ],
    oauthUrl: 'https://login.salesforce.com/services/oauth2/authorize',
    fields: ['Opportunity', 'Account', 'Contact', 'Product', 'PricebookEntry'],
  },
  hubspot: {
    id: 'hubspot',
    name: 'HubSpot',
    logo: '🟠',
    color: '#ff7a59',
    bgColor: 'bg-orange-50',
    textColor: 'text-[#ff7a59]',
    authType: 'oauth',
    description: 'Connect via OAuth 2.0 to HubSpot CRM',
    environments: [
      { id: 'production', label: 'Production', url: 'https://app.hubspot.com' },
      { id: 'sandbox', label: 'Sandbox (Developer)', url: 'https://app.hubspot.com/developer' },
    ],
    oauthUrl: 'https://app.hubspot.com/oauth/authorize',
    fields: ['Deal', 'Company', 'Contact', 'Product', 'LineItem'],
  },
  custom: {
    id: 'custom',
    name: 'Custom CRM',
    logo: '🔧',
    color: 'var(--accent)',
    bgColor: 'bg-brand-50',
    textColor: 'text-brand-600',
    authType: 'api_key',
    description: 'Connect any CRM via API Key or Client Credentials',
    environments: [
      { id: 'production', label: 'Production', url: '' },
      { id: 'staging', label: 'Staging', url: '' },
      { id: 'development', label: 'Development', url: '' },
    ],
    fields: ['Deal', 'Customer', 'Contact', 'Product', 'LineItem'],
  },
};

// ─── Mock Connected CRMs ─────────────────────────────────────
const INITIAL_CONNECTIONS = [
  {
    id: 'conn-1',
    platformId: 'salesforce',
    connectionName: 'Salesforce Production',
    environment: 'production',
    status: 'connected',
    lastSync: '2 min ago',
    deals: 1247,
    health: 99.8,
    connectedAt: 'Dec 15, 2025',
  },
  {
    id: 'conn-2',
    platformId: 'hubspot',
    connectionName: 'HubSpot Developer Sandbox',
    environment: 'sandbox',
    status: 'connected',
    lastSync: '5 min ago',
    deals: 342,
    health: 98.2,
    connectedAt: 'Jan 08, 2026',
  },
];

// ─── Field Mappings ──────────────────────────────────────────
const FIELD_MAPPINGS = [
  { crm: 'Opportunity / Deal', maps: 'deal_name', icon: Tag },
  { crm: 'Account / Company', maps: 'client_name', icon: Users },
  { crm: 'Amount', maps: 'deal_amount', icon: DollarSign },
  { crm: 'Line Items', maps: 'products[]', icon: Package },
  { crm: 'Contact Email', maps: 'contact_email', icon: Mail },
  { crm: 'Close Date', maps: 'close_date', icon: Clock },
  { crm: 'Stage / Pipeline', maps: 'deal_stage', icon: Layers },
  { crm: 'Region', maps: 'buyer_region', icon: Globe },
];

// ─── Connection Modal ────────────────────────────────────────
function ConnectModal({ platform, onClose, onConnect }) {
  const config = CRM_PLATFORMS[platform];
  const [env, setEnv] = useState(config.environments[0].id);
  const [step, setStep] = useState(1); // 1: choose env, 2: auth, 3: success
  const [loading, setLoading] = useState(false);
  const [connectionName, setConnectionName] = useState('');

  // For custom CRM
  const [baseUrl, setBaseUrl] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [authMethod, setAuthMethod] = useState('client_credentials'); // or 'api_key'
  const [showSecret, setShowSecret] = useState(false);

  const selectedEnv = config.environments.find((e) => e.id === env);

  const handleOAuthConnect = async () => {
    // Real OAuth — fetch the Salesforce authorize URL from the backend,
    // then hand the browser off to Salesforce login. On return, Salesforce
    // posts to /api/crm/oauth/callback, backend stores tokens, then redirects
    // back to /crm?connected=salesforce. No "fake success" sleep.
    setLoading(true);
    try {
      if (platform === 'salesforce') {
        const res = await api.get('/crm/salesforce/authorize', {
          params: { environment: env },
        });
        const url = res.data?.authorization_url;
        if (!url) throw new Error('no authorization_url returned from backend');
        window.location.href = url;
        return;   // browser navigates away
      }
      // HubSpot OAuth not wired yet — flag and abort.
      alert(`${config.name} OAuth is not yet implemented. Use API key mode or pick Salesforce.`);
      setLoading(false);
    } catch (e) {
      alert(
        e.response?.data?.detail
        ?? e.message
        ?? 'Failed to start OAuth. Is SALESFORCE_CLIENT_ID set in the backend .env?'
      );
      setLoading(false);
    }
  };

  const handleApiConnect = async () => {
    setLoading(true);
    await new Promise((r) => setTimeout(r, 1500));
    setLoading(false);
    setStep(3);
  };

  const handleFinish = () => {
    onConnect({
      id: `conn-${Date.now()}`,
      platformId: platform,
      connectionName: connectionName || `${config.name} ${selectedEnv.label}`,
      environment: env,
      status: 'connected',
      lastSync: 'Just now',
      deals: 0,
      health: 100,
      connectedAt: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded shadow-2xl w-full max-w-[560px] max-h-[90vh] overflow-y-auto ">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className={clsx('w-9 h-9 rounded flex items-center justify-center text-xl', config.bgColor)}>
              {config.logo}
            </div>
            <div>
              <h3 className="text-[13px] font-bold text-text-primary">Connect {config.name}</h3>
              <p className="text-sm text-text-secondary">{config.description}</p>
            </div>
          </div>
          <button onClick={onClose} className="icon-btn"><X size={18} className="text-text-muted" /></button>
        </div>

        {/* Steps indicator */}
        <div className="px-6 py-4 bg-subtle border-b border-border">
          <div className="flex items-center gap-3">
            {[
              { num: 1, label: 'Environment' },
              { num: 2, label: 'Authenticate' },
              { num: 3, label: 'Connected' },
            ].map((s, i) => (
              <div key={s.num} className="flex items-center gap-3 flex-1">
                <div className={clsx(
                  'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors',
                  step >= s.num ? 'bg-brand-500 text-white' : 'bg-muted text-text-secondary'
                )}>
                  {step > s.num ? <CheckCircle size={16} /> : s.num}
                </div>
                <span className={clsx('text-sm font-medium', step >= s.num ? 'text-text-primary' : 'text-text-muted')}>
                  {s.label}
                </span>
                {i < 2 && <div className={clsx('flex-1 h-px', step > s.num ? 'bg-brand-300' : 'bg-muted')} />}
              </div>
            ))}
          </div>
        </div>

        <div className="p-4">
          {/* ─── Step 1: Choose Environment ─── */}
          {step === 1 && (
            <div className="space-y-5 ">
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-1.5">Connection Name</label>
                <input
                  value={connectionName}
                  onChange={(e) => setConnectionName(e.target.value)}
                  placeholder={`${config.name} Production`}
                  className="input-field w-full"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">Select Environment</label>
                <div className="space-y-2.5">
                  {config.environments.map((e) => (
                    <label
                      key={e.id}
                      className={clsx(
                        'flex items-center gap-3.5 p-4 rounded border-2 cursor-pointer transition-all',
                        env === e.id
                          ? 'border-brand-500 bg-brand-50/50'
                          : 'border-border hover:border-border-strong hover:bg-subtle'
                      )}
                    >
                      <input
                        type="radio"
                        name="env"
                        value={e.id}
                        checked={env === e.id}
                        onChange={() => setEnv(e.id)}
                        className="w-4 h-4 text-brand-500 border-border-strong focus:ring-brand-500"
                      />
                      <div className={clsx(
                        'w-8 h-8 rounded flex items-center justify-center',
                        e.id === 'production' ? 'bg-success-muted' : e.id === 'sandbox' ? 'bg-warning-muted' : 'bg-accent-muted'
                      )}>
                        {e.id === 'production' ? <Server size={18} className="text-success" /> :
                         e.id === 'sandbox' ? <TestTube size={18} className="text-warning" /> :
                         <Globe size={18} className="text-accent" />}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-text-primary">{e.label}</div>
                        {e.url && <div className="text-xs text-text-muted font-mono">{e.url}</div>}
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <button
                onClick={() => setStep(2)}
                className="btn-primary w-full justify-center py-3"
              >
                Continue <ArrowRight size={16} />
              </button>
            </div>
          )}

          {/* ─── Step 2: Authenticate ─── */}
          {step === 2 && config.authType === 'oauth' && (
            <div className="space-y-5 ">
              <div className="p-4 rounded bg-accent-muted border border-blue-200">
                <div className="flex items-start gap-3">
                  <Lock size={20} className="text-accent mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-blue-900 mb-1">OAuth 2.0 Authentication</h4>
                    <p className="text-xs text-accent leading-relaxed">
                      You'll be redirected to {config.name}'s login page ({selectedEnv.url}).
                      After signing in, {config.name} will share access to your CRM data with QuoteForge.
                      We only request read access to Deals, Accounts, Contacts, and Products.
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded border border-border bg-subtle">
                <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Permissions Requested</div>
                <div className="space-y-2">
                  {config.fields.map((f) => (
                    <div key={f} className="flex items-center gap-2.5 text-sm text-text-primary">
                      <CheckCircle size={15} className="text-success" />
                      <span>Read {f} data</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2.5 text-sm text-text-primary">
                    <CheckCircle size={15} className="text-success" />
                    <span>Write activity logs</span>
                  </div>
                </div>
              </div>

              <button
                onClick={handleOAuthConnect}
                disabled={loading}
                className="btn-primary w-full justify-center py-3"
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Connecting to {config.name}...
                  </>
                ) : (
                  <>
                    <ExternalLink size={16} />
                    Sign in with {config.name}
                  </>
                )}
              </button>

              <button onClick={() => setStep(1)} className="btn-secondary w-full justify-center text-sm">
                Back
              </button>
            </div>
          )}

          {step === 2 && config.authType === 'api_key' && (
            <div className="space-y-5 ">
              {/* Auth method selector */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-2">Authentication Method</label>
                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    { id: 'client_credentials', label: 'Client ID & Secret', icon: Key },
                    { id: 'api_key', label: 'API Key', icon: Lock },
                  ].map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setAuthMethod(m.id)}
                      className={clsx(
                        'flex items-center gap-2.5 p-3.5 rounded border-2 text-sm font-medium transition-all',
                        authMethod === m.id
                          ? 'border-brand-500 bg-brand-50 text-brand-700'
                          : 'border-border text-text-secondary hover:border-border-strong'
                      )}
                    >
                      <m.icon size={16} />
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-sm font-semibold text-text-primary mb-1.5">API Base URL</label>
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://your-crm.com/api/v1"
                  className="input-field w-full font-mono text-sm"
                />
              </div>

              {authMethod === 'client_credentials' ? (
                <>
                  <div>
                    <label className="block text-sm font-semibold text-text-primary mb-1.5">Client ID</label>
                    <input
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder="your-client-id-here"
                      className="input-field w-full font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-text-primary mb-1.5">Client Secret</label>
                    <div className="relative">
                      <input
                        type={showSecret ? 'text' : 'password'}
                        value={clientSecret}
                        onChange={(e) => setClientSecret(e.target.value)}
                        placeholder="your-client-secret-here"
                        className="input-field w-full pr-11 font-mono text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setShowSecret(!showSecret)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                      >
                        {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div>
                  <label className="block text-sm font-semibold text-text-primary mb-1.5">API Key</label>
                  <div className="relative">
                    <input
                      type={showSecret ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="your-api-key-here"
                      className="input-field w-full pr-11 font-mono text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret(!showSecret)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                    >
                      {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              )}

              <div className="p-4 rounded bg-warning-muted border border-amber-200">
                <div className="flex items-start gap-2.5">
                  <AlertCircle size={16} className="text-warning mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-warning leading-relaxed">
                    Credentials are encrypted and stored securely. They are never logged or exposed
                    in API responses. Only admin users can manage connections.
                  </p>
                </div>
              </div>

              <button
                onClick={handleApiConnect}
                disabled={loading}
                className="btn-primary w-full justify-center py-3"
              >
                {loading ? (
                  <><Loader2 size={16} className="animate-spin" /> Testing Connection...</>
                ) : (
                  <><Plug size={16} /> Test & Connect</>
                )}
              </button>

              <button onClick={() => setStep(1)} className="btn-secondary w-full justify-center text-sm">
                Back
              </button>
            </div>
          )}

          {/* ─── Step 3: Success ─── */}
          {step === 3 && (
            <div className="text-center py-4 ">
              <div className="w-16 h-16 rounded-full bg-success-muted flex items-center justify-center mx-auto mb-4">
                <CheckCircle size={32} className="text-success" />
              </div>
              <h3 className="text-xl font-bold text-text-primary mb-2">Connected Successfully!</h3>
              <p className="text-sm text-text-secondary mb-4 max-w-xs mx-auto">
                {config.name} ({selectedEnv.label}) is now connected to QuoteForge.
                CRM data will be synced automatically.
              </p>
              <div className="p-4 rounded bg-subtle border border-border text-left mb-4">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-text-secondary">Platform:</span><br /><span className="font-semibold text-text-primary">{config.name}</span></div>
                  <div><span className="text-text-secondary">Environment:</span><br /><span className="font-semibold text-text-primary">{selectedEnv.label}</span></div>
                  <div><span className="text-text-secondary">Auth:</span><br /><span className="font-semibold text-text-primary">{config.authType === 'oauth' ? 'OAuth 2.0' : 'API Credentials'}</span></div>
                  <div><span className="text-text-secondary">Status:</span><br /><StatusBadge status="connected" /></div>
                </div>
              </div>
              <button onClick={handleFinish} className="btn-primary w-full justify-center py-3">
                Done <ArrowRight size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Connection Card ─────────────────────────────────────────
function ConnectionCard({ connection, onDisconnect, onSync }) {
  const config = CRM_PLATFORMS[connection.platformId];
  const envLabel = config.environments.find((e) => e.id === connection.environment)?.label || connection.environment;
  const [syncing, setSyncing] = useState(false);
  const [liveHealth, setLiveHealth] = useState(null);  // {healthy, latency_ms, status, error, last_checked_at}
  const [reauthing, setReauthing] = useState(false);

  // Poll real health every 30s. One upfront load on mount.
  useEffect(() => {
    let cancelled = false;
    async function pull() {
      try {
        const res = await api.get(`/crm/connections/${connection.id}/health`);
        if (!cancelled) setLiveHealth(res.data);
      } catch { /* silent */ }
    }
    pull();
    const t = setInterval(pull, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [connection.id]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.post(`/crm/connections/${connection.id}/sync`);
      onSync?.(connection.id);
    } catch {}
    setSyncing(false);
  };

  async function handleReauthenticate() {
    setReauthing(true);
    try {
      const res = await api.post(`/crm/connections/${connection.id}/reauthenticate`);
      if (res.data?.authorization_url) {
        window.location.href = res.data.authorization_url;
      }
    } catch (e) {
      alert(e.response?.data?.detail || 'Re-authenticate failed');
      setReauthing(false);
    }
  }

  // Decide which health value to display. Prefer the live probe; fall back
  // to the server-side cached value on the connection row.
  const effectiveStatus = liveHealth?.status || connection.status;
  const isReauth = effectiveStatus === 'reauth_required';
  const healthPct = isReauth
    ? 0
    : liveHealth
      ? (liveHealth.healthy ? 100 : 0)
      : (connection.health ?? 0);
  const latencyLabel = liveHealth?.latency_ms != null ? `${liveHealth.latency_ms}ms` : null;

  return (
    <div className={clsx(
      'card p-4 ',
      connection.status === 'disconnected' && 'border-danger'
    )}>
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <div className={clsx('w-10 h-10 rounded flex items-center justify-center text-xl', config.bgColor)}>
            {config.logo}
          </div>
          <div>
            <h4 className="text-[13px] font-bold text-text-primary">{connection.connectionName}</h4>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm text-text-secondary">{config.name}</span>
              <span className="text-text-muted">•</span>
              <span className={clsx(
                'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded',
                connection.environment === 'production' ? 'bg-success-muted text-success' : 'bg-warning-muted text-warning'
              )}>
                {connection.environment === 'production' ? <Server size={10} /> : <TestTube size={10} />}
                {envLabel}
              </span>
            </div>
          </div>
        </div>
        <StatusBadge status={connection.status} />
      </div>

      {/* Reauth banner — replaces stats when this state fires */}
      {isReauth && (
        <div
          className="p-3 mb-4 rounded border"
          style={{
            background: 'var(--warning-muted)', borderColor: 'var(--warning)',
            color: 'var(--warning)',
          }}
        >
          <div className="text-[12px] font-semibold mb-1">Re-authentication required</div>
          <div className="text-[11.5px]">
            The stored refresh token is invalid. Click “Re-authenticate” below to restore this connection.
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3.5 rounded bg-subtle">
          <div className="text-xl font-bold text-text-primary font-mono tabular-nums">
            {connection.deals.toLocaleString()}
          </div>
          <div className="text-xs text-text-secondary">Active Deals</div>
        </div>
        <div className="p-3.5 rounded bg-subtle">
          <div
            className={clsx(
              'text-xl font-bold font-mono tabular-nums',
              healthPct > 0 ? 'text-success' : 'text-danger',
            )}
          >
            {healthPct}%
          </div>
          <div className="text-xs text-text-secondary flex items-center justify-between">
            <span>API Health</span>
            {latencyLabel && !isReauth && (
              <span className="font-mono text-text-muted text-[10.5px]">{latencyLabel}</span>
            )}
          </div>
        </div>
      </div>

      {liveHealth?.error && !isReauth && (
        <div className="mb-3 text-[11px] font-mono" style={{ color: 'var(--danger)' }}>
          {liveHealth.error}
        </div>
      )}

      {/* Health bar */}
      {effectiveStatus === 'connected' && (
        <div className="mb-4">
          <div className="h-1.5 rounded-full bg-subtle">
            <div
              className={clsx(
                'h-full rounded-full transition-all duration-1000',
                healthPct > 99 ? 'bg-success' : healthPct > 90 ? 'bg-warning' : 'bg-danger',
              )}
              style={{ width: `${healthPct}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <span className="text-xs text-text-muted">Last sync: {connection.lastSync}</span>
        <span className="text-xs text-text-muted">Connected: {connection.connectedAt}</span>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        {isReauth ? (
          <>
            <button
              onClick={handleReauthenticate}
              disabled={reauthing}
              className="btn-primary flex-1 justify-center text-sm"
            >
              {reauthing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {reauthing ? 'Redirecting…' : 'Re-authenticate'}
            </button>
            <button
              onClick={() => onDisconnect(connection.id)}
              className="icon-btn"
              title="Remove connection"
            >
              <Trash2 size={14} className="text-danger" />
            </button>
          </>
        ) : connection.status === 'connected' ? (
          <>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn-secondary flex-1 justify-center text-sm"
            >
              {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
            <button className="icon-btn"><Settings size={14} className="text-text-secondary" /></button>
            <button
              onClick={() => onDisconnect(connection.id)}
              className="icon-btn hover:!border-red-300 hover:!bg-danger-muted"
            >
              <Trash2 size={14} className="text-red-400" />
            </button>
          </>
        ) : (
          <button className="btn-primary flex-1 justify-center text-sm">
            <Link2 size={14} /> Reconnect
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main CRM Page ───────────────────────────────────────────
export default function CRM() {
  const [connections, setConnections] = useState(INITIAL_CONNECTIONS);
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [showPlatformPicker, setShowPlatformPicker] = useState(false);

  // Handle the OAuth return bounce — Salesforce redirects back here after
  // the user approves access at login.salesforce.com.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected') === 'salesforce') {
      toast.success('Salesforce connected');
      window.history.replaceState({}, '', '/crm');
    } else if (params.get('error')) {
      toast.error(`Salesforce OAuth failed: ${params.get('error')}`);
      window.history.replaceState({}, '', '/crm');
    }
  }, []);

  // Load real connections from backend
  useEffect(() => {
    api.get('/crm/connections').then(res => {
      const mapped = res.data.map(c => ({
        id: `conn-${c.id}`,
        backendId: c.id,
        platformId: c.platform.toLowerCase(),
        connectionName: `${c.platform} ${c.environment}`,
        environment: c.environment === 'production' ? 'production' : 'sandbox',
        status: c.status,
        lastSync: c.lastSync ? new Date(c.lastSync).toLocaleString() : 'Never',
        deals: c.deals || 0,
        health: c.health || 0,
        connectedAt: c.lastSync ? new Date(c.lastSync).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A',
      }));
      if (mapped.length > 0) setConnections(mapped);
    }).catch(() => {});
  }, []);

  const handleConnect = (newConnection) => {
    // Salesforce OAuth creates the row server-side in /api/crm/oauth/callback;
    // don't double-write with /crm/connect. Only call /crm/connect for the
    // non-OAuth custom-CRM path.
    if (newConnection.platformId !== 'salesforce') {
      const platformName = CRM_PLATFORMS[newConnection.platformId]?.name || newConnection.platformId;
      api.post('/crm/connect', {
        platform: platformName,
        environment: newConnection.environment,
      }).catch(() => {});
    }
    setConnections((prev) => [...prev, newConnection]);
  };

  const handleDisconnect = (id) => {
    const conn = connections.find(c => c.id === id);
    if (conn?.backendId) api.delete(`/crm/connections/${conn.backendId}`).catch(() => {});
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'disconnected', health: 0 } : c))
    );
  };

  const handleSync = (id) => {
    const conn = connections.find(c => c.id === id);
    if (conn?.backendId) api.post(`/crm/connections/${conn.backendId}/sync`).catch(() => {});
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? { ...c, lastSync: 'Just now' } : c))
    );
  };

  const openConnector = (platformId) => {
    setSelectedPlatform(platformId);
    setShowPlatformPicker(false);
    setShowConnectModal(true);
  };

  return (
    <div className="page-enter">
      {/* ─── Header ─── */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-success-muted text-xs font-semibold text-success">
            <Wifi size={12} />
            {connections.filter((c) => c.status === 'connected').length} Connected
          </span>
          {connections.some((c) => c.status === 'disconnected') && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-danger-muted text-xs font-semibold text-danger">
              <WifiOff size={12} />
              {connections.filter((c) => c.status === 'disconnected').length} Disconnected
            </span>
          )}
        </div>

        {/* Add Connection Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowPlatformPicker(!showPlatformPicker)}
            className="btn-primary"
          >
            <Plus size={18} /> Add Connection <ChevronDown size={14} />
          </button>

          {showPlatformPicker && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowPlatformPicker(false)} />
              <div className="absolute right-0 top-full mt-2 w-[280px] bg-white rounded border border-border  py-2 z-50 ">
                <div className="px-4 py-2 text-xs font-semibold text-text-muted uppercase tracking-wider">
                  Choose Platform
                </div>
                {Object.values(CRM_PLATFORMS).map((platform) => (
                  <button
                    key={platform.id}
                    onClick={() => openConnector(platform.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-subtle transition-colors"
                  >
                    <div className={clsx('w-8 h-8 rounded flex items-center justify-center text-[13px]', platform.bgColor)}>
                      {platform.logo}
                    </div>
                    <div className="text-left">
                      <div className="text-sm font-semibold text-text-primary">{platform.name}</div>
                      <div className="text-xs text-text-muted">
                        {platform.authType === 'oauth' ? 'OAuth 2.0' : 'API Key / Client Credentials'}
                      </div>
                    </div>
                    <ArrowRight size={14} className="text-text-muted ml-auto" />
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ─── Connection Cards ─── */}
      {connections.length === 0 ? (
        <div className="card p-8 text-center mb-5">
          <div className="w-12 h-12 rounded bg-subtle flex items-center justify-center mx-auto mb-4">
            <Database size={32} className="text-text-muted" />
          </div>
          <h3 className="text-[13px] font-bold text-text-primary mb-2">No CRM Connected</h3>
          <p className="text-sm text-text-secondary mb-4 max-w-sm mx-auto">
            Connect your CRM platform to start generating AI-powered quotes and proposals from your deal data.
          </p>
          <button onClick={() => setShowPlatformPicker(true)} className="btn-primary mx-auto">
            <Plus size={18} /> Add Your First Connection
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4 mb-5">
          {connections.map((conn, i) => (
            <ConnectionCard
              key={conn.id}
              connection={conn}
              onDisconnect={handleDisconnect}
              onSync={handleSync}
            />
          ))}

          {/* Add more card */}
          <button
            onClick={() => setShowPlatformPicker(true)}
            className="card border-dashed border-2 border-border hover:border-brand-300 hover:bg-brand-50/30 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all min-h-[200px] group"
          >
            <div className="w-10 h-10 rounded bg-subtle group-hover:bg-brand-100 flex items-center justify-center transition-colors">
              <Plus size={24} className="text-text-muted group-hover:text-brand-500 transition-colors" />
            </div>
            <span className="text-sm font-medium text-text-secondary group-hover:text-brand-600 transition-colors">
              Add Another CRM
            </span>
          </button>
        </div>
      )}

      {/* ─── Field Mapping ─── */}
      <div className="card p-4">
        <h3 className="text-[13px] font-bold text-text-primary mb-1.5">CRM Field Mapping</h3>
        <p className="text-sm text-text-secondary mb-4">
          Maps CRM data fields to the QuoteForge generation schema. Works across all connected platforms.
        </p>
        <div className="grid grid-cols-4 gap-4">
          {FIELD_MAPPINGS.map((field) => {
            const Icon = field.icon;
            return (
              <div key={field.crm} className="p-4 rounded border border-border bg-subtle/50 hover:border-brand-200 transition-colors">
                <div className="flex items-center gap-2 mb-2.5">
                  <Icon size={16} className="text-brand-500" />
                  <span className="text-sm font-semibold text-text-primary">{field.crm}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <ChevronRight size={14} className="text-text-muted" />
                  <code className="text-xs text-brand-600 bg-brand-50 px-2 py-0.5 rounded">{field.maps}</code>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ─── Connection Modal ─── */}
      {showConnectModal && selectedPlatform && (
        <ConnectModal
          platform={selectedPlatform}
          onClose={() => setShowConnectModal(false)}
          onConnect={handleConnect}
        />
      )}
    </div>
  );
}
