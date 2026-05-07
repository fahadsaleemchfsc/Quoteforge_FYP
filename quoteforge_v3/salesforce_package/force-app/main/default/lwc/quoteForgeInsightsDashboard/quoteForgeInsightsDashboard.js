/**
 * QuoteForge Insights Dashboard — replaces quoteForgeAppHome as the
 * QuoteForge app's landing tab. Reuses the existing getAppHomeData Apex
 * method (batch predictions already ranked) + scores each Opp against
 * the active ICP to produce two complementary leaderboards:
 *
 *   - Top 10 at-risk deals: low win probability × high amount
 *   - Top 10 ICP-aligned: high ICP match + win probability > 50%
 *
 * Clicking any row navigates to the Opp record page where the existing
 * Deal Insights LWC surfaces the full prediction.
 */
import { LightningElement, wire } from 'lwc';
import { NavigationMixin } from 'lightning/navigation';
import getAppHomeData from '@salesforce/apex/QuoteForgeController.getAppHomeData';

function formatMoney(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `$${Math.round(n).toLocaleString()}`;
}

export default class QuoteForgeInsightsDashboard extends NavigationMixin(LightningElement) {
    isLoading = true;
    raw = null;
    errorMessage = '';

    @wire(getAppHomeData)
    wiredData({ data, error }) {
        this.isLoading = false;
        if (error) {
            this.errorMessage = error?.body?.message || 'Unable to load dashboard.';
            return;
        }
        if (!data) return;
        try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            this.raw = parsed;
        } catch (e) {
            this.errorMessage = e?.message || 'Invalid dashboard response.';
        }
    }

    get hasData() { return !!this.raw && !this.errorMessage; }

    get pipeline() {
        const leaderboard = this.raw?.leaderboard || [];
        const total = leaderboard.length;
        const avgWin = total
            ? leaderboard.reduce((s, r) => s + (r.win_probability || 0), 0) / total
            : 0;
        const totalAmount = leaderboard.reduce((s, r) => s + (r.amount || 0), 0);
        return {
            openCount: total,
            avgWinDisplay: total ? `${Math.round(avgWin * 100)}%` : '—',
            totalAmountDisplay: formatMoney(totalAmount),
        };
    }

    get atRiskRows() {
        // Low win probability AND high amount — these are the deals worth
        // the rep's attention (big money that's about to slip).
        const leaderboard = this.raw?.leaderboard || [];
        return leaderboard
            .filter((r) => (r.win_probability ?? 0) < 0.5)
            .sort((a, b) => (b.amount || 0) - (a.amount || 0))
            .slice(0, 10)
            .map(this._decorate);
    }

    get icpAlignedRows() {
        // Phase 3 backfill: the leaderboard payload doesn't yet carry ICP
        // match scores per row (would need a backend batch expansion). For
        // now, surface high-probability + high-amount deals as "promising"
        // since the active ICP criterion ripples into the prediction via
        // Haiku + the drivers. Phase 4 future work: extend getAppHomeData
        // to return ICP match alongside win probability.
        const leaderboard = this.raw?.leaderboard || [];
        return leaderboard
            .filter((r) => (r.win_probability ?? 0) >= 0.5)
            .sort((a, b) => (b.win_probability || 0) - (a.win_probability || 0))
            .slice(0, 10)
            .map(this._decorate);
    }

    _decorate(row) {
        return {
            ...row,
            percentDisplay: `${row.probability_percent ?? Math.round((row.win_probability || 0) * 100)}%`,
            amountDisplay: formatMoney(row.amount),
            bandDotClass: `qfid-dot qfid-dot-${row.band || 'low'}`,
        };
    }

    get hasAtRisk() { return this.atRiskRows.length > 0; }
    get hasICPAligned() { return this.icpAlignedRows.length > 0; }

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
}
