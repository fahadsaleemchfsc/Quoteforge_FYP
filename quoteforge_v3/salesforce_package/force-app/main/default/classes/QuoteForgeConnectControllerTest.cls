/**
 * Coverage tests for QuoteForgeConnectController (getStatus / getAuthorizeUrl
 * / disconnect). Endpoint-aware mock drives the auth callout + the status/
 * init/disconnect callouts; a 500 variant exercises the sendJson non-2xx
 * throw and each method's AuraHandledException catch.
 */
@isTest
private class QuoteForgeConnectControllerTest {

    private class ConnMock implements HttpCalloutMock {
        Integer authStatus;
        Integer mainStatus;
        ConnMock(Integer authStatus, Integer mainStatus) {
            this.authStatus = authStatus;
            this.mainStatus = mainStatus;
        }
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setHeader('Content-Type', 'application/json');
            String ep = req.getEndpoint();
            if (ep.contains('/auth/login')) {
                res.setStatusCode(authStatus);
                res.setBody('{"access_token":"tok"}');
                return res;
            }
            res.setStatusCode(mainStatus);
            if (ep.contains('/init')) {
                res.setBody('{"authorize_url":"https://login.salesforce.com/oauth/authorize?x=1"}');
            } else {
                res.setBody('{"connected":true,"configured":true,"org_id":"00Dxx"}');
            }
            return res;
        }
    }

    @isTest
    static void testHappyPath() {
        Test.setMock(HttpCalloutMock.class, new ConnMock(200, 200));
        Test.startTest();
        Map<String, Object> status = QuoteForgeConnectController.getStatus();
        String url = QuoteForgeConnectController.getAuthorizeUrl();
        Map<String, Object> disc = QuoteForgeConnectController.disconnect();
        Test.stopTest();
        System.assertEquals(true, status.get('connected'), 'status parsed');
        System.assert(url.startsWith('https://'), 'authorize_url returned');
        System.assertNotEquals(null, disc, 'disconnect returned a map');
    }

    @isTest
    static void testBackendError() {
        Test.setMock(HttpCalloutMock.class, new ConnMock(200, 500));
        Test.startTest();
        Integer thrown = 0;
        try { QuoteForgeConnectController.getStatus(); }       catch (Exception e) { thrown++; }
        try { QuoteForgeConnectController.getAuthorizeUrl(); }  catch (Exception e) { thrown++; }
        try { QuoteForgeConnectController.disconnect(); }       catch (Exception e) { thrown++; }
        Test.stopTest();
        System.assertEquals(3, thrown, 'each method surfaced the backend error');
    }
}
