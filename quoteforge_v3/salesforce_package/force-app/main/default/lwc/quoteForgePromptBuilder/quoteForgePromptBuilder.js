/**
 * QuoteForge Prompt Builder LWC
 * ==============================
 * Natural-language → signed offer preview → commit.
 *
 * Flow:
 *   1. Rep types prompt on a Contact (or Opportunity / Account) record page.
 *   2. Optionally picks a linked Opportunity.
 *   3. Submit → generateQuoteFromPrompt Apex → backend parses + runs guardrails.
 *   4. Preview shows SKUs, quantities, totals, guardrail verdict (pass/review/block).
 *   5. Approve → commitQuoteFromPrompt → QuoteForge commits the offer + logs a Task.
 */
import { LightningElement, api, wire } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { NavigationMixin } from 'lightning/navigation';
import { getRecord, getFieldValue } from 'lightning/uiRecordApi';
import generateQuoteFromPrompt from '@salesforce/apex/QuoteForgeController.generateQuoteFromPrompt';
import commitQuoteFromPrompt from '@salesforce/apex/QuoteForgeController.commitQuoteFromPrompt';

import CONTACT_NAME from '@salesforce/schema/Contact.Name';
import CONTACT_ACCOUNT_NAME from '@salesforce/schema/Contact.Account.Name';

const CONTACT_FIELDS = [CONTACT_NAME, CONTACT_ACCOUNT_NAME];


function formatMoney(n, currency) {
    const num = Number(n);
    if (!Number.isFinite(num)) return '—';
    const sym = currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '$';
    return sym + num.toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
}

function formatDate(iso) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleDateString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric',
        });
    } catch (e) { return iso; }
}

export default class QuoteForgePromptBuilder extends NavigationMixin(LightningElement) {
    @api recordId;   // Contact, Opportunity, or Account — depends on placement

    promptText = '';
    selectedOpportunityId = null;
    selectedOppLabel = '';

    isProcessing = false;
    isCommitting = false;
    statusMessage = '';
    hasError = false;
    errorMessage = '';

    result = null;          // PromptToQuoteResult from backend
    commitResult = null;    // CommitQuoteResult from backend

    contactName = '';
    contactAccount = '';

    examples = [
        { id: 1, label: 'Simple',       prompt: 'Quote Acme Corp for 10 ENT-LIC licenses.' },
        { id: 2, label: 'PK region',    prompt: 'Proposal for Punjab IT Board in Pakistan: 5 ENT-LIC plus ONBOARD-STD.' },
        { id: 3, label: 'Mixed cart',   prompt: 'TechStart Inc needs 3 PRO-LIC seats and 1 SUPPORT-ANNUAL.' },
    ];

    @api
    get objectApiName() { return this._objectApiName; }
    set objectApiName(v) { this._objectApiName = v; }
    _objectApiName = 'Contact';

    connectedCallback() {
        // If we're dropped on an Opportunity page, auto-link.
        if (this._objectApiName === 'Opportunity' && this.recordId) {
            this.selectedOpportunityId = this.recordId;
            this.selectedOppLabel = 'this Opportunity';
        }
    }

    // Wire the contact record for chip display. Only fires when recordId is
    // a Contact; for other objects the wire returns an error we ignore.
    @wire(getRecord, { recordId: '$recordId', fields: CONTACT_FIELDS })
    wiredContact({ data }) {
        if (!data) return;
        this.contactName = getFieldValue(data, CONTACT_NAME) || '';
        this.contactAccount = getFieldValue(data, CONTACT_ACCOUNT_NAME) || '';
    }

    // ─── Getters ──────────────────────────────────────────────────

    get submitLabel() { return this.isProcessing ? 'Generating…' : 'Generate quote'; }
    get approveLabel() { return this.isCommitting ? 'Committing…' : 'Approve + commit'; }

    get submitDisabled() {
        return this.isProcessing || !this.promptText || this.promptText.trim().length < 10;
    }

    get hasResult() {
        return !!this.result || this.isCommitted || this.isPendingApproval || this.isProcessing || this.hasError;
    }

    get showPreview() {
        return !!this.result && this.result.guardrail_verdict !== 'block'
            && !this.isCommitted && !this.isPendingApproval;
    }

    get showBlocked() {
        return !!this.result && this.result.guardrail_verdict === 'block';
    }

    get isCommitted() {
        return !!this.commitResult && this.commitResult.status === 'committed';
    }

    get isPendingApproval() {
        return !!this.commitResult && this.commitResult.status === 'pending_approval';
    }

    get contextChipsVisible() {
        return this.contactLabel || this.selectedOppLabel || this.parseSource;
    }

    get contactLabel() {
        if (this._objectApiName !== 'Contact') return '';
        return this.contactName
            ? (this.contactAccount ? `${this.contactName} · ${this.contactAccount}` : this.contactName)
            : '';
    }

    get parseSource() { return this.result?.parse_source || ''; }
    get guardrailReason() { return this.result?.guardrail_reason || 'Seller policy refused this combination.'; }

