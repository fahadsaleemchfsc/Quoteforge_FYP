/**
 * QuoteForge Model Accuracy LWC
 *
 * Answers the buyer's most important question: "how do I know this model
 * works on my data?" Renders four sections from /api/insights/accuracy:
 *   1. Holdout metrics (accuracy, precision, recall, AUC)
 *   2. Accuracy by confidence bucket (calibration sanity)
 *   3. Recent closed deals (predicted vs. actual, last 10)
 *   4. Retrain callout (when deals-since-last-training crosses threshold)
 */
import { LightningElement } from 'lwc';
import { NavigationMixin } from 'lightning/navigation';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import getModelAccuracy from '@salesforce/apex/QuoteForgeController.getModelAccuracy';
import triggerRetrain from '@salesforce/apex/QuoteForgeController.triggerRetrain';

const TIER_LABELS = {
    insufficient: 'Not enough data',
    early_stage: 'Early stage',
    standard: 'Standard',
    mature: 'Mature',
};

function pct(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(1)}%`;
}

function formatDate(iso) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleDateString(undefined, {
            month: 'short', day: 'numeric', year: 'numeric',
        });
    } catch (e) { return iso; }
}

export default class QuoteForgeModelAccuracy extends NavigationMixin(LightningElement) {
    data = null;
    isLoading = true;
    isRetraining = false;
    errorMessage = '';

    connectedCallback() { this.refresh(); }

    async refresh() {
        this.isLoading = true;
        this.errorMessage = '';
        try {
            const raw = await getModelAccuracy();
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.data = parsed;
        } catch (e) {
            this.errorMessage = e?.body?.message || e?.message || 'Unable to load accuracy data.';
        } finally {
            this.isLoading = false;
        }
    }

    // ─── Derived ──────────────────────────────────────────────────

    get hasData() { return !!this.data && !this.errorMessage; }

    get tierLabel() { return TIER_LABELS[this.data?.data_quality_tier] || this.data?.data_quality_tier || '—'; }

    get headerLine() {
        if (!this.data) return '';
        const rows = this.data.training_row_count?.toLocaleString?.() || this.data.training_row_count;
        const trained = formatDate(this.data?.recent_closed_deals?.[0]?.close_date);
        return `Model v${this.data.model_version} · ${this.tierLabel} · ${rows} deals`;
    }

    get accuracyDisplay()  { return pct(this.data?.holdout_metrics?.accuracy); }
    get precisionDisplay() { return pct(this.data?.holdout_metrics?.precision); }
    get recallDisplay()    { return pct(this.data?.holdout_metrics?.recall); }
    get aucDisplay()       { return Number(this.data?.holdout_metrics?.auc ?? 0).toFixed(3); }

    get holdoutSubtitle() {
        const n = this.data?.holdout_row_count ?? 0;
        return `on ${n.toLocaleString()} deals the model never saw`;
    }

    get bucketRows() {
        return (this.data?.accuracy_by_confidence_bucket || []).map((b) => {
            const rate = Number(b.actual_win_rate || 0);
            const label = rate >= 0.7 || rate <= 0.3 ? '✓ Accurate' : '~ Near coin-flip';
            const pct100 = Math.round(rate * 100);
            return {
                ...b,
                actualDisplay: `${Math.round(b.count * rate)} (${pct100}%)`,
                matchLabel: label,
                rowClass: rate >= 0.7 || rate <= 0.3 ? 'qfma-row-accurate' : 'qfma-row-coinflip',
            };
        });
    }

    get recentRows() {
        return (this.data?.recent_closed_deals || []).map((d) => {
            const predProb = Number(d.predicted_probability_at_close || 0);
            const predSide = predProb >= 0.5 ? 'win' : 'loss';
            const hit = (d.actual_outcome === 'won' && predSide === 'win')
                     || (d.actual_outcome === 'lost' && predSide === 'loss');
            return {
                ...d,
                predictedDisplay: `${Math.round(predProb * 100)}% (${predSide})`,
                actualDisplay: d.actual_outcome === 'won' ? 'Won' : 'Lost',
                hitIcon: hit ? '✓' : '✗',
                hitClass: hit ? 'qfma-hit' : 'qfma-miss',
                displayName: d.name || d.sf_opportunity_id,
            };
        });
    }

    get showRetrainCallout() { return !!this.data?.retrain_recommended; }

    get retrainReason() { return this.data?.retrain_reason || ''; }

    // ─── Actions ──────────────────────────────────────────────────

    openOpportunity(event) {
        const id = event.currentTarget.dataset.id;
        if (!id) return;
        this[NavigationMixin.Navigate]({
            type: 'standard__recordPage',
            attributes: {
                recordId: id, objectApiName: 'Opportunity', actionName: 'view',
            },
        });
    }

    async handleRetrain() {
        this.isRetraining = true;
        try {
            const raw = await triggerRetrain();
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.dispatchEvent(new ShowToastEvent({
                title: 'Retraining started',
                message: 'Kicked off in the background. Refresh in ~30 seconds.',
                variant: 'success',
            }));
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Retrain failed',
                message: e?.body?.message || e?.message || 'Unknown error',
                variant: 'error',
            }));
        } finally {
            this.isRetraining = false;
        }
    }
}
