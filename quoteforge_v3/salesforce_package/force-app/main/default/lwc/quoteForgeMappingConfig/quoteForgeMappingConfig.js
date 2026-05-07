/**
 * QuoteForge Mapping Config — in-Salesforce mapping wizard.
 *
 * Mirrors the existing React admin /insights/setup three-step flow so
 * admins can configure Deal Insights without leaving Salesforce. Calls
 * the same three API endpoints through the QuoteForge_API Named Credential:
 *   GET  /insights/schema   → step 1 summary + field dropdowns
 *   GET  /insights/mapping  → current mapping (or auto-suggested draft)
 *   POST /insights/mapping  → save edits from the wizard
 */
import { LightningElement, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import getInsightsSchema from '@salesforce/apex/QuoteForgeController.getInsightsSchema';
import getInsightsMapping from '@salesforce/apex/QuoteForgeController.getInsightsMapping';
import saveInsightsMapping from '@salesforce/apex/QuoteForgeController.saveInsightsMapping';

const REQUIRED_FIELDS = [
    { key: 'amount_field',       label: 'Amount field',       hint: 'Currency column for deal size.' },
    { key: 'stage_field',        label: 'Stage field',        hint: 'Pipeline stage picklist.' },
    { key: 'close_date_field',   label: 'Close date field',   hint: 'Expected close date.' },
    { key: 'created_date_field', label: 'Created date field', hint: 'Opportunity creation timestamp.' },
    { key: 'is_closed_field',    label: 'IsClosed flag',      hint: 'Boolean — Opportunity closed?' },
    { key: 'is_won_field',       label: 'IsWon flag',         hint: 'Boolean — closed won?' },
];

const OPTIONAL_FIELDS = [
    { key: 'industry_field',    label: 'Industry (Account)', hint: 'For categorical signal.' },
    { key: 'lead_source_field', label: 'Lead source',        hint: 'Channel attribution.' },
    { key: 'owner_field',       label: 'Owner ID',           hint: 'Per-rep effects.' },
    { key: 'record_type_field', label: 'Record type',        hint: 'For filtering test / demo Opps.' },
];

const CUSTOM_TYPES = [
    { label: 'Numeric',     value: 'numeric' },
    { label: 'Categorical', value: 'categorical' },
    { label: 'Boolean',     value: 'boolean' },
];

export default class QuoteForgeMappingConfig extends LightningElement {
    step = 1;
    isLoading = true;
    isSaving = false;
    errorMessage = '';
    saveSuccessful = false;

    @track schema = null;
    @track mapping = null;

    customModalOpen = false;
    customDraft = { sf_field: '', feature_name: '', type: 'categorical' };

    async connectedCallback() {
        try {
            const [schemaRaw, mappingRaw] = await Promise.all([
                getInsightsSchema(),
                getInsightsMapping(),
            ]);
            const schema = JSON.parse(schemaRaw);
            const mapping = JSON.parse(mappingRaw);
            if (schema.error) throw new Error(schema.error);
            if (mapping.error) throw new Error(mapping.error);
            this.schema = schema;
            this.mapping = mapping;
        } catch (e) {
            this.errorMessage = e?.body?.message || e?.message ||
                'Unable to load schema or mapping.';
        } finally {
            this.isLoading = false;
        }
    }

    // ─── Derived data ──────────────────────────────────────────────

    get stepperClass() { return `qfm-stepper qfm-step-${this.step}`; }
    get isStep1() { return this.step === 1; }
    get isStep2() { return this.step === 2; }
    get isStep3() { return this.step === 3; }

    get fieldOptions() {
        if (!this.schema?.opportunity_fields) return [];
        return this.schema.opportunity_fields.map((f) => ({
            value: f.api_name,
            label: `${f.api_name} — ${f.label} (${f.type})`,
        }));
    }
    get fieldOptionsWithNone() {
        return [{ value: '', label: '— none —' }, ...this.fieldOptions];
    }
    get customTypeOptions() { return CUSTOM_TYPES; }

    get requiredRows() {
        if (!this.mapping) return [];
        return REQUIRED_FIELDS.map((f) => ({
            ...f,
            currentValue: this.mapping[f.key] || '',
        }));
    }
    get optionalRows() {
        if (!this.mapping) return [];
        return OPTIONAL_FIELDS.map((f) => ({
            ...f,
            currentValue: this.mapping[f.key] || '',
        }));
    }

    get customFields() { return this.mapping?.custom_fields || []; }
    get hasCustomFields() { return this.customFields.length > 0; }

    get recordTypeRows() {
        if (!this.schema?.record_types) return [];
        const excluded = this.mapping?.excluded_record_types || [];
        return this.schema.record_types.map((rt) => ({
            ...rt,
            included: !excluded.includes(rt.id),
        }));
    }
    get hasRecordTypes() { return this.recordTypeRows.length > 0; }

    get customFieldCandidates() {
        if (!this.schema) return [];
        const pool = this.schema.custom_fields?.length > 0
            ? this.schema.custom_fields
            : this.schema.opportunity_fields || [];
        return pool.map((f) => ({
            value: f.api_name,
            label: `${f.api_name} — ${f.label}`,
        }));
    }

    // ─── Step navigation ───────────────────────────────────────────

    goStep2() { this.step = 2; this.saveSuccessful = false; }
    goStep1() { this.step = 1; }
    goStep3() { this.step = 3; }
    back() { if (this.step > 1) this.step -= 1; }

    // ─── Field edits ───────────────────────────────────────────────

    handleRequiredChange(e) {
        const key = e.currentTarget.dataset.key;
        const value = e.detail.value;
        this.mapping = { ...this.mapping, [key]: value };
    }

    handleOptionalChange(e) {
        const key = e.currentTarget.dataset.key;
        const value = e.detail.value || null;
        this.mapping = { ...this.mapping, [key]: value };
    }

    handleRecordTypeToggle(e) {
        const id = e.currentTarget.dataset.id;
        const now = new Set(this.mapping.excluded_record_types || []);
        if (e.target.checked) now.delete(id); else now.add(id);
        this.mapping = { ...this.mapping, excluded_record_types: [...now] };
    }

    // ─── Custom fields ─────────────────────────────────────────────

    openCustomModal() {
        this.customDraft = { sf_field: '', feature_name: '', type: 'categorical' };
        this.customModalOpen = true;
    }
    closeCustomModal() { this.customModalOpen = false; }

    handleCustomField(e) {
        this.customDraft = { ...this.customDraft, sf_field: e.detail.value };
    }
    handleCustomName(e) {
        const raw = e.detail.value || '';
        this.customDraft = {
            ...this.customDraft,
            feature_name: raw.replace(/[^a-zA-Z0-9_]/g, '_'),
        };
    }
    handleCustomType(e) {
        this.customDraft = { ...this.customDraft, type: e.detail.value };
    }

    addCustomField() {
        const draft = this.customDraft;
        if (!draft.sf_field || !draft.feature_name) return;
        const cfs = [...(this.mapping.custom_fields || []), draft];
        this.mapping = { ...this.mapping, custom_fields: cfs };
        this.customModalOpen = false;
    }

    removeCustomField(e) {
        const idx = parseInt(e.currentTarget.dataset.idx, 10);
        const cfs = (this.mapping.custom_fields || []).filter((_, i) => i !== idx);
        this.mapping = { ...this.mapping, custom_fields: cfs };
    }

    // ─── Submit ────────────────────────────────────────────────────

    async handleSave() {
        this.isSaving = true;
        this.errorMessage = '';
        try {
            const payload = { ...this.mapping, auto_suggested: false };
            delete payload.id;
            delete payload.tenant_id;
            delete payload.suggestions;
            const raw = await saveInsightsMapping({ mappingJson: JSON.stringify(payload) });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);
            this.mapping = parsed;
            this.saveSuccessful = true;
            this.dispatchEvent(new ShowToastEvent({
                title: 'Mapping saved',
                message: 'Ready to train your model.',
                variant: 'success',
            }));
        } catch (e) {
            this.errorMessage = e?.body?.message || e?.message || 'Save failed.';
            this.dispatchEvent(new ShowToastEvent({
                title: 'Save failed', message: this.errorMessage, variant: 'error',
            }));
        } finally {
            this.isSaving = false;
        }
    }
}
