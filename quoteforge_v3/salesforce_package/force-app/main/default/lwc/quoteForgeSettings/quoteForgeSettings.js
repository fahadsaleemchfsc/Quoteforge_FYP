/**
 * QuoteForge Settings — the "control panel" tab in the QuoteForge
 * Lightning App.
 *
 * Not a full admin UI (that lives in the QuoteForge React admin at the
 * same domain as the Named Credential). This page is a status +
 * installation-checklist view showing:
 *   - whether the backend is reachable
 *   - the active Deal Insights model metadata
 *   - pass/fail checks for each installation step
 *   - a quick-reference table pointing at where each config setting lives
 */
import { LightningElement } from 'lwc';
import getSettingsStatus from '@salesforce/apex/QuoteForgeController.getSettingsStatus';

function pct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(1)}%`;
}

function fixed3(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return n.toFixed(3);
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

export default class QuoteForgeSettings extends LightningElement {
    isLoading = true;
    status = {};

    connectedCallback() {
        this.refresh();
    }

    async refresh() {
        this.isLoading = true;
        try {
            const raw = await getSettingsStatus();
            this.status = JSON.parse(raw);
        } catch (e) {
            this.status = {
                backend_reachable: false,
                backend_error: e?.body?.message || e?.message || 'Unknown error',
                named_credential: 'QuoteForge_API',
                checks: [],
            };
        } finally {
            this.isLoading = false;
        }
    }

    handleRefresh() { this.refresh(); }

    // ─── Getters ──────────────────────────────────────────────

    get statusDotClass() {
        return this.status.backend_reachable
            ? 'qfs-dot qfs-dot-ok'
            : 'qfs-dot qfs-dot-err';
    }

    get statusLabel() {
        return this.status.backend_reachable
            ? 'Reachable'
            : 'Unreachable';
    }

    get checks() {
        const items = this.status.checks || [];
        return items.map((c) => ({
            ...c,
            icon: c.passed ? '✓' : '✗',
            rowClass: c.passed ? 'qfs-check-row qfs-check-pass' : 'qfs-check-row qfs-check-fail',
        }));
    }

    get hasActiveModel() { return !!this.status.active_model; }
    get activeModel() { return this.status.active_model || {}; }
    get accuracyDisplay() { return pct(this.activeModel.accuracy); }
    get aucDisplay() { return fixed3(this.activeModel.auc); }
    get trainingRowsDisplay() {
        const n = Number(this.activeModel.training_rows);
        return Number.isFinite(n) ? n.toLocaleString() : '—';
    }
    get trainedAtDisplay() { return formatDate(this.activeModel.trained_at); }
}
