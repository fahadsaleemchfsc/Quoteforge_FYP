/**
 * QuoteForge Deal Insights LWC
 * =============================
 * Compact card on the Opportunity record page showing:
 *   - Big color-coded win probability (green ≥60, amber 40-60, red <40)
 *   - Haiku-generated plain-English explanation
 *   - Expandable driver breakdown (top 3 positive + top 3 negative SHAP values)
 *
 * Calls QuoteForgeController.getOpportunityInsight(recordId). The Apex
 * method is cacheable, so Salesforce will reuse the result within a short
 * transaction cache window; reloading the page re-fetches.
 *
 * Explanation polling: the backend populates explanation_text asynchronously
 * after the first prediction (Claude Haiku generates it in a background task).
 * If the initial response arrives with explanation_text null/empty, we poll
 * via refreshApex every POLL_INTERVAL_MS up to MAX_POLL_ATTEMPTS times, then
 * give up and render "Explanation unavailable" while keeping the drivers.
 */
import { LightningElement, api, wire } from 'lwc';
import { refreshApex } from '@salesforce/apex';
import getOpportunityInsight from '@salesforce/apex/QuoteForgeController.getOpportunityInsight';

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 10;

// Session 6.5 — translate internal ML feature names into rep-facing labels.
// The raw SHAP numbers are also suppressed in the template; only the
// direction (positive/negative) + bar width survive to the UI.
const FEATURE_LABELS = {
    activity_count: 'Customer engagement',
    amount: 'Deal size',
    days_since_last_activity: 'Recent activity',
    contact_activity_count: 'Contact engagement',
    contact_days_since_last_activity: 'Contact responsiveness',
    account_activity_count_365d: 'Account relationship strength',
    account_engagement_diversity: 'Engagement variety',
    days_since_account_last_activity: 'Account recency',
    contact_count_on_account: 'Contacts engaged',
    expected_close_distance: 'Timeline risk',
    age_days: 'Deal tenure',
    days_in_current_stage: 'Stage progression',
    activity_velocity: 'Engagement pace',
};

const CATEGORY_PREFIXES = {
    'industry=': 'Industry: ',
    'lead_source=': 'Lead source: ',
    'product_tier=': 'Product tier: ',
    'sales_region=': 'Region: ',
    'quarter=': 'Quarter: ',
    'record_type=': 'Deal type: ',
    'owner_id=': 'Owner: ',
};

