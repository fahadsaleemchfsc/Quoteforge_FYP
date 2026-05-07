import { useEffect, useState } from 'react';
import { PlayCircle, Brain, TrendingUp, Clock, Settings as SettingsIcon } from 'lucide-react';
import { Panel, Pill, Mono, MetricCard } from '@/components/ui';
import api from '@/services/api';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

/*
 * Deal Insights — models dashboard.
 *
 *   - Top row: active model card + training-status card + retrain button
 *   - Feature-importance bar chart (top 10 from active model)
 *   - History table of all trained versions
 */

const POLL_MS = 2000;

function formatPct(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default function InsightsModels() {
  const [models, setModels] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const navigate = useNavigate();

  async function refresh() {
    try {
      const [mRes, sRes] = await Promise.all([
        api.get('/insights/models'),
        api.get('/insights/status'),
      ]);
      setModels(mRes.data);
      setStatus(sRes.data);
    } catch (e) {
      // Soft-fail: dashboards shouldn't throw toasts on every refresh tick.
    }
  }

  useEffect(() => {
    (async () => { await refresh(); setLoading(false); })();
  }, []);

  // Poll while a job is running.
  useEffect(() => {
    const state = status?.latest_job?.state;
    if (state !== 'running') return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [status?.latest_job?.state]);

  async function triggerTrain() {
    setTraining(true);
    try {
      await api.post('/insights/train');
      toast.success('Training started');
      refresh();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Failed to start training';
      if (e.response?.status === 400 && /mapping/i.test(msg)) {
        toast.error('Complete the setup wizard first');
        navigate('/insights/setup');
      } else {
        toast.error(msg);
      }
    } finally {
      setTraining(false);
    }
  }

  if (loading) {
    return (
      <div className="page-enter">
        <Panel padded>
          <div className="py-8 text-center text-text-muted">loading…</div>
        </Panel>
      </div>
    );
  }

  const active = status?.active_model;
  const job = status?.latest_job;

  return (
    <div className="page-enter space-y-4">
      {/* ── Top row: quick stats + train button ────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded flex items-center justify-center"
            style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
          >
            <Brain size={18} />
          </div>
          <div>
            <div className="text-[14px] font-semibold text-text-primary">Deal Insights</div>
            <div className="text-[12px] text-text-muted">
              Per-tenant win-probability classifier (LightGBM, self-hosted)
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => navigate('/insights/setup')}>
            <SettingsIcon size={13} /> Mapping
          </button>
          <button
            className="btn-primary"
            onClick={triggerTrain}
            disabled={training || job?.state === 'running'}
          >
            <PlayCircle size={13} />
            {job?.state === 'running'
              ? 'training…'
              : (training ? 'starting…' : 'Retrain now')}
          </button>
        </div>
      </div>

      {/* ── Status strip ──────────────────────────────────────── */}
      {job?.state === 'running' && (
        <Panel padded>
          <div className="flex items-center gap-3">
            <Clock size={16} className="animate-pulse" style={{ color: 'var(--accent)' }} />
            <div className="text-[12.5px]">
              <span className="font-semibold">Training in progress:</span>{' '}
              <span className="text-text-muted">{job.message}</span>
            </div>
          </div>
        </Panel>
      )}
      {job?.state === 'error' && (
        <Panel padded>
          <div style={{ color: 'var(--danger)' }} className="text-[12.5px]">
            <strong>Training failed:</strong> {job.message}
          </div>
        </Panel>
      )}

      {/* ── Active model metrics ──────────────────────────────── */}
      {!active ? (
        <Panel padded>
          <div className="py-6 text-center text-text-muted text-[12.5px]">
            No trained model yet.{' '}
            <button className="link-btn" onClick={triggerTrain}>Train the first model →</button>
          </div>
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-3">
            <MetricCard
              label="Active version"
              value={`v${active.version}`}
              hint={`trained ${formatDate(active.trained_at)}`}
            />
            <MetricCard
              label="Accuracy"
              value={formatPct(active.accuracy)}
              hint="held-out 20% split"
            />
            <MetricCard
              label="ROC AUC"
              value={Number(active.auc).toFixed(3)}
              hint="1.0 = perfect"
            />
            <MetricCard
              label="Training rows"
              value={active.training_rows.toLocaleString()}
              hint={`${active.closed_won_count} won · ${active.closed_lost_count} lost`}
            />
          </div>

          {/* Feature importance */}
          <Panel padded>
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={14} style={{ color: 'var(--accent)' }} />
              <div className="text-[13px] font-semibold text-text-primary">
                Top 10 features driving predictions
              </div>
            </div>
            <FeatureImportanceChart items={active.feature_importances.slice(0, 10)} />
          </Panel>
        </>
      )}

      {/* ── History table ─────────────────────────────────────── */}
      <Panel padded={false}>
        <div className="px-4 pt-3 text-[13px] font-semibold text-text-primary">
          Training history
        </div>
        <table className="w-full mt-2">
          <thead>
            <tr>
              <th className="table-header">Version</th>
              <th className="table-header">Trained</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Rows</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Won / Lost</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Accuracy</th>
              <th className="table-header" style={{ textAlign: 'right' }}>AUC</th>
              <th className="table-header" style={{ textAlign: 'right' }}>Duration</th>
              <th className="table-header">Status</th>
            </tr>
          </thead>
          <tbody>
            {models.length === 0 ? (
              <tr><td colSpan={8} className="table-cell text-center text-text-muted py-8">
                no versions yet
              </td></tr>
            ) : models.map((m) => (
              <tr key={m.id} className="table-row">
                <td className="table-cell"><Mono className="font-medium">v{m.version}</Mono></td>
                <td className="table-cell text-text-secondary">{formatDate(m.trained_at)}</td>
                <td className="table-cell table-num">{m.training_rows.toLocaleString()}</td>
                <td className="table-cell table-num text-text-secondary">
                  {m.closed_won_count} / {m.closed_lost_count}
                </td>
                <td className="table-cell table-num">{formatPct(m.accuracy)}</td>
                <td className="table-cell table-num">{Number(m.auc).toFixed(3)}</td>
                <td className="table-cell table-num text-text-secondary">
                  {m.training_duration_seconds.toFixed(1)}s
                </td>
                <td className="table-cell">
                  {m.is_active
                    ? <Pill variant="success">active</Pill>
                    : <Pill variant="neutral">archived</Pill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

function FeatureImportanceChart({ items }) {
  if (!items || items.length === 0) return null;
  const max = Math.max(...items.map((it) => it.importance || 0), 0.001);
  return (
    <div className="space-y-1.5">
      {items.map((it) => (
        <div key={it.feature} className="flex items-center gap-3">
          <div className="w-[220px] text-[11.5px] font-mono text-text-secondary truncate">
            {it.feature}
          </div>
          <div className="flex-grow h-[14px] rounded-sm overflow-hidden"
               style={{ background: 'var(--surface-raised)' }}>
            <div
              className="h-full"
              style={{
                width: `${(it.importance / max) * 100}%`,
                background: 'var(--accent)',
              }}
            />
          </div>
          <div className="w-[56px] text-right text-[11.5px] font-mono text-text-primary">
            {(it.importance * 100).toFixed(1)}%
          </div>
        </div>
      ))}
    </div>
  );
}