    get verdictBadgeClass() {
        const v = this.result?.guardrail_verdict;
        return v === 'review' ? 'qf-badge qf-badge-review' : 'qf-badge qf-badge-pass';
    }
    get verdictBadgeText() {
        const v = this.result?.guardrail_verdict;
        return v === 'review' ? 'Review required' : 'Guardrails passed';
    }

    get lineItemsDisplay() {
        if (!this.result) return [];
        const cur = this.result.currency;
        return this.result.line_items.map((li) => ({
            ...li,
            unit_price_display: formatMoney(li.unit_price, cur),
            line_total_display: formatMoney(li.line_total, cur),
        }));
    }

    get subtotalDisplay() { return formatMoney(this.result?.subtotal, this.result?.currency); }
    get discountDisplay() { return formatMoney(this.result?.discount, this.result?.currency); }
    get taxDisplay()      { return formatMoney(this.result?.tax, this.result?.currency); }
    get totalDisplay()    { return formatMoney(this.result?.total, this.result?.currency); }
    get hasDiscount()     { return (this.result?.discount || 0) > 0; }
    get hasTax()          { return (this.result?.tax || 0) > 0; }
    get validUntilDisplay() { return formatDate(this.result?.valid_until); }

    // ─── Handlers ──────────────────────────────────────────────────

    handlePromptChange(e) { this.promptText = e.detail?.value ?? e.target.value; }

    handleOpportunityPick(e) {
        this.selectedOpportunityId = e.detail.recordId || null;
        this.selectedOppLabel = this.selectedOpportunityId ? 'linked to Opportunity' : '';
    }

    useExample(e) {
        const id = parseInt(e.currentTarget.dataset.id, 10);
        const ex = this.examples.find((x) => x.id === id);
        if (ex) this.promptText = ex.prompt;
    }

    async handleSubmit() {
        this.isProcessing = true;
        this.hasError = false;
        this.result = null;
        this.commitResult = null;
        this.statusMessage = 'Parsing prompt…';

        setTimeout(() => {
            if (this.isProcessing) this.statusMessage = 'Resolving catalog…';
        }, 1500);
        setTimeout(() => {
            if (this.isProcessing) this.statusMessage = 'Running guardrails…';
        }, 3500);

        try {
            const contactId = this._objectApiName === 'Contact' ? this.recordId : null;
            const raw = await generateQuoteFromPrompt({
                contactId,
                opportunityId: this.selectedOpportunityId,
                promptText: this.promptText,
            });
            const parsed = JSON.parse(raw);

            if (parsed.error) throw new Error(parsed.error);

            this.result = parsed;

            if (parsed.guardrail_verdict === 'block') {
                this.dispatchEvent(new ShowToastEvent({
                    title: 'Blocked by guardrails',
                    message: parsed.guardrail_reason || 'Seller policy refused this quote.',
                    variant: 'warning',
                }));
            } else {
                this.dispatchEvent(new ShowToastEvent({
                    title: parsed.guardrail_verdict === 'review'
                        ? 'Quote needs review' : 'Quote generated',
                    message: `${parsed.line_items.length} line items · ${this.totalDisplay}`,
                    variant: parsed.guardrail_verdict === 'review' ? 'info' : 'success',
                }));
            }
        } catch (err) {
            this.hasError = true;
            this.errorMessage = err.body?.message || err.message || 'Quote generation failed';
        } finally {
            this.isProcessing = false;
        }
    }

    async handleApprove() {
        if (!this.result?.offer_id) return;
        this.isCommitting = true;
        try {
            const raw = await commitQuoteFromPrompt({
                offerId: this.result.offer_id,
                signature: this.result.signature,
                opportunityId: this.selectedOpportunityId,
            });
            const parsed = JSON.parse(raw);
            if (parsed.error) throw new Error(parsed.error);

            this.commitResult = parsed;

            if (parsed.status === 'committed') {
                this.dispatchEvent(new ShowToastEvent({
                    title: 'Committed',
                    message: `Document ${parsed.document_id}`,
                    variant: 'success',
                }));
            } else if (parsed.status === 'pending_approval') {
                this.dispatchEvent(new ShowToastEvent({
                    title: 'Pending approval',
                    message: parsed.message || 'Routed to Approvals.',
                    variant: 'info',
                }));
            } else {
                this.dispatchEvent(new ShowToastEvent({
                    title: parsed.status,
                    message: parsed.message || 'Commit did not succeed',
                    variant: 'warning',
                }));
            }
        } catch (err) {
            this.hasError = true;
            this.errorMessage = err.body?.message || err.message || 'Commit failed';
        } finally {
            this.isCommitting = false;
        }
    }

    handleEdit() {
        this.result = null;
        this.commitResult = null;
        this.hasError = false;
    }

    handleReset() {
        this.promptText = '';
        this.result = null;
        this.commitResult = null;
        this.hasError = false;
        this.errorMessage = '';
        this.isProcessing = false;
        this.isCommitting = false;
    }

    handleOpenOpp() {
        if (!this.selectedOpportunityId) return;
        this[NavigationMixin.Navigate]({
            type: 'standard__recordPage',
            attributes: {
                recordId: this.selectedOpportunityId,
                objectApiName: 'Opportunity',
                actionName: 'view',
            },
        });
    }
}
