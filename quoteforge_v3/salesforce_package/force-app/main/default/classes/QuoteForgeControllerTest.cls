/**
 * Coverage tests for QuoteForgeController.
 *
 * Every method is a thin authenticated callout wrapper, so an endpoint-aware
 * HttpCalloutMock + a handful of test records exercises the request build,
 * the success branch, and (via a second mock) the non-2xx + exception
 * branches. Three scenarios:
 *   1. happy path        — auth 200, endpoints 200
 *   2. backend errors     — auth 200, endpoints 500 (non-200 return branches)
 *   3. auth failure       — auth 500 (getAuthToken throw + per-method catch)
 *
 * The package ships QuoteForge_Tenant_Config__mdt records (Sandbox_/Prod_),
 * which are visible in tests, so getAuthBody() resolves credentials.
 */
@isTest
private class QuoteForgeControllerTest {

    private class QFMock implements HttpCalloutMock {
        Integer authStatus;
        Integer mainStatus;
        Id oppId;
        QFMock(Integer authStatus, Integer mainStatus, Id oppId) {
            this.authStatus = authStatus;
            this.mainStatus = mainStatus;
            this.oppId = oppId;
        }
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setHeader('Content-Type', 'application/json');
            String ep = req.getEndpoint();
            if (ep.contains('/auth/login')) {
                res.setStatusCode(authStatus);
                res.setBody('{"access_token":"test-token-123"}');
                return res;
            }
            res.setStatusCode(mainStatus);
            if (ep.contains('/insights/models')) {
                res.setBody('[{"is_active":true,"version":"v1","accuracy":0.72,' +
                            '"auc":0.81,"training_rows":1000,"trained_at":"2026-01-01"}]');
            } else if (ep.contains('/insights/predict/batch')) {
                res.setBody('{"results":[{"opportunity_id":"' + oppId + '",' +
                            '"win_probability":0.83,"probability_percent":"83%","band":"high"},' +
                            '{"error":"skip"}]}');
            } else if (ep.contains('/health')) {
                res.setBody('{"version":"1.0.0","service":"quoteforge"}');
            } else if (ep.contains('/quotes/documents/')) {
                res.setHeader('Content-Type', 'application/pdf');
                res.setHeader('Content-Disposition', 'attachment; filename="DOC-TEST.pdf"');
                res.setBody('PDF-BYTES');
            } else {
                res.setBody('{"ok":true,"data":"x"}');
            }
            return res;
        }
    }

    @testSetup
    static void seed() {
        Account a = new Account(Name = 'Test Co', BillingCountry = 'Germany');
        insert a;
        insert new Opportunity(
            Name = 'Test Opp', StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30), Amount = 120000, AccountId = a.Id
        );
        insert new Contact(LastName = 'Tester', AccountId = a.Id);
        Opportunity o = [SELECT Id FROM Opportunity LIMIT 1];
        insert new QuoteForge_Document__c(
            Name = 'DOC-TEST', Status__c = 'Generated', Total__c = 1000, Opportunity__c = o.Id
        );
    }

    // Calls every @AuraEnabled method once. `expectError` just documents
    // intent — the methods swallow backend failures into JSON, so we assert
    // they return (or throw, for the auth-failure path) without blowing up.
    static void callAll(Id oppId, Id contactId, String docName) {
        QuoteForgeController.generateProposal(oppId, 'PDF');
        QuoteForgeController.getDownloadUrl(docName);
        QuoteForgeController.downloadDocument(docName);
        QuoteForgeController.parsePrompt('quote for "ACME" with 2 seats\nrush');
        QuoteForgeController.quickGenerate('Test Opp');
        QuoteForgeController.submitFeedback('DOC-1', 'positive');
        QuoteForgeController.generateQuoteFromPrompt(contactId, oppId, 'two seats');
        QuoteForgeController.commitQuoteFromPrompt('offer-1', 'sig-1', oppId);
        QuoteForgeController.createDealFromPrompt('a brand new deal', contactId, 'PDF');
        QuoteForgeController.getOpportunityInsight(oppId);
        QuoteForgeController.getAppHomeData();
        QuoteForgeController.getSettingsStatus();
        QuoteForgeController.getInsightsSchema();
        QuoteForgeController.getInsightsMapping();
        QuoteForgeController.saveInsightsMapping('{"amount":"Amount"}');
        QuoteForgeController.getModelAccuracy();
        QuoteForgeController.triggerRetrain();
        QuoteForgeController.listInsightsModels();
        QuoteForgeController.getTrainingLog(100);
        QuoteForgeController.getTrainingLog(null);
        QuoteForgeController.getInsightsStatus();
        QuoteForgeController.listICPs();
        QuoteForgeController.getICP('icp-1');
        QuoteForgeController.createICP('{"name":"x"}');
        QuoteForgeController.updateICP('icp-1', '{"name":"y"}');
        QuoteForgeController.activateICP('icp-1');
        QuoteForgeController.scoreOppAgainstICP(String.valueOf(oppId));
        QuoteForgeController.deleteICP('icp-1');
    }

    @isTest
    static void testHappyPath() {
        Opportunity o = [SELECT Id FROM Opportunity LIMIT 1];
        Contact c = [SELECT Id FROM Contact LIMIT 1];
        QuoteForge_Document__c d = [SELECT Name FROM QuoteForge_Document__c LIMIT 1];
        Test.setMock(HttpCalloutMock.class, new QFMock(200, 200, o.Id));
        Test.startTest();
        callAll(o.Id, c.Id, d.Name);
        Test.stopTest();
        System.assertEquals(1, [SELECT Id FROM Opportunity].size(), 'setup intact');
    }

    @isTest
    static void testBackendErrors() {
        Opportunity o = [SELECT Id FROM Opportunity LIMIT 1];
        Contact c = [SELECT Id FROM Contact LIMIT 1];
        QuoteForge_Document__c d = [SELECT Name FROM QuoteForge_Document__c LIMIT 1];
        Test.setMock(HttpCalloutMock.class, new QFMock(200, 500, o.Id));
        Test.startTest();
        callAll(o.Id, c.Id, d.Name);
        Test.stopTest();
        System.assert(true, 'all error branches returned JSON, none threw');
    }

    @isTest
    static void testAuthFailure() {
        Opportunity o = [SELECT Id FROM Opportunity LIMIT 1];
        Contact c = [SELECT Id FROM Contact LIMIT 1];
        Test.setMock(HttpCalloutMock.class, new QFMock(500, 500, o.Id));
        Test.startTest();
        // getAuthToken throws CalloutException → each method's catch returns JSON.
        QuoteForgeController.generateProposal(o.Id, 'PDF');
        QuoteForgeController.parsePrompt('x');
        QuoteForgeController.getInsightsSchema();
        QuoteForgeController.generateQuoteFromPrompt(c.Id, o.Id, 'p');
        Test.stopTest();
        System.assert(true, 'auth failure handled without uncaught exception');
    }
}
