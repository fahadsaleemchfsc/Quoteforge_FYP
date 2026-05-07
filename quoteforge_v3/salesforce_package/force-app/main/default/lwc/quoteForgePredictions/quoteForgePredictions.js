/**
 * QuoteForge Predictions — filterable table of every open Opp with its
 * win probability. Reuses the existing getAppHomeData leaderboard payload
 * (top-15 open Opps already ranked). Filters are client-side since the
 * dataset is bounded.
 */
import { LightningElement, wire } from 'lwc';
import { NavigationMixin } from 'lightning/navigation';
import getAppHomeData from '@salesforce/apex/QuoteForgeController.getAppHomeData';

const PAGE_SIZE = 25;

function formatMoney(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `$${Math.round(n).toLocaleString()}`;
}

export default class QuoteForgePredictions extends NavigationMixin(LightningElement) {
    isLoading = true;
    raw = null;
    errorMessage = '';

    filterStage = '';
    filterMinAmount = '';
    filterMinWinProb = '';
    sortKey = 'win_probability';
    sortDir = 'desc';
    page = 1;

    @wire(getAppHomeData)
    wiredData({ data, error }) {
        this.isLoading = false;
        if (error) {
            this.errorMessage = error?.body?.message || 'Unable to load predictions.';
            return;
        }
        if (!data) return;
        try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            this.raw = parsed;
        } catch (e) {
            this.errorMessage = e?.message || 'Invalid response.';
        }
    }

    // ─── Filtering + sorting + pagination ─────────────────────────

    get hasData() { return !!this.raw && !this.errorMessage; }

    get stageOptions() {
        const leaderboard = this.raw?.leaderboard || [];
        const stages = [...new Set(leaderboard.map((r) => r.stage).filter(Boolean))];
        return [{ label: 'All stages', value: '' },
                ...stages.map((s) => ({ label: s, value: s }))];
    }

    get filteredSortedRows() {
        const leaderboard = this.raw?.leaderboard || [];
        const minAmt = Number(this.filterMinAmount) || 0;
        const minProb = (Number(this.filterMinWinProb) || 0) / 100;

        const filtered = leaderboard.filter((r) => {
            if (this.filterStage && r.stage !== this.filterStage) return false;
            if ((r.amount || 0) < minAmt) return false;
            if ((r.win_probability || 0) < minProb) return false;
            return true;
        });

        const dir = this.sortDir === 'desc' ? -1 : 1;
        const key = this.sortKey;
        filtered.sort((a, b) => {
            const av = a[key] ?? 0;
            const bv = b[key] ?? 0;
            if (typeof av === 'string' || typeof bv === 'string') {
                return dir * String(av).localeCompare(String(bv));
            }
            return dir * (av < bv ? -1 : av > bv ? 1 : 0);
        });
        return filtered;
    }

    get totalRows() { return this.filteredSortedRows.length; }
    get totalPages() {
        return Math.max(1, Math.ceil(this.totalRows / PAGE_SIZE));
    }

    get pagedRows() {
        const start = (this.page - 1) * PAGE_SIZE;
        return this.filteredSortedRows.slice(start, start + PAGE_SIZE).map((r) => ({
            ...r,
            percentDisplay: `${r.probability_percent ?? Math.round((r.win_probability || 0) * 100)}%`,
            amountDisplay: formatMoney(r.amount),
            bandClass: `qfp-band qfp-band-${r.band || 'low'}`,
        }));
    }

    get hasRows() { return this.pagedRows.length > 0; }
    get pageLabel() { return `Page ${this.page} / ${this.totalPages}`; }
    get canPrev() { return this.page > 1; }
    get canNext() { return this.page < this.totalPages; }
    // LWC doesn't support `!canPrev` inline in templates — provide inverted.
    get canPrevDisabled() { return !this.canPrev; }
    get canNextDisabled() { return !this.canNext; }

    // ─── Handlers ─────────────────────────────────────────────────

    handleStageChange(e) { this.filterStage = e.detail.value; this.page = 1; }
    handleMinAmount(e) { this.filterMinAmount = e.target.value; this.page = 1; }
    handleMinWinProb(e) { this.filterMinWinProb = e.target.value; this.page = 1; }

    prevPage() { if (this.canPrev) this.page -= 1; }
    nextPage() { if (this.canNext) this.page += 1; }

    sortBy(event) {
        const key = event.currentTarget.dataset.key;
        if (this.sortKey === key) {
            this.sortDir = this.sortDir === 'desc' ? 'asc' : 'desc';
        } else {
            this.sortKey = key;
            this.sortDir = 'desc';
        }
    }

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
