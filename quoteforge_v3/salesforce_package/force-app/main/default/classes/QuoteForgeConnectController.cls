/**
 * QuoteForgeConnectController — backs the quoteForgeConnect LWC.
 *
 * The LWC needs three actions:
 *   getStatus()       → is this tenant currently connected to a SF org?
 *   getAuthorizeUrl() → URL to open in window.open() for OAuth consent.
 *   disconnect()      → revoke + clear the stored token.
 *
 * All three round-trip through the QuoteForge backend via the Named
 * Credential `QuoteForge_API`. The JWT is fetched once per transaction by
 * delegating to QuoteForgeController.getAuthToken() (which already reads
 * credentials from QuoteForge_Tenant_Config__mdt).
 */
public with sharing class QuoteForgeConnectController {

    private static final String QUOTEFORGE_API = 'callout:QuoteForge_API';
    private static final Integer TIMEOUT_MS = 15000;

    private static HttpRequest authedRequest(String path, String method) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint(QUOTEFORGE_API + path);
        req.setMethod(method);
        req.setHeader('Accept', 'application/json');
        req.setHeader('Authorization', 'Bearer ' + QuoteForgeController.getAuthToken());
        req.setTimeout(TIMEOUT_MS);
        return req;
    }

    private static Map<String, Object> sendJson(HttpRequest req) {
        HttpResponse res = new Http().send(req);
        Integer code = res.getStatusCode();
        if (code < 200 || code >= 300) {
            throw new CalloutException(
                'QuoteForge backend returned ' + code + ': ' + res.getBody()
            );
        }
        String body = res.getBody();
        if (String.isBlank(body)) return new Map<String, Object>();
        return (Map<String, Object>) JSON.deserializeUntyped(body);
    }

    /**
     * Returns {connected, configured, org_id, instance_url, scopes,
     * connected_at}. The LWC polls this every couple seconds while the
     * OAuth popup is open.
     */
    @AuraEnabled(cacheable=false)
    public static Map<String, Object> getStatus() {
        try {
            return sendJson(authedRequest('/api/integrations/salesforce/status', 'GET'));
        } catch (Exception e) {
            // Surface as AuraHandledException so the LWC sees a clean
            // error message rather than a stack trace.
            AuraHandledException ahe = new AuraHandledException(e.getMessage());
            ahe.setMessage(e.getMessage());
            throw ahe;
        }
    }

    /**
     * Builds a tenant-scoped Salesforce OAuth authorize URL on the
     * backend and returns it. The LWC opens this in a popup; on consent
     * Salesforce redirects to the backend's /callback which stores the
     * token and bounces to the success page.
     */
    @AuraEnabled(cacheable=false)
    public static String getAuthorizeUrl() {
        try {
            Map<String, Object> body = sendJson(
                authedRequest('/api/integrations/salesforce/init', 'GET')
            );
            String url = (String) body.get('authorize_url');
            if (String.isBlank(url)) {
                throw new CalloutException('Backend did not return authorize_url');
            }
            return url;
        } catch (Exception e) {
            AuraHandledException ahe = new AuraHandledException(e.getMessage());
            ahe.setMessage(e.getMessage());
            throw ahe;
        }
    }

    /**
     * Revoke the tenant's Salesforce token at Salesforce and delete the
     * row from the backend store. Idempotent — calling when not connected
     * still returns {disconnected: true, had_token: false}.
     */
    @AuraEnabled(cacheable=false)
    public static Map<String, Object> disconnect() {
        try {
            return sendJson(
                authedRequest('/api/integrations/salesforce/disconnect', 'POST')
            );
        } catch (Exception e) {
            AuraHandledException ahe = new AuraHandledException(e.getMessage());
            ahe.setMessage(e.getMessage());
            throw ahe;
        }
    }
}
