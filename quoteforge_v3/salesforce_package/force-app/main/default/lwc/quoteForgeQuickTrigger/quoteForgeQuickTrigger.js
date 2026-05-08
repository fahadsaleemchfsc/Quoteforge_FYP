/**
 * QuoteForge Quick Trigger
 * ==========================
 * The simplest possible UX: one input, one button.
 * Works from Home, App, or any record page.
 */
import { LightningElement, api } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import quickGenerate from '@salesforce/apex/QuoteForgeController.quickGenerate';
import downloadDocument from '@salesforce/apex/QuoteForgeController.downloadDocument';
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
            let raw = error.body?.message || error.message || 'Generation failed';
            // Apex wraps backend errors as "{statusCode} - {responseBody}". When
            // responseBody is FastAPI's `{"detail": "..."}` shape, surface only
            // the detail string instead of the concatenated raw form.
            const dashIdx = raw.indexOf(' - ');
            if (dashIdx > -1) {
                const tail = raw.slice(dashIdx + 3).trim();
                try {
                    const parsed = JSON.parse(tail);
                    if (parsed && typeof parsed.detail === 'string') {
                        raw = parsed.detail;
                    }
                } catch (_e) {
                    // tail wasn't JSON — leave raw as the concatenated string.
                }
            }
            this.errorMessage = raw;
        } finally {
            this.isProcessing = false;
        }
    }

    async handleDownload() {
        try {
            const resultJson = await downloadDocument({ docId: this.generatedDocId });
            const result = JSON.parse(resultJson);
            if (result.error) throw new Error(result.error);

            // Decode base64 PDF/DOCX bytes into a Blob and trigger a browser
            // save via a synthetic <a download> click. window.open against the
            // backend doesn't work because (a) callout: URLs aren't browser-
            // resolvable and (b) the endpoint requires JWT auth the browser
            // tab doesn't carry.
            const binary = atob(result.content_base64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const blob = new Blob([bytes], { type: result.content_type || 'application/pdf' });
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = objectUrl;
            a.download = result.filename || `${this.generatedDocId}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(objectUrl);
        } catch (error) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Download Error',
                message: error.message || 'Failed to download document',
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
