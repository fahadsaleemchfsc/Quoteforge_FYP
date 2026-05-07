/**
 * QuoteForge ICP Config — Phase 4.
 *
 * Inline ICP builder for Salesforce. Mirrors the admin /icp React page
 * one-for-one. CRUD + activate + test scoring against a paste-in Opp Id.
 * Calls the same /api/icp endpoints through the Named Credential.
 */
import { LightningElement, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import listICPs from '@salesforce/apex/QuoteForgeController.listICPs';
import createICP from '@salesforce/apex/QuoteForgeController.createICP';
import updateICP from '@salesforce/apex/QuoteForgeController.updateICP';
import deleteICP from '@salesforce/apex/QuoteForgeController.deleteICP';
import activateICP from '@salesforce/apex/QuoteForgeController.activateICP';
import scoreOppAgainstICP from '@salesforce/apex/QuoteForgeController.scoreOppAgainstICP';

const EMPTY = {
    name: '', description: '',
    included_industries: [], included_regions: [],
    min_amount: '', max_amount: '',
    min_employee_count: '', max_employee_count: '',
    required_lead_sources: [], min_engagement_score: '',
    weight_industry_match: 1.0, weight_region_match: 0.8,
    weight_amount_fit: 1.0, weight_engagement: 1.2, weight_lead_source: 0.7,
};

function joinList(arr) { return (arr || []).join(', '); }
function splitList(s) {
    return (s || '').split(',').map((x) => x.trim()).filter(Boolean);
}
function numOrNull(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
}

export default class QuoteForgeICPConfig extends LightningElement {
    icps = [];
    @track draft = { ...EMPTY };
    selectedId = null;
    isLoading = true;
    isSaving = false;
    testOppId = '006gL00000KlPp8QAF';
    @track testResult = null;
    isTesting = false;

    connectedCallback() { this.refresh(); }

    async refresh() {
        this.isLoading = true;
        try {
            const raw = await listICPs();
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.icps = parsed;
            const active = this.icps.find((i) => i.is_active) || this.icps[0];
            if (active) this.loadIcp(active);
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Load failed',
                message: e?.message || 'unable to load ICPs',
                variant: 'error',
            }));
        } finally {
            this.isLoading = false;
        }
    }

    loadIcp(icp) {
        this.selectedId = icp.id;
        this.draft = {
            ...EMPTY, ...icp,
            min_amount: icp.min_amount ?? '',
            max_amount: icp.max_amount ?? '',
            min_employee_count: icp.min_employee_count ?? '',
            max_employee_count: icp.max_employee_count ?? '',
            min_engagement_score: icp.min_engagement_score ?? '',
        };
        this.testResult = null;
    }

    handleSelect(e) {
        const id = e.currentTarget.dataset.id;
        const icp = this.icps.find((i) => i.id === id);
        if (icp) this.loadIcp(icp);
    }

    newIcp() {
        this.selectedId = null;
        this.draft = { ...EMPTY };
        this.testResult = null;
    }

    // ─── Field handlers ──────────────────────────────────────────

    handleFieldChange(e) {
        const key = e.currentTarget.dataset.key;
        const value = e.target.value ?? e.detail?.value;
        this.draft = { ...this.draft, [key]: value };
    }

    handleListField(e) {
        const key = e.currentTarget.dataset.key;
        this.draft = { ...this.draft, [key]: splitList(e.target.value) };
    }

    handleWeightChange(e) {
        const key = e.currentTarget.dataset.key;
        this.draft = { ...this.draft, [key]: parseFloat(e.target.value) };
    }

    // ─── Actions ──────────────────────────────────────────────────

    async save() {
        if (!this.draft.name) return;
        this.isSaving = true;
        try {
            const payload = {
                name: this.draft.name,
                description: this.draft.description || null,
                included_industries: this.draft.included_industries,
                included_regions: this.draft.included_regions,
                min_amount: numOrNull(this.draft.min_amount),
                max_amount: numOrNull(this.draft.max_amount),
                min_employee_count: numOrNull(this.draft.min_employee_count),
                max_employee_count: numOrNull(this.draft.max_employee_count),
                required_lead_sources: this.draft.required_lead_sources,
                min_engagement_score: numOrNull(this.draft.min_engagement_score),
                weight_industry_match: Number(this.draft.weight_industry_match),
                weight_region_match: Number(this.draft.weight_region_match),
                weight_amount_fit: Number(this.draft.weight_amount_fit),
                weight_engagement: Number(this.draft.weight_engagement),
                weight_lead_source: Number(this.draft.weight_lead_source),
            };
            const raw = this.selectedId
                ? await updateICP({ icpId: this.selectedId, bodyJson: JSON.stringify(payload) })
                : await createICP({ bodyJson: JSON.stringify(payload) });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.dispatchEvent(new ShowToastEvent({
                title: this.selectedId ? 'ICP updated' : 'ICP created',
                variant: 'success',
            }));
            await this.refresh();
            this.loadIcp(parsed);
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Save failed', message: e?.message, variant: 'error',
            }));
        } finally {
            this.isSaving = false;
        }
    }

    async activate() {
        if (!this.selectedId) return;
        try {
            const raw = await activateICP({ icpId: this.selectedId });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.dispatchEvent(new ShowToastEvent({
                title: 'Activated', variant: 'success',
            }));
            await this.refresh();
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Activate failed', message: e?.message, variant: 'error',
            }));
        }
    }

    async remove() {
        if (!this.selectedId) return;
        // eslint-disable-next-line no-alert
        if (!confirm('Delete this ICP?')) return;
        try {
            const raw = await deleteICP({ icpId: this.selectedId });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.dispatchEvent(new ShowToastEvent({
                title: 'Deleted', variant: 'success',
            }));
            this.newIcp();
            await this.refresh();
        } catch (e) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Delete failed', message: e?.message, variant: 'error',
            }));
        }
    }

    handleTestOppIdChange(e) { this.testOppId = e.target.value; }

    async runTest() {
        if (!this.testOppId?.trim()) return;
        this.isTesting = true;
        try {
            const raw = await scoreOppAgainstICP({ opportunityId: this.testOppId.trim() });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.testResult = parsed;
        } catch (e) {
            this.testResult = { error: e?.message };
        } finally {
            this.isTesting = false;
        }
    }

    // ─── Derived ──────────────────────────────────────────────────

    get hasIcps() { return this.icps.length > 0; }
    get editTitle() { return this.selectedId ? 'Edit ICP' : 'Create ICP'; }
    get saveLabel() { return this.selectedId ? 'Save changes' : 'Create ICP'; }
    get canSave() { return !!this.draft.name && !this.isSaving; }
    get showActivate() { return this.selectedId && !this.draft.is_active; }

    get includedIndustriesString() { return joinList(this.draft.included_industries); }
    get includedRegionsString()    { return joinList(this.draft.included_regions); }
    get leadSourcesString()         { return joinList(this.draft.required_lead_sources); }

    get icpListDecorated() {
        return this.icps.map((i) => ({
            ...i,
            rowClass: `qfic-list-row ${this.selectedId === i.id ? 'qfic-list-row-selected' : ''}`,
            activeBadge: i.is_active ? 'ACTIVE' : '',
        }));
    }

    get testResultBandClass() {
        if (!this.testResult) return '';
        return `qfic-test-band qfic-test-band-${this.testResult.band || 'weak'}`;
    }
    get testResultReasons() {
        if (!this.testResult?.match_reasons) return [];
        return this.testResult.match_reasons.map((r) => ({
            ...r,
            pillClass: r.status === 'match' ? 'qfic-pill qfic-pill-match'
                     : r.status === 'partial' ? 'qfic-pill qfic-pill-partial'
                     : 'qfic-pill qfic-pill-mismatch',
        }));
    }
}