function translateFeature(rawName) {
    if (FEATURE_LABELS[rawName]) return FEATURE_LABELS[rawName];
    for (const [prefix, label] of Object.entries(CATEGORY_PREFIXES)) {
        if (rawName.startsWith(prefix)) {
            return label + rawName.slice(prefix.length);
        }
    }
    return rawName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default class QuoteForgeDealInsights extends LightningElement {
    @api recordId;

    result = null;
    errorMessage = '';
    isLoading = true;
    showDrivers = false;
    explanationUnavailable = false;

    // Keeps the full @wire payload so refreshApex can re-invoke the adapter.
    _wiredResult;
    _pollTimer;
    _pollAttempts = 0;

    @wire(getOpportunityInsight, { opportunityId: '$recordId' })
    wiredInsight(wireResult) {
        this._wiredResult = wireResult;
        const { data, error } = wireResult;
        this.isLoading = false;
        if (error) {
            this.errorMessage = error?.body?.message || 'Unable to fetch insight.';
            this._stopPolling();
            return;
        }
        if (!data) return;
        try {
            const parsed = JSON.parse(data);
            if (parsed.error || parsed.detail) {
                this.errorMessage = parsed.error || parsed.detail;
                this._stopPolling();
                return;
            }

            // Opportunity switched in-page — reset polling bookkeeping so the
            // new record gets a fresh 30-second budget.
            if (this.result?.opportunity_id &&
                this.result.opportunity_id !== parsed.opportunity_id) {
                this._resetPollState();
            }

            this.result = parsed;
            this.errorMessage = '';

            const hasExplanation = !!(
                parsed.explanation_text && String(parsed.explanation_text).trim()
            );
            if (hasExplanation) {
                this._stopPolling();
                this.explanationUnavailable = false;
                return;
            }

            // No explanation yet — schedule another poll unless we've hit
            // the cap. _pollAttempts reflects polls initiated so far; when
            // it reaches MAX_POLL_ATTEMPTS the most recent refreshApex was
            // the 10th, and we stop.
            if (this._pollAttempts < MAX_POLL_ATTEMPTS) {
                this._scheduleNextPoll();
            } else {
                this._stopPolling();
                this.explanationUnavailable = true;
            }
        } catch (e) {
            // Include a preview of the raw payload so the rep/admin can see
            // WHAT came back (HTML error page, plain-text timeout, etc.)
            // instead of the generic "invalid response" we used to show.
            const preview = typeof data === 'string' ? data.substring(0, 120) : '';
            this.errorMessage = preview
                ? `Backend returned non-JSON: ${preview}…`
                : 'Invalid response from QuoteForge backend.';
            this._stopPolling();
        }
    }

    disconnectedCallback() {
        this._stopPolling();
    }

    _scheduleNextPoll() {
        if (this._pollTimer) return; // already scheduled, don't stack
        this._pollTimer = setTimeout(() => {
            this._pollTimer = null;
            this._pollAttempts += 1;
            // refreshApex re-fires the wire adapter, which runs wiredInsight
            // again. The wire handler decides whether to schedule the next
            // poll based on the updated payload.
            refreshApex(this._wiredResult).catch(() => {
                // Swallow transient errors — next poll (if any) still fires;
                // if this was the last one the wire handler will mark
                // explanationUnavailable on the next refresh that succeeds.
            });
        }, POLL_INTERVAL_MS);
    }

    _stopPolling() {
        if (this._pollTimer) {
            clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }
    }

    _resetPollState() {
        this._stopPolling();
        this._pollAttempts = 0;
        this.explanationUnavailable = false;
    }

    get hasResult() {
        return !!this.result && !this.errorMessage;
    }

    get hasExplanation() {
        return !!(
            this.result?.explanation_text &&
            String(this.result.explanation_text).trim()
        );
    }

    // "Generating…" placeholder is shown while we're still inside the poll
    // budget and haven't received an explanation yet.
    get explanationPending() {
        return this.hasResult && !this.hasExplanation && !this.explanationUnavailable;
    }

    get percentDisplay() {
        if (!this.result) return '';
        // Session 6.5 — if the bootstrap range is wider than 15pp, show it
        // as a range ("75-90%") instead of a point estimate. Narrow ranges
        // and predictions without range data fall back to the point.
        const lo = this.result.probability_lower;
        const hi = this.result.probability_upper;
        if (typeof lo === 'number' && typeof hi === 'number' && hi - lo > 0.15) {
            return `${Math.round(lo * 100)}–${Math.round(hi * 100)}%`;
        }
        return `${this.result.probability_percent}%`;
    }

    get hasRangeSpread() {
        const lo = this.result?.probability_lower;
        const hi = this.result?.probability_upper;
        return (typeof lo === 'number' && typeof hi === 'number' &&
                hi - lo > 0.15);
    }

    // ─── ICP match display (Phase 3) ─────────────────────────

    get hasICP() {
        return !!(this.result?.icp && typeof this.result.icp.match_percent === 'number');
    }

    get icpPercent() { return this.result?.icp?.match_percent; }

    get icpBandLabel() {
        const b = this.result?.icp?.band;
        if (b === 'strong') return 'strong fit';
        if (b === 'partial') return 'partial fit';
        return 'weak fit';
    }

    get icpLineClass() {
        const b = this.result?.icp?.band;
        return `qfd-icp-line qfd-icp-${b || 'weak'}`;
    }

    get icpReasonRows() {
        const reasons = this.result?.icp?.match_reasons || [];
        return reasons.map((r) => {
            const factorLabel = {
                industry: 'Industry',
                region: 'Region',
                amount: 'Deal size',
                employee_count: 'Employee count',
                engagement: 'Engagement',
                lead_source: 'Lead source',
            }[r.factor] || r.factor;
            const pill = r.status === 'match' ? 'qfd-pill-match'
                       : r.status === 'partial' ? 'qfd-pill-partial'
                       : 'qfd-pill-mismatch';
            return {
                factor: r.factor,
                factorLabel,
                status: r.status,
                detail: r.detail,
                statusPillClass: `qfd-icp-pill ${pill}`,
            };
        });
    }

    get bandLabel() {
        const b = this.result?.band;
        if (b === 'high') return 'High';
        if (b === 'medium') return 'Medium';
        return 'Low';
    }

    get bandContainerClass() {
        const b = this.result?.band;
        if (b === 'high') return 'qfd-band qfd-band-high';
        if (b === 'medium') return 'qfd-band qfd-band-medium';
        return 'qfd-band qfd-band-low';
    }

    get positiveDrivers() {
        return this._driverRows('positive');
    }
    get negativeDrivers() {
        return this._driverRows('negative');
    }
    get hasPositiveDrivers() { return this.positiveDrivers.length > 0; }
    get hasNegativeDrivers() { return this.negativeDrivers.length > 0; }

    _driverRows(direction) {
        if (!this.result?.top_drivers) return [];
        const filtered = this.result.top_drivers.filter((d) => d.direction === direction);
        const maxAbs = Math.max(
            ...this.result.top_drivers.map((d) => Math.abs(d.shap_value)),
            0.001,
        );
        return filtered.map((d) => {
            const width = Math.max(6, Math.round((Math.abs(d.shap_value) / maxAbs) * 100));
            return {
                // Session 6.5 — surface a rep-facing label; raw feature name
                // never reaches the template.
                feature: translateFeature(d.feature),
                barStyle: `width: ${width}%;`,
            };
        });
    }

    get updatedDisplay() {
        if (!this.result?.predicted_at) return '';
        try {
            return new Date(this.result.predicted_at).toLocaleString(undefined, {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
            });
        } catch (e) {
            return this.result.predicted_at;
        }
    }

    toggleDrivers() {
        this.showDrivers = !this.showDrivers;
    }
}
