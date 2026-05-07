import { useState } from 'react';
import {
  Plus, Database, RefreshCw, Settings, Link2, ChevronRight, X, ExternalLink,
  CheckCircle, AlertCircle, Loader2, Eye, EyeOff, Globe, Server, TestTube,
  Key, Lock, ArrowRight, Trash2, ChevronDown, Plug, Wifi, WifiOff,
  Tag, Users, DollarSign, Package, Mail, Clock, Layers,
} from 'lucide-react';
import { StatusBadge } from '@/components/ui';
import clsx from 'clsx';

// ─── CRM Platform Definitions ────────────────────────────────
const CRM_PLATFORMS = {
  salesforce: {
    id: 'salesforce',
    name: 'Salesforce',
    logo: '☁️',
    color: '#0176d3',
    bgColor: 'bg-blue-50',
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
    color: '#6366f1',
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
  { crm: 'Region', maps: 'compliance_region', icon: Globe },
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
    setLoading(true);
    // Simulate OAuth redirect + callback
    await new Promise((r) => setTimeout(r, 2000));
    setLoading(false);
    setStep(3);
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
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-[560px] max-h-[90vh] overflow-y-auto animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className={clsx('w-11 h-11 rounded-xl flex items-center justify-center text-xl', config.bgColor)}>
              {config.logo}
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">Connect {config.name}</h3>
              <p className="text-sm text-gray-500">{config.description}</p>
            </div>
          </div>
          <button onClick={onClose} className="icon-btn"><X size={18} className="text-gray-400" /></button>
        </div>

        {/* Steps indicator */}
        <div className="px-6 py-4 bg-gray-50 border-b border-gray-100">
          <div className="flex items-center gap-3">
            {[
              { num: 1, label: 'Environment' },
              { num: 2, label: 'Authenticate' },
              { num: 3, label: 'Connected' },
            ].map((s, i) => (
              <div key={s.num} className="flex items-center gap-3 flex-1">
                <div className={clsx(
                  'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors',
                  step >= s.num ? 'bg-brand-500 text-white' : 'bg-gray-200 text-gray-500'
                )}>
                  {step > s.num ? <CheckCircle size={16} /> : s.num}
                </div>
                <span className={clsx('text-sm font-medium', step >= s.num ? 'text-gray-900' : 'text-gray-400')}>
                  {s.label}
                </span>
                {i < 2 && <div className={clsx('flex-1 h-px', step > s.num ? 'bg-brand-300' : 'bg-gray-200')} />}
              </div>
            ))}
          </div>
        </div>

        <div className="p-6">
          {/* ─── Step 1: Choose Environment ─── */}
          {step === 1 && (
            <div className="space-y-5 animate-fade-in">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Connection Name</label>
                <input
                  value={connectionName}
                  onChange={(e) => setConnectionName(e.target.value)}
                  placeholder={`${config.name} Production`}
                  className="input-field w-full"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Select Environment</label>
                <div className="space-y-2.5">
                  {config.environments.map((e) => (
                    <label
                      key={e.id}
                      className={clsx(
                        'flex items-center gap-3.5 p-4 rounded-xl border-2 cursor-pointer transition-all',
                        env === e.id
                          ? 'border-brand-500 bg-brand-50/50'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      )}
                    >
                      <input
                        type="radio"
                        name="env"
                        value={e.id}
                        checked={env === e.id}
                        onChange={() => setEnv(e.id)}
                        className="w-4 h-4 text-brand-500 border-gray-300 focus:ring-brand-500"
                      />
                      <div className={clsx(
                        'w-9 h-9 rounded-lg flex items-center justify-center',
                        e.id === 'production' ? 'bg-green-100' : e.id === 'sandbox' ? 'bg-amber-100' : 'bg-blue-100'
                      )}>
                        {e.id === 'production' ? <Server size={18} className="text-green-600" /> :
                         e.id === 'sandbox' ? <TestTube size={18} className="text-amber-600" /> :
                         <Globe size={18} className="text-blue-600" />}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-gray-900">{e.label}</div>
                        {e.url && <div className="text-xs text-gray-400 font-mono">{e.url}</div>}
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
            <div className="space-y-5 animate-fade-in">
              <div className="p-5 rounded-xl bg-blue-50 border border-blue-200">
                <div className="flex items-start gap-3">
                  <Lock size={20} className="text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-blue-900 mb-1">OAuth 2.0 Authentication</h4>
                    <p className="text-xs text-blue-700 leading-relaxed">
                      You'll be redirected to {config.name}'s login page ({selectedEnv.url}).
                      After signing in, {config.name} will share access to your CRM data with QuoteForge.
                      We only request read access to Deals, Accounts, Contacts, and Products.
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-gray-200 bg-gray-50">
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Permissions Requested</div>
                <div className="space-y-2">
                  {config.fields.map((f) => (
                    <div key={f} className="flex items-center gap-2.5 text-sm text-gray-700">
                      <CheckCircle size={15} className="text-green-500" />
                      <span>Read {f} data</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2.5 text-sm text-gray-700">
                    <CheckCircle size={15} className="text-green-500" />
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
            <div className="space-y-5 animate-fade-in">
              {/* Auth method selector */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Authentication Method</label>
                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    { id: 'client_credentials', label: 'Client ID & Secret', icon: Key },
                    { id: 'api_key', label: 'API Key', icon: Lock },
                  ].map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setAuthMethod(m.id)}
                      className={clsx(
                        'flex items-center gap-2.5 p-3.5 rounded-xl border-2 text-sm font-medium transition-all',
                        authMethod === m.id
                          ? 'border-brand-500 bg-brand-50 text-brand-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
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
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">API Base URL</label>
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
                    <label className="block text-sm font-semibold text-gray-700 mb-1.5">Client ID</label>
                    <input
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder="your-client-id-here"
                      className="input-field w-full font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1.5">Client Secret</label>
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
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      >
                        {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">API Key</label>
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
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              )}

              <div className="p-4 rounded-xl bg-amber-50 border border-amber-200">
                <div className="flex items-start gap-2.5">
                  <AlertCircle size={16} className="text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-700 leading-relaxed">
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
            <div className="text-center py-4 animate-fade-in">
              <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-5">
                <CheckCircle size={32} className="text-green-500" />
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-2">Connected Successfully!</h3>
              <p className="text-sm text-gray-500 mb-6 max-w-xs mx-auto">
                {config.name} ({selectedEnv.label}) is now connected to QuoteForge.
                CRM data will be synced automatically.
              </p>
              <div className="p-4 rounded-xl bg-gray-50 border border-gray-200 text-left mb-6">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-gray-500">Platform:</span><br /><span className="font-semibold text-gray-900">{config.name}</span></div>
                  <div><span className="text-gray-500">Environment:</span><br /><span className="font-semibold text-gray-900">{selectedEnv.label}</span></div>
                  <div><span className="text-gray-500">Auth:</span><br /><span className="font-semibold text-gray-900">{config.authType === 'oauth' ? 'OAuth 2.0' : 'API Credentials'}</span></div>
                  <div><span className="text-gray-500">Status:</span><br /><StatusBadge status="connected" /></div>
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

  const handleSync = async () => {
    setSyncing(true);
    await new Promise((r) => setTimeout(r, 1500));
    setSyncing(false);
    onSync?.(connection.id);
  };

  return (
    <div className={clsx(
      'card p-6 animate-slide-up',
      connection.status === 'disconnected' && 'border-red-200'
    )}>
      {/* Header */}
      <div className="flex justify-between items-start mb-5">
        <div className="flex items-center gap-3">
          <div className={clsx('w-12 h-12 rounded-2xl flex items-center justify-center text-2xl', config.bgColor)}>
            {config.logo}
          </div>
          <div>
            <h4 className="text-base font-bold text-gray-900">{connection.connectionName}</h4>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm text-gray-500">{config.name}</span>
              <span className="text-gray-300">•</span>
              <span className={clsx(
                'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md',
                connection.environment === 'production' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
              )}>
                {connection.environment === 'production' ? <Server size={10} /> : <TestTube size={10} />}
                {envLabel}
              </span>
            </div>
          </div>
        </div>
        <StatusBadge status={connection.status} />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3.5 rounded-xl bg-gray-50">
          <div className="text-xl font-bold text-gray-900">{connection.deals.toLocaleString()}</div>
          <div className="text-xs text-gray-500">Active Deals</div>
        </div>
        <div className="p-3.5 rounded-xl bg-gray-50">
          <div className={clsx('text-xl font-bold', connection.health > 0 ? 'text-emerald-600' : 'text-red-600')}>
            {connection.health}%
          </div>
          <div className="text-xs text-gray-500">API Health</div>
        </div>
      </div>

      {/* Health bar */}
      {connection.status === 'connected' && (
        <div className="mb-4">
          <div className="h-1.5 rounded-full bg-gray-100">
            <div
              className={clsx(
                'h-full rounded-full transition-all duration-1000',
                connection.health > 99 ? 'bg-emerald-500' : connection.health > 90 ? 'bg-amber-500' : 'bg-red-500'
              )}
              style={{ width: `${connection.health}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <span className="text-xs text-gray-400">Last sync: {connection.lastSync}</span>
        <span className="text-xs text-gray-400">Connected: {connection.connectedAt}</span>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        {connection.status === 'connected' ? (
          <>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn-secondary flex-1 justify-center text-sm"
            >
              {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
            <button className="icon-btn"><Settings size={14} className="text-gray-500" /></button>
            <button
              onClick={() => onDisconnect(connection.id)}
              className="icon-btn hover:!border-red-300 hover:!bg-red-50"
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

  const handleConnect = (newConnection) => {
    setConnections((prev) => [...prev, newConnection]);
  };

  const handleDisconnect = (id) => {
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status: 'disconnected', health: 0 } : c))
    );
  };

  const handleSync = (id) => {
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
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-100 text-xs font-semibold text-green-700">
            <Wifi size={12} />
            {connections.filter((c) => c.status === 'connected').length} Connected
          </span>
          {connections.some((c) => c.status === 'disconnected') && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-100 text-xs font-semibold text-red-700">
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
              <div className="absolute right-0 top-full mt-2 w-[280px] bg-white rounded-xl border border-gray-200 shadow-xl py-2 z-50 animate-fade-in">
                <div className="px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Choose Platform
                </div>
                {Object.values(CRM_PLATFORMS).map((platform) => (
                  <button
                    key={platform.id}
                    onClick={() => openConnector(platform.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center text-lg', platform.bgColor)}>
                      {platform.logo}
                    </div>
                    <div className="text-left">
                      <div className="text-sm font-semibold text-gray-900">{platform.name}</div>
                      <div className="text-xs text-gray-400">
                        {platform.authType === 'oauth' ? 'OAuth 2.0' : 'API Key / Client Credentials'}
                      </div>
                    </div>
                    <ArrowRight size={14} className="text-gray-300 ml-auto" />
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ─── Connection Cards ─── */}
      {connections.length === 0 ? (
        <div className="card p-12 text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Database size={32} className="text-gray-400" />
          </div>
          <h3 className="text-lg font-bold text-gray-900 mb-2">No CRM Connected</h3>
          <p className="text-sm text-gray-500 mb-6 max-w-sm mx-auto">
            Connect your CRM platform to start generating AI-powered quotes and proposals from your deal data.
          </p>
          <button onClick={() => setShowPlatformPicker(true)} className="btn-primary mx-auto">
            <Plus size={18} /> Add Your First Connection
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-5 mb-8">
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
            className="card border-dashed border-2 border-gray-200 hover:border-brand-300 hover:bg-brand-50/30 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all min-h-[260px] group"
          >
            <div className="w-12 h-12 rounded-xl bg-gray-100 group-hover:bg-brand-100 flex items-center justify-center transition-colors">
              <Plus size={24} className="text-gray-400 group-hover:text-brand-500 transition-colors" />
            </div>
            <span className="text-sm font-medium text-gray-500 group-hover:text-brand-600 transition-colors">
              Add Another CRM
            </span>
          </button>
        </div>
      )}

      {/* ─── Field Mapping ─── */}
      <div className="card p-7">
        <h3 className="text-base font-bold text-gray-900 mb-1.5">CRM Field Mapping</h3>
        <p className="text-sm text-gray-500 mb-5">
          Maps CRM data fields to the QuoteForge generation schema. Works across all connected platforms.
        </p>
        <div className="grid grid-cols-4 gap-4">
          {FIELD_MAPPINGS.map((field) => {
            const Icon = field.icon;
            return (
              <div key={field.crm} className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 hover:border-brand-200 transition-colors">
                <div className="flex items-center gap-2 mb-2.5">
                  <Icon size={16} className="text-brand-500" />
                  <span className="text-sm font-semibold text-gray-900">{field.crm}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <ChevronRight size={14} className="text-gray-400" />
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
