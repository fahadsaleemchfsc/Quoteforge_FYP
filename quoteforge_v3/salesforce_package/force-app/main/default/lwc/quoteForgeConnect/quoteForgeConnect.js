import { LightningElement, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import getStatus from '@salesforce/apex/QuoteForgeConnectController.getStatus';
import getAuthorizeUrl from '@salesforce/apex/QuoteForgeConnectController.getAuthorizeUrl';
import disconnect from '@salesforce/apex/QuoteForgeConnectController.disconnect';

// Poll cadence + cap while the OAuth popup is open. 3s × 100 = 5 min,
// which comfortably covers password reset / MFA flows.
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_TICKS = 100;

export default class QuoteForgeConnect extends LightningElement {
    @track loading = true;
    @track busy = false;
    @track status = null;        // backend /status response payload
    @track errorMessage = '';
    _pollHandle = null;
    _pollTicks = 0;

    connectedCallback() {
        this.refreshStatus();
    }

    disconnectedCallback() {
        this.stopPolling();
    }

    async refreshStatus() {
        this.loading = true;
        this.errorMessage = '';
        try {
            this.status = await getStatus();
        } catch (e) {
            this.errorMessage = this.extractError(e);
        } finally {
            this.loading = false;
        }
    }

    // ─── derived state for the template ──────────────────────────────

    get connected() {
        return Boolean(this.status && this.status.connected);
    }

    get configured() {
        // Treat missing field as configured=true so older backends that
        // don't ship the flag still render the Connect button.
        return !this.status || this.status.configured !== false;
    }

    get pillVariant() {
        if (!this.configured) return 'warning';
        return this.connected ? 'success' : 'inverse';
    }

    get pillLabel() {
        if (!this.configured) return 'Backend not configured';
        if (this.connected) {
            const org = this.status.org_id || 'connected org';
            return `Connected · ${org}`;
        }
        return 'Not connected';
    }

    get primaryActionLabel() {
        return this.connected ? 'Disconnect' : 'Connect to Salesforce';
    }

    get primaryActionVariant() {
        return this.connected ? 'destructive-text' : 'brand';
    }

    get instanceUrl() {
        return this.status ? this.status.instance_url : '';
    }

    get scopes() {
        return this.status ? this.status.scopes : '';
    }

    // ─── actions ─────────────────────────────────────────────────────

    async handlePrimaryClick() {
        if (this.busy) return;
        if (this.connected) {
            await this.handleDisconnect();
        } else {
            await this.handleConnect();
        }
    }

    async handleConnect() {
        this.busy = true;
        this.errorMessage = '';
        try {
            const url = await getAuthorizeUrl();
            // window.open requires a user gesture — handleConnect is fired
            // from a click handler, so this is allowed by Lightning CSP.
            const popup = window.open(
                url,
                'quoteforge-sf-oauth',
                'width=600,height=720'
            );
            if (!popup) {
                throw new Error(
                    'Popup was blocked. Allow pop-ups for this site and try again.'
                );
            }
            this.startPolling();
        } catch (e) {
            this.errorMessage = this.extractError(e);
        } finally {
            this.busy = false;
        }
    }

    async handleDisconnect() {
        this.busy = true;
        this.errorMessage = '';
        try {
            await disconnect();
            this.dispatchEvent(
                new ShowToastEvent({
                    title: 'Disconnected',
                    message: 'QuoteForge is no longer linked to a Salesforce org.',
                    variant: 'success',
                })
            );
            await this.refreshStatus();
        } catch (e) {
            this.errorMessage = this.extractError(e);
        } finally {
            this.busy = false;
        }
    }

    // ─── status polling while the OAuth popup is open ───────────────

    startPolling() {
        this.stopPolling();
        this._pollTicks = 0;
        this._pollHandle = setInterval(() => this.pollTick(), POLL_INTERVAL_MS);
    }

    stopPolling() {
        if (this._pollHandle) {
            clearInterval(this._pollHandle);
            this._pollHandle = null;
        }
    }

    async pollTick() {
        this._pollTicks += 1;
        try {
            const next = await getStatus();
            if (next && next.connected) {
                this.status = next;
                this.stopPolling();
                this.dispatchEvent(
                    new ShowToastEvent({
                        title: 'Connected',
                        message: `Linked to org ${next.org_id}.`,
                        variant: 'success',
                    })
                );
                return;
            }
        } catch (e) {
            // Transient — keep polling unless we've exceeded the cap.
            // Show the error only after we give up so a slow Salesforce
            // login doesn't flash red mid-flow.
        }
        if (this._pollTicks >= POLL_MAX_TICKS) {
            this.stopPolling();
            this.errorMessage =
                'Timed out waiting for the OAuth popup. Close it and click Connect again.';
        }
    }

    extractError(e) {
        if (!e) return 'Unknown error';
        if (e.body && e.body.message) return e.body.message;
        if (e.message) return e.message;
        return String(e);
    }
}
