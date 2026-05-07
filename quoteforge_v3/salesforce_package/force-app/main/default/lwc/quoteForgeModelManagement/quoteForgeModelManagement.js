/**
 * QuoteForge Model Management — Phase 4 admin tab.
 *
 *   - Active model card: version, tier, metrics, trained timestamp
 *   - Retrain button that tails the visible training_log.txt while running
 *   - History table: every trained version with metrics
 *   - Feature-importance horizontal bar chart (top 10 features from active model)
 *
 * The retrain flow polls /insights/status every 2s during training. Once
 * the job state flips to "done", we fetch /insights/models fresh to show
 * the new row at the top of the history table and pick up the updated
 * feature importances.
 */
import { LightningElement } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import listInsightsModels from '@salesforce/apex/QuoteForgeController.listInsightsModels';
import triggerRetrain from '@salesforce/apex/QuoteForgeController.triggerRetrain';
import getInsightsStatus from '@salesforce/apex/QuoteForgeController.getInsightsStatus';
import getTrainingLog from '@salesforce/apex/QuoteForgeController.getTrainingLog';

const STATUS_POLL_MS = 2000;
const LOG_TAIL_LINES = 80;

function pct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(1)}%`;
}
function fixed3(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(3) : '—';
}
function formatDate(iso) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    } catch (e) { return iso; }
}

export default class QuoteForgeModelManagement extends LightningElement {
    isLoading = true;
    errorMessage = '';

    models = [];        // version history
    jobState = null;    // "running" / "done" / "error" / null
    jobMessage = '';
    logLines = [];      // tail of training_log.txt
    isRetraining = false;

    _statusTimer = null;

    connectedCallback() { this.refreshAll(); }
    disconnectedCallback() { this._stopPolling(); }

    async refreshAll() {
        this.isLoading = true;
        this.errorMessage = '';
        try {
            const raw = await listInsightsModels();
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.models = parsed;
        } catch (e) {
            this.errorMessage = e?.message || 'Unable to load models.';
        } finally {
            this.isLoading = false;
        }
    }

    // ─── Derived ──────────────────────────────────────────────────

    get hasData() { return this.models.length > 0 && !this.errorMessage; }

    get activeModel() {
        return this.models.find((m) => m.is_active) || this.models[0];
    }

    get activeVersionDisplay() {
        return this.activeModel ? `v${this.activeModel.version}` : '—';
    }

    get tierDisplay() {
        const t = this.activeModel?.data_quality_tier;
        if (!t) return '—';
        return t.charAt(0).toUpperCase() + t.slice(1).replace('_', ' ');
    }

    get activeAccuracy() { return pct(this.activeModel?.accuracy); }
    get activeAUC() { return fixed3(this.activeModel?.auc); }
    get activePrecision() { return pct(this.activeModel?.precision_won); }
    get activeRecall() { return pct(this.activeModel?.recall_won); }
    get activeTrained() { return formatDate(this.activeModel?.trained_at); }

    get activeTrainingRows() {
        const n = this.activeModel?.training_rows;
        return Number.isFinite(n) ? n.toLocaleString() : '—';
    }

    get historyRows() {
        return this.models.map((m) => ({
            ...m,
            versionDisplay: `v${m.version}`,
            trainedDisplay: formatDate(m.trained_at),
            accuracyDisplay: pct(m.accuracy),
            aucDisplay: fixed3(m.auc),
            rowsDisplay: Number(m.training_rows).toLocaleString(),
            statusBadge: m.is_active ? 'ACTIVE' : 'archived',
            badgeClass: m.is_active ? 'qfmm-badge qfmm-badge-active' : 'qfmm-badge qfmm-badge-archived',
        }));
    }

    get topFeatures() {
        const features = this.activeModel?.feature_importances || [];
        const top10 = features.slice(0, 10);
        const max = Math.max(...top10.map((f) => f.importance || 0), 0.001);
        return top10.map((f) => ({
            name: f.feature,
            percentDisplay: `${(f.importance * 100).toFixed(1)}%`,
            barStyle: `width: ${Math.round((f.importance / max) * 100)}%;`,
        }));
    }

    get isJobRunning() { return this.jobState === 'running'; }
    get hasLogLines() { return this.logLines.length > 0; }

    get retrainLabel() {
        return this.isJobRunning ? 'Training…' : 'Retrain now';
    }
    get retrainDisabled() {
        return this.isRetraining || this.isJobRunning;
    }

    // ─── Retrain flow ─────────────────────────────────────────────

    async handleRetrain() {
        this.isRetraining = true;
        this.logLines = [];
        try {
            const raw = await triggerRetrain();
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.dispatchEvent(new ShowToastEvent({
                title: 'Retraining started',
                message: 'Watch the log stream below.',
                variant: 'success',
            }));
            this.jobState = 'running';
            this.jobMessage = parsed.message || 'queued';
            this._startPolling();
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Retrain failed',
                message: e?.message, variant: 'error',
            }));
        } finally {
            this.isRetraining = false;
        }
    }

    _startPolling() {
        this._stopPolling();
        this._tick();
        this._statusTimer = setInterval(() => this._tick(), STATUS_POLL_MS);
    }

    _stopPolling() {
        if (this._statusTimer) {
            clearInterval(this._statusTimer);
            this._statusTimer = null;
        }
    }

    async _tick() {
        try {
            const [statusRaw, logRaw] = await Promise.all([
                getInsightsStatus(),
                getTrainingLog({ tail: LOG_TAIL_LINES }),
            ]);
            const status = JSON.parse(statusRaw);
            const log = JSON.parse(logRaw);
            if (log && Array.isArray(log.lines)) this.logLines = log.lines;
            if (status?.latest_job) {
                this.jobState = status.latest_job.state;
                this.jobMessage = status.latest_job.message || '';
            }
            if (this.jobState === 'done' || this.jobState === 'error') {
                this._stopPolling();
                await this.refreshAll();
                if (this.jobState === 'done') {
                    this.dispatchEvent(new ShowToastEvent({
                        title: 'Training complete',
                        message: this.jobMessage || 'new model active',
                        variant: 'success',
                    }));
                } else {
                    this.dispatchEvent(new ShowToastEvent({
                        title: 'Training error',
                        message: this.jobMessage || 'see log',
                        variant: 'error',
                    }));
                }
            }
        } catch (e) {
            // Swallow poll errors — next tick retries.
        }
    }
}
