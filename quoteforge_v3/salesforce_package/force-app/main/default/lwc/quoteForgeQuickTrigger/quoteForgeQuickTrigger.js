/**
 * QuoteForge Quick Trigger
 * ==========================
 * The simplest possible UX: one input, one button.
 * Works from Home, App, or any record page.
 */
import { LightningElement, api } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import quickGenerate from '@salesforce/apex/QuoteForgeController.quickGenerate';
import getDownloadUrl from '@salesforce/apex/QuoteForgeController.getDownloadUrl';
import submitFeedback from '@salesforce/apex/QuoteForgeController.submitFeedback';

export default class QuoteForgeQuickTrigger extends LightningElement {
    @api recordId;

    identifier = '';
    isProcessing = false;
    isComplete = false;
    hasError = false;

    statusMessage = '';
    errorMessage = '';
    generatedDocId = '';
    resolvedClient = '';
    totalAmount = '';
    validUntilDisplay = '';

    get isInputEmpty() {
        return !this.identifier || this.identifier.trim().length < 3;
    }

    handleInput(event) {
        this.identifier = event.target.value;
    }

    handleKeyup(event) {
        if (event.keyCode === 13 && !this.isInputEmpty) {
            this.handleGenerate();
        }
    }

    async handleGenerate() {
        this.isProcessing = true;
        this.hasError = false;
        this.isComplete = false;
        this.statusMessage = `Finding "${this.identifier}"...`;

        setTimeout(() => { if (this.isProcessing) this.statusMessage = 'Fetching deal data...'; }, 2000);
        setTimeout(() => { if (this.isProcessing) this.statusMessage = 'Applying pricing & compliance...'; }, 5000);
        setTimeout(() => { if (this.isProcessing) this.statusMessage = 'AI generating proposal sections...'; }, 10000);
        setTimeout(() => { if (this.isProcessing) this.statusMessage = 'Rendering document...'; }, 30000);

        try {
            const resultJson = await quickGenerate({ identifier: this.identifier });
            const result = JSON.parse(resultJson);

            if (result.error) throw new Error(result.error);

            this.generatedDocId = result.doc_id;
            this.resolvedClient = result.client;
            this.totalAmount = Number(result.pricing?.total || 0).toLocaleString();

            if (result.valid_until) {
                this.validUntilDisplay = new Date(result.valid_until).toLocaleDateString('en-US',
                    { year: 'numeric', month: 'long', day: 'numeric' });
            }

            this.isComplete = true;

            this.dispatchEvent(new ShowToastEvent({
                title: 'Generated!',
                message: `${this.generatedDocId} — ${this.resolvedClient}`,
                variant: 'success',
            }));
        } catch (error) {
            this.hasError = true;
            this.errorMessage = error.body?.message || error.message || 'Generation failed';
        } finally {
            this.isProcessing = false;
        }
    }

    async handleDownload() {
        try {
            const url = await getDownloadUrl({ docId: this.generatedDocId });
            window.open(url, '_blank');
        } catch (error) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Download Error',
                message: 'Failed to get link',
                variant: 'error',
            }));
        }
    }

    async handleApprove() {
        try {
            await submitFeedback({ docId: this.generatedDocId, feedbackType: 'approved' });
            this.dispatchEvent(new ShowToastEvent({
                title: 'Approved!',
                message: 'Model will learn from this proposal.',
                variant: 'success',
            }));
        } catch (error) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Feedback Failed',
                message: error.body?.message || 'Could not submit feedback',
                variant: 'error',
            }));
        }
    }

    handleReset() {
        this.identifier = '';
        this.isProcessing = false;
        this.isComplete = false;
        this.hasError = false;
        this.generatedDocId = '';
        this.resolvedClient = '';
        this.totalAmount = '';
        this.validUntilDisplay = '';
        this.errorMessage = '';
    }
}
