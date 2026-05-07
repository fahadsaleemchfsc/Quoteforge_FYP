/**
 * QuoteForge LWC — Uses Apex callouts to reach QuoteForge backend.
 * Salesforce Locker Service blocks direct fetch() to external APIs,
 * so we go through Apex (server-side) which is allowed.
 */

import { LightningElement, api, wire } from 'lwc';
import { getRecord, getFieldValue } from 'lightning/uiRecordApi';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import generateProposal from '@salesforce/apex/QuoteForgeController.generateProposal';
import downloadDocument from '@salesforce/apex/QuoteForgeController.downloadDocument';

import OPP_NAME from '@salesforce/schema/Opportunity.Name';
import OPP_AMOUNT from '@salesforce/schema/Opportunity.Amount';
import OPP_STAGE from '@salesforce/schema/Opportunity.StageName';
import ACCOUNT_NAME from '@salesforce/schema/Opportunity.Account.Name';

const FIELDS = [OPP_NAME, OPP_AMOUNT, OPP_STAGE, ACCOUNT_NAME];

export default class QuoteForgeGenerator extends LightningElement {
    @api recordId;

    outputFormat = 'PDF';
    isGenerating = false;
    isComplete = false;
    hasError = false;

    statusMessage = '';
    errorMessage = '';
    generatedDocId = '';
    generationTime = '';
    pricingData = null;

    @wire(getRecord, { recordId: '$recordId', fields: FIELDS })
    opportunity;

    get formatOptions() {
        return [
            { label: 'PDF', value: 'PDF' },
            { label: 'DOCX', value: 'DOCX' },
        ];
    }

    get isConnected() { return true; }
    get oppName() { return getFieldValue(this.opportunity.data, OPP_NAME); }
    get oppAmount() { return getFieldValue(this.opportunity.data, OPP_AMOUNT); }

    get dealSummary() {
        if (!this.opportunity?.data) return '';
        const name = getFieldValue(this.opportunity.data, ACCOUNT_NAME);
        const amount = getFieldValue(this.opportunity.data, OPP_AMOUNT);
        return `${name} — $${Number(amount || 0).toLocaleString()}`;
    }

    handleFormatChange(event) {
        this.outputFormat = event.detail.value;
    }

    async handleGenerate() {
        this.isGenerating = true;
        this.isComplete = false;
        this.hasError = false;
        this.pricingData = null;
        this.statusMessage = 'Generating proposal via QuoteForge AI...';

        try {
            const resultJson = await generateProposal({
                opportunityId: this.recordId,
                outputFormat: this.outputFormat,
            });

            const result = JSON.parse(resultJson);

            if (result.error) {
                throw new Error(result.error);
            }

            this.generatedDocId = result.doc_id;
            this.generationTime = result.generation_time;
            this.pricingData = {
                subtotal: Number(result.pricing?.subtotal || 0).toLocaleString(),
                discount: Number(result.pricing?.discount || 0).toLocaleString(),
                tax: Number(result.pricing?.tax || 0).toLocaleString(),
                total: Number(result.pricing?.total || 0).toLocaleString(),
                compliance_framework: result.pricing?.compliance_framework || '',
            };

            this.isComplete = true;

            this.dispatchEvent(new ShowToastEvent({
                title: 'Proposal Generated!',
                message: `${result.doc_id} — $${this.pricingData.total} — ${result.generation_time}s`,
                variant: 'success',
            }));

        } catch (error) {
            this.hasError = true;
            this.errorMessage = error.body?.message || error.message || 'Generation failed';
            this.dispatchEvent(new ShowToastEvent({
                title: 'Error',
                message: this.errorMessage,
                variant: 'error',
            }));
        } finally {
            this.isGenerating = false;
        }
    }

    async handleDownload() {
        if (!this.generatedDocId) return;
        try {
            // Apex fetches the PDF with JWT auth and hands us back base64.
            // `callout:QuoteForge_API/...` only resolves inside Apex — a
            // browser-side window.open on that string is a no-op.
            const raw = await downloadDocument({ docId: this.generatedDocId });
            const payload = JSON.parse(raw);
            if (payload.error) throw new Error(payload.error);

            // base64 → Uint8Array → Blob → object URL → trigger download.
            const byteString = atob(payload.content_base64);
            const bytes = new Uint8Array(byteString.length);
            for (let i = 0; i < byteString.length; i++) {
                bytes[i] = byteString.charCodeAt(i);
            }
            const blob = new Blob([bytes], { type: payload.content_type });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = payload.filename || (this.generatedDocId + '.pdf');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 2000);

            this.dispatchEvent(new ShowToastEvent({
                title: 'Download started',
                message: payload.filename,
                variant: 'success',
            }));
        } catch (error) {
            this.dispatchEvent(new ShowToastEvent({
                title: 'Download failed',
                message: error?.body?.message || error?.message || 'Unknown error',
                variant: 'error',
            }));
        }
    }

    handleSend() {
        this.dispatchEvent(new ShowToastEvent({
            title: 'Sent!',
            message: 'Proposal sent to client (simulated)',
            variant: 'success',
        }));
    }
}
