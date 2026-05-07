/**
 * QuoteForge Deal Builder LWC
 * =============================
 * Natural language → Salesforce Opportunity + AI-generated proposal
 *
 * Flow:
 *  1. User types prompt on Contact page
 *  2. (Optional) Preview extraction
 *  3. Click "Create Deal + Proposal"
 *  4. Apex callout to QuoteForge backend
 *  5. Backend creates Account (if needed), Opportunity, LineItems, Proposal
 *  6. Returns Opportunity ID and Document ID
 *  7. User can view Opportunity or download PDF
 */

import { LightningElement, api } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { NavigationMixin } from 'lightning/navigation';
import parsePrompt from '@salesforce/apex/QuoteForgeController.parsePrompt';
import createDealFromPrompt from '@salesforce/apex/QuoteForgeController.createDealFromPrompt';
import getDownloadUrl from '@salesforce/apex/QuoteForgeController.getDownloadUrl';

export default class QuoteForgeDealBuilder extends NavigationMixin(LightningElement) {
    @api recordId;  // Contact ID (when placed on Contact page)

    promptText = '';
    isProcessing = false;
    showPreview = false;
    isComplete = false;
    hasError = false;

    statusMessage = '';
    errorMessage = '';
    parsed = null;
    generatedDocId = '';
    opportunityId = '';
    pricingData = null;
    validUntilDisplay = '';

    examples = [
        { id: 1, label: 'US Enterprise', prompt: 'Create a proposal for Acme Corporation. They need Enterprise License for $50,000, Implementation Services for $15,000, and Annual Support for $10,000.' },
        { id: 2, label: 'Pakistan PPRA', prompt: 'Generate a proposal for Punjab IT Board in Pakistan. They need Document Management System for $30,000, PPRA Compliance Module for $10,000, and Training Services for $5,000.' },
        { id: 3, label: 'SaaS Deal', prompt: 'Quote for TechStart Inc: SaaS subscription for $25K, onboarding services for $8K.' },
    ];

    get isPromptEmpty() {
        return !this.promptText || this.promptText.trim().length < 10;
    }

    get hasResult() {
        return this.isComplete || this.hasError || this.showPreview;
    }

    get parsedTotal() {
        if (!this.parsed || !this.parsed.deal_amount) return '0.00';
        return Number(this.parsed.deal_amount).toLocaleString();
    }

    get lineItemCount() {
        return this.parsed?.line_items?.length || 0;
    }

    handlePromptChange(event) {
        this.promptText = event.target.value;
    }

    useExample(event) {
        const id = parseInt(event.currentTarget.dataset.id);
        const example = this.examples.find(e => e.id === id);
        if (example) {
            this.promptText = example.prompt;
        }
    }

    async handlePreview() {
        this.isProcessing = true;
        this.statusMessage = 'Analyzing prompt...';
        this.hasError = false;

        try {
            const resultJson = await parsePrompt({ prompt: this.promptText });
            const result = JSON.parse(resultJson);

            if (result.error) throw new Error(result.error);

            this.parsed = result.parsed;
            this.showPreview = true;

            this.dispatchEvent(new ShowToastEvent({
                title: 'Preview Ready',
                message: `Extracted ${this.lineItemCount} items for ${this.parsed.client_name}`,
                variant: 'info',
            }));
        } catch (error) {
            this.hasError = true;
            this.errorMessage = error.message || 'Failed to parse prompt';
        } finally {
            this.isProcessing = false;
        }
    }

    async handleCreate() {
        this.isProcessing = true;
        this.showPreview = false;
        this.statusMessage = 'Creating Opportunity in Salesforce...';
        this.hasError = false;

        try {
            // Progressive status updates
            setTimeout(() => { if (this.isProcessing) this.statusMessage = 'Applying pricing rules & compliance...'; }, 3000);
            setTimeout(() => { if (this.isProcessing) this.statusMessage = 'AI generating proposal sections...'; }, 8000);
            setTimeout(() => { if (this.isProcessing) this.statusMessage = 'Rendering document...'; }, 20000);

            const resultJson = await createDealFromPrompt({
                prompt: this.promptText,
                contactId: this.recordId,
                outputFormat: 'PDF',
            });
            const result = JSON.parse(resultJson);

            if (result.error) throw new Error(result.error);

            this.generatedDocId = result.doc_id;
            this.opportunityId = result.salesforce_opportunity_id;
            this.pricingData = result.pricing ? {
                subtotal: Number(result.pricing.subtotal || 0).toLocaleString(),
                discount: Number(result.pricing.discount || 0).toLocaleString(),
                tax: Number(result.pricing.tax || 0).toLocaleString(),
                total: Number(result.pricing.total || 0).toLocaleString(),
            } : null;

            if (result.valid_until) {
                this.validUntilDisplay = new Date(result.valid_until).toLocaleDateString('en-US',
                    { year: 'numeric', month: 'long', day: 'numeric' });
            }

            this.isComplete = true;

            this.dispatchEvent(new ShowToastEvent({
                title: 'Success!',
                message: `Opportunity created, proposal ${this.generatedDocId} generated`,
                variant: 'success',
            }));

        } catch (error) {
            this.hasError = true;
            this.errorMessage = error.body?.message || error.message || 'Creation failed';

            this.dispatchEvent(new ShowToastEvent({
                title: 'Error',
                message: this.errorMessage,
                variant: 'error',
            }));
        } finally {
            this.isProcessing = false;
        }
    }

    handleViewOpportunity() {
        this[NavigationMixin.Navigate]({
            type: 'standard__recordPage',
            attributes: {
                recordId: this.opportunityId,
                objectApiName: 'Opportunity',
                actionName: 'view',
            },
        });
    }

    async handleDownload() {
        if (!this.generatedDocId) return;
        try {
            const url = await getDownloadUrl({ docId: this.generatedDocId });
            window.open(url, '_blank');
        } catch (error) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Download Error',
                message: 'Failed to get download link',
                variant: 'error',
            }));
        }
    }

    handleReset() {
        this.promptText = '';
        this.isProcessing = false;
        this.showPreview = false;
        this.isComplete = false;
        this.hasError = false;
        this.parsed = null;
        this.generatedDocId = '';
        this.opportunityId = '';
        this.pricingData = null;
        this.errorMessage = '';
    }
}
