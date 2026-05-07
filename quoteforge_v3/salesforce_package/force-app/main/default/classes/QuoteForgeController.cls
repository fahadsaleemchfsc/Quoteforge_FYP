/**
 * QuoteForgeController — API bridge between Salesforce and QuoteForge backend.
 *
 * Backend URL is resolved via the Named Credential `QuoteForge_API`, which
 * the org admin configures once at install time (see salesforce_package/README.md).
 * No hardcoded URLs — rotating ngrok/Cloudflare tunnels, switching between
 * sandbox and production, or moving to a real HTTPS endpoint is a one-field
 * change in Salesforce Setup.
 *
 * Authentication credentials are loaded from QuoteForge_Tenant_Config__mdt
 * Custom Metadata Type at runtime. The record used depends on whether the
 * org is a Sandbox (DeveloperName=Sandbox_Tenant) or Production (Prod_Tenant).
 *
 * To customize per-tenant credentials, edit the corresponding metadata record
 * in Setup → Custom Metadata Types → QuoteForge Tenant Config → Manage Records.
 */
public with sharing class QuoteForgeController {

    // Named Credential prefix. The admin configures the actual endpoint
    // (e.g. https://api.quoteforge.io) once in Setup → Named Credentials.
    // Apex concatenation works: 'callout:QuoteForge_API' + '/path' resolves
    // to the Named Credential's URL with /path appended.
    private static final String QUOTEFORGE_API = 'callout:QuoteForge_API';
    private static String cachedToken;

    // Per-transaction cache of the auth payload read from Custom Metadata.
    // Avoids a second SOQL hit during the same Apex transaction. Cleared
    // automatically at the end of the request because static fields live
    // only for the duration of the execution context.
    private static String cachedAuthBody;

    /**
     * Build the JSON body for /auth/login. Reads credentials from
     * QuoteForge_Tenant_Config__mdt. Sandbox orgs use DeveloperName
     * `Sandbox_Tenant`; production orgs use `Prod_Tenant`.
     */
    private static String getAuthBody() {
        if (cachedAuthBody != null) return cachedAuthBody;

        String tenantDeveloperName =
            [SELECT IsSandbox FROM Organization LIMIT 1].IsSandbox
            ? 'Sandbox_Tenant'
            : 'Prod_Tenant';

        List<QuoteForge_Tenant_Config__mdt> configs = [
            SELECT Auth_Email__c, Auth_Password__c, Tenant_Slug__c
            FROM QuoteForge_Tenant_Config__mdt
            WHERE DeveloperName = :tenantDeveloperName
            LIMIT 1
        ];

        if (configs.isEmpty()) {
            throw new CalloutException(
                'No QuoteForge_Tenant_Config__mdt found for ' + tenantDeveloperName +
                '. Create a Custom Metadata record in Setup → Custom Metadata Types ' +
                '→ QuoteForge Tenant Config → Manage Records.'
            );
        }

        QuoteForge_Tenant_Config__mdt cfg = configs[0];
        cachedAuthBody = JSON.serialize(new Map<String, String>{
            'email' => cfg.Auth_Email__c,
            'password' => cfg.Auth_Password__c
        });
        return cachedAuthBody;
    }

    private static String getAuthToken() {
        if (cachedToken != null) return cachedToken;

        HttpRequest req = new HttpRequest();
        req.setEndpoint(QUOTEFORGE_API + '/auth/login');
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setHeader('ngrok-skip-browser-warning', 'true');
        req.setBody(getAuthBody());
        req.setTimeout(30000);

        Http http = new Http();
        HttpResponse res = http.send(req);

        if (res.getStatusCode() == 200) {
            Map<String, Object> body = (Map<String, Object>) JSON.deserializeUntyped(res.getBody());
            cachedToken = (String) body.get('access_token');
            return cachedToken;
        }
        throw new CalloutException('QuoteForge auth failed: ' + res.getStatusCode() + ' ' + res.getBody());
    }

    @AuraEnabled(cacheable=false)
    public static String generateProposal(Id opportunityId, String outputFormat) {
        try {
            // Get Opportunity data
            Opportunity opp = [
                SELECT Id, Name, Amount, StageName, CloseDate,
                       Account.Name, Account.BillingCountry
                FROM Opportunity
                WHERE Id = :opportunityId
                LIMIT 1
            ];

            // Determine region
            String region = 'US';
            if (opp.Account != null && opp.Account.BillingCountry != null) {
                String country = opp.Account.BillingCountry.toUpperCase();
                if (country == 'PAKISTAN' || country == 'PK') {
                    region = 'PK';
                } else if (country == 'GERMANY' || country == 'FRANCE' || country == 'UNITED KINGDOM' || country == 'UK') {
                    region = 'EU';
                }
            }

            // Build payload
            Map<String, Object> payload = new Map<String, Object>();
            payload.put('deal_id', String.valueOf(opp.Id));
            payload.put('client_name', opp.Account != null ? opp.Account.Name : 'Client');
            payload.put('deal_name', opp.Name);
            payload.put('deal_amount', opp.Amount != null ? opp.Amount : 0);
            payload.put('contact_email', '');
            payload.put('region', region);
            payload.put('output_format', outputFormat != null ? outputFormat : 'PDF');
            payload.put('line_items', new List<Object>());

            // Call QuoteForge API
            String token = getAuthToken();

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/quotes/generate');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(JSON.serialize(payload));
            req.setTimeout(120000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                // Log activity
                Task activity = new Task(
                    WhatId = opportunityId,
                    Subject = 'QuoteForge: Proposal Generated',
                    Description = 'Auto-generated by QuoteForge.\n' + res.getBody(),
                    Status = 'Completed',
                    Priority = 'Normal',
                    ActivityDate = Date.today()
                );
                insert activity;

                return res.getBody();
            } else {
                return '{"error":"Generation failed: ' + res.getStatusCode() + '"}';
            }
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    @AuraEnabled
    public static String getDownloadUrl(String docId) {
        // Legacy — kept for any component still referencing the old method.
        // Prefer downloadDocument(docId) which returns the actual PDF bytes
        // base64-encoded. `callout:QuoteForge_API` is an Apex-only alias that
        // a browser can't resolve on its own, and the backend endpoint
        // requires JWT auth the LWC can't inject into window.open().
        return QUOTEFORGE_API + '/quotes/documents/' + docId + '/download';
    }

    /**
     * Fetch a generated document through an authenticated Apex callout and
     * return its bytes base64-encoded. The LWC decodes, wraps in a Blob,
     * and triggers a browser download via an <a download> click.
     *
     * Returns JSON: { doc_id, filename, content_type, content_base64, size }
     * or { error } on failure.
     */
    @AuraEnabled
    public static String downloadDocument(String docId) {
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/quotes/documents/' + docId + '/download');
            req.setMethod('GET');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(60000);
            HttpResponse res = new Http().send(req);
            if (res.getStatusCode() != 200) {
                return JSON.serialize(new Map<String, Object>{
                    'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                    'status' => res.getStatusCode()
                });
            }
            Blob body = res.getBodyAsBlob();
            String contentType = res.getHeader('Content-Type');
            if (contentType == null) contentType = 'application/pdf';
            String filename = docId + (contentType.contains('wordprocessingml') ? '.docx' : '.pdf');
            // Try to honor the server-provided filename if present.
            String disp = res.getHeader('Content-Disposition');
            if (disp != null && disp.contains('filename=')) {
                Integer idx = disp.indexOf('filename=') + 9;
                String cand = disp.substring(idx).replace('"', '').trim();
                if (cand.length() > 0) filename = cand;
            }
            return JSON.serialize(new Map<String, Object>{
                'doc_id' => docId,
                'filename' => filename,
                'content_type' => contentType,
                'content_base64' => EncodingUtil.base64Encode(body),
                'size' => body.size()
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(),
                'exception_type' => e.getTypeName()
            });
        }
    }

    /**
     * Parse a natural language prompt (preview mode).
     * Returns extracted structured data without creating anything.
     */
    @AuraEnabled(cacheable=false)
    public static String parsePrompt(String prompt) {
        try {
            String token = getAuthToken();

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/crm/salesforce/parse-prompt');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody('{"prompt":"' + prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"}');
            req.setTimeout(30000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            return '{"error":"Parse failed: ' + res.getStatusCode() + '"}';
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Quick Trigger: Generate proposal from just an identifier
     * (SF ID, deal name, or account name). Simplest possible UX.
     */
    @AuraEnabled(cacheable=false)
    public static String quickGenerate(String identifier) {
        try {
            String token = getAuthToken();

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/crm/salesforce/quick-generate');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody('{"deal_identifier":"' + identifier.replace('\\', '\\\\').replace('"', '\\"') + '"}');
            req.setTimeout(120000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            return '{"error":"' + res.getStatusCode() + ' - ' + res.getBody().replace('"', '\\"').replace('\n', ' ') + '"}';
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Submit feedback on a proposal (for continuous learning).
     */
    @AuraEnabled(cacheable=false)
    public static String submitFeedback(String docId, String feedbackType) {
        try {
            String token = getAuthToken();

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/learning/feedback');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody('{"doc_id":"' + docId + '","feedback_type":"' + feedbackType + '"}');
            req.setTimeout(30000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            return res.getBody();
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Prompt-to-Quote preview (Headless 360 LWC entry point).
     *
     * Invoked by quoteForgePromptBuilder on the Contact record page. The backend
     * parses the prompt against the seller's agent-exposed catalog, runs the
     * result through the guardrail engine, and returns a SIGNED offer payload
     * ready to commit. No Opportunity/Account side-effects yet — this is a
     * preview so the rep can review line items + guardrail verdict first.
     */
    @AuraEnabled(cacheable=false)
    public static String generateQuoteFromPrompt(Id contactId, Id opportunityId, String promptText) {
        try {
            String token = getAuthToken();

            Map<String, Object> payload = new Map<String, Object>();
            payload.put('prompt_text', promptText != null ? promptText : '');
            if (contactId != null) payload.put('contact_id', String.valueOf(contactId));
            if (opportunityId != null) payload.put('opportunity_id', String.valueOf(opportunityId));

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/sf/prompt-to-quote');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(JSON.serialize(payload));
            req.setTimeout(120000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            return '{"error":"' + res.getStatusCode() + ' - ' +
                res.getBody().replace('"', '\\"').replace('\n', ' ') + '"}';
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Commit a previewed quote: verify signature → persist → log Task on the
     * Opportunity. The (offerId, signature) pair comes from generateQuoteFromPrompt;
     * the LWC should only call this after the user clicks Approve on the preview.
     */
    @AuraEnabled(cacheable=false)
    public static String commitQuoteFromPrompt(String offerId, String signature, Id opportunityId) {
        try {
            String token = getAuthToken();

            Map<String, Object> payload = new Map<String, Object>();
            payload.put('offer_id', offerId);
            payload.put('signature', signature);
            if (opportunityId != null) payload.put('opportunity_id', String.valueOf(opportunityId));

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/sf/commit-quote');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(JSON.serialize(payload));
            req.setTimeout(60000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200 && opportunityId != null) {
                // Log a Task against the Opportunity so the rep sees the commit
                // in the activity timeline. Best-effort — failure here doesn't
                // invalidate the committed offer in QuoteForge.
                try {
                    Task activity = new Task(
                        WhatId = opportunityId,
                        Subject = 'QuoteForge: Prompt Quote Committed',
                        Description = 'Committed via Prompt Builder LWC.\n' + res.getBody(),
                        Status = 'Completed',
                        Priority = 'Normal',
                        ActivityDate = Date.today()
                    );
                    insert activity;
                } catch (Exception ignored) { /* best-effort */ }
            }

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            return '{"error":"' + res.getStatusCode() + ' - ' +
                res.getBody().replace('"', '\\"').replace('\n', ' ') + '"}';
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Create a full deal from a natural language prompt.
     * Creates Account (if needed), Opportunity, LineItems, and generates proposal.
     */
    @AuraEnabled(cacheable=false)
    public static String createDealFromPrompt(String prompt, Id contactId, String outputFormat) {
        try {
            String token = getAuthToken();

            Map<String, Object> payload = new Map<String, Object>();
            payload.put('prompt', prompt);
            if (contactId != null) payload.put('contact_id', String.valueOf(contactId));
            payload.put('output_format', outputFormat != null ? outputFormat : 'PDF');

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/crm/salesforce/create-deal-from-prompt');
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(JSON.serialize(payload));
            req.setTimeout(120000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            return '{"error":"Deal creation failed: ' + res.getStatusCode() + ' - ' + res.getBody().replace('"', '\\"') + '"}';
        } catch (Exception e) {
            return '{"error":"' + e.getMessage().replace('"', '\\"') + '"}';
        }
    }

    /**
     * Deal Insights — fetch win-probability prediction for an Opportunity.
     *
     * Invoked by the quoteForgeDealInsights LWC on Opportunity record pages.
     * Returns JSON from the backend /api/insights/predict endpoint containing
     * probability, top SHAP drivers, and (asynchronously populated) Haiku
     * explanation text.
     *
     * Cacheable — the LWC uses `cacheable=true` so Salesforce can share the
     * result across rep sessions viewing the same Opportunity within the
     * short transaction cache window.
     */
    @AuraEnabled(cacheable=true)
    public static String getOpportunityInsight(Id opportunityId) {
        try {
            String token = getAuthToken();

            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/insights/predict/' + String.valueOf(opportunityId));
            req.setMethod('GET');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(30000);

            Http http = new Http();
            HttpResponse res = http.send(req);

            if (res.getStatusCode() == 200) {
                return res.getBody();
            }
            if (res.getStatusCode() == 409) {
                // No active model — FastAPI returns {"detail":"..."} JSON.
                return res.getBody();
            }
            // Non-2xx / non-409 — hand back a diagnostic payload the LWC can
            // render verbatim. JSON.serialize escapes newlines, backslashes,
            // and control chars correctly (string concatenation does not,
            // which is what caused "Invalid response from QuoteForge backend"
            // when the backend returned HTML with line breaks).
            return JSON.serialize(new Map<String, Object>{
                'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                'status' => res.getStatusCode(),
                'body_preview' => (res.getBody() == null
                    ? '' : res.getBody().left(200))
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(),
                'exception_type' => e.getTypeName()
            });
        }
    }

    /**
     * QuoteForge App Home — bundled data for the App Launcher tile.
     *
     * Drives the quoteForgeAppHome LWC which lives on the QuoteForge
     * Lightning App's Home page. Returns three sections in one callout
     * so the page renders with a single Apex round-trip:
     *
     *   leaderboard   — top-15 open Opportunities ranked by the backend's
     *                   cached win-probability predictions (batch endpoint)
     *   launcher_opps — 5 most-recently-modified open Opps, linked so reps
     *                   can jump in and fire the Prompt Builder there
     *   quotes        — last 5 QuoteForge_Document__c rows by CreatedDate
     *
     * All three sections are independent — a failure fetching one does not
     * blank out the others.
     */
    @AuraEnabled(cacheable=true)
    public static String getAppHomeData() {
        Map<String, Object> out = new Map<String, Object>{
            'leaderboard' => new List<Object>(),
            'launcher_opps' => new List<Object>(),
            'quotes' => new List<Object>()
        };

        // ── Section 1 + 2: open Opps + leaderboard ───────────────
        try {
            List<Opportunity> opens = [
                SELECT Id, Name, Amount, StageName, Account.Name, LastModifiedDate
                FROM Opportunity
                WHERE IsClosed = false
                ORDER BY LastModifiedDate DESC
                LIMIT 15
            ];

            // Launcher_opps: first five opens for the Prompt Builder card.
            List<Map<String, Object>> launcher = new List<Map<String, Object>>();
            Integer n = 0;
            for (Opportunity o : opens) {
                if (n >= 5) break;
                launcher.add(new Map<String, Object>{
                    'id' => String.valueOf(o.Id),
                    'name' => o.Name,
                    'account_name' => o.Account != null ? o.Account.Name : '',
                    'stage' => o.StageName,
                    'amount' => o.Amount
                });
                n++;
            }
            out.put('launcher_opps', launcher);

            if (!opens.isEmpty()) {
                List<String> ids = new List<String>();
                Map<Id, Opportunity> byId = new Map<Id, Opportunity>();
                for (Opportunity o : opens) {
                    ids.add(String.valueOf(o.Id));
                    byId.put(o.Id, o);
                }

                String token = getAuthToken();
                HttpRequest req = new HttpRequest();
                req.setEndpoint(QUOTEFORGE_API + '/insights/predict/batch');
                req.setMethod('POST');
                req.setHeader('Content-Type', 'application/json');
                req.setHeader('Authorization', 'Bearer ' + token);
                req.setHeader('ngrok-skip-browser-warning', 'true');
                req.setBody(JSON.serialize(new Map<String, Object>{
                    'opportunity_ids' => ids
                }));
                req.setTimeout(90000);

                Http http = new Http();
                HttpResponse res = http.send(req);
                if (res.getStatusCode() == 200) {
                    Map<String, Object> body =
                        (Map<String, Object>) JSON.deserializeUntyped(res.getBody());
                    List<Object> results = (List<Object>) body.get('results');
                    List<Map<String, Object>> leaderboard =
                        new List<Map<String, Object>>();
                    if (results != null) {
                        for (Object r : results) {
                            Map<String, Object> p = (Map<String, Object>) r;
                            if (p.containsKey('error')) continue;
                            Id oid;
                            try {
                                oid = (Id) p.get('opportunity_id');
                            } catch (Exception idEx) {
                                continue;
                            }
                            Opportunity o = byId.get(oid);
                            if (o == null) continue;
                            leaderboard.add(new Map<String, Object>{
                                'opportunity_id' => String.valueOf(oid),
                                'name' => o.Name,
                                'account_name' => o.Account != null ? o.Account.Name : '',
                                'amount' => o.Amount,
                                'stage' => o.StageName,
                                'win_probability' => p.get('win_probability'),
                                'probability_percent' => p.get('probability_percent'),
                                'band' => p.get('band')
                            });
                        }
                    }
                    out.put('leaderboard', leaderboard);
                }
            }
        } catch (Exception e) {
            out.put('leaderboard_error', e.getMessage());
        }

        // ── Section 3: recent QuoteForge documents ───────────────
        try {
            List<QuoteForge_Document__c> docs = [
                SELECT Id, Name, Total__c, Status__c, CreatedDate,
                       Opportunity__c, Opportunity__r.Name,
                       Opportunity__r.Account.Name
                FROM QuoteForge_Document__c
                ORDER BY CreatedDate DESC
                LIMIT 5
            ];
            List<Map<String, Object>> quotes = new List<Map<String, Object>>();
            for (QuoteForge_Document__c d : docs) {
                String acct = '';
                if (d.Opportunity__r != null && d.Opportunity__r.Account != null) {
                    acct = d.Opportunity__r.Account.Name;
                }
                quotes.add(new Map<String, Object>{
                    'id' => String.valueOf(d.Id),
                    'name' => d.Name,
                    'total' => d.Total__c,
                    'status' => d.Status__c,
                    'account_name' => acct,
                    'opportunity_id' => d.Opportunity__c == null
                        ? null : String.valueOf(d.Opportunity__c),
                    'opportunity_name' => d.Opportunity__r == null
                        ? '' : d.Opportunity__r.Name,
                    'created_at' => d.CreatedDate
                });
            }
            out.put('quotes', quotes);
        } catch (Exception e) {
            out.put('quotes_error', e.getMessage());
        }

        return JSON.serialize(out);
    }

    /**
     * Settings/status page data for the QuoteForge Lightning App's
     * "QuoteForge Settings" tab. Aggregates:
     *
     *   - backend reachability (GET /health — doesn't require auth)
     *   - active Deal Insights model metadata (GET /insights/models)
     *   - installation checklist outcomes
     *
     * Not cacheable — reps/admins click "Refresh" to get current status.
     */
    @AuraEnabled(cacheable=false)
    public static String getSettingsStatus() {
        Map<String, Object> out = new Map<String, Object>{
            'named_credential' => 'QuoteForge_API',
            'backend_reachable' => false,
            'backend_version' => null,
            'backend_error' => null,
            'active_model' => null
        };

        // ── Health ping ─────────────────────────────────────
        try {
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/health');
            req.setMethod('GET');
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(10000);
            Http http = new Http();
            HttpResponse res = http.send(req);
            if (res.getStatusCode() == 200) {
                out.put('backend_reachable', true);
                try {
                    Map<String, Object> body =
                        (Map<String, Object>) JSON.deserializeUntyped(res.getBody());
                    out.put('backend_version', body.get('version'));
                    out.put('backend_service', body.get('service'));
                } catch (Exception parseEx) {
                    // non-JSON 200 — treat as reachable but unknown version
                }
            } else {
                out.put('backend_error',
                    'HTTP ' + res.getStatusCode() + ' from /health');
            }
        } catch (Exception e) {
            out.put('backend_error', e.getMessage());
        }

        // ── Active Deal Insights model ──────────────────────
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + '/insights/models');
            req.setMethod('GET');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(15000);
            Http http = new Http();
            HttpResponse res = http.send(req);
            if (res.getStatusCode() == 200) {
                List<Object> models =
                    (List<Object>) JSON.deserializeUntyped(res.getBody());
                for (Object m : models) {
                    Map<String, Object> model = (Map<String, Object>) m;
                    Object activeFlag = model.get('is_active');
                    if (activeFlag instanceof Boolean && (Boolean) activeFlag) {
                        out.put('active_model', new Map<String, Object>{
                            'version' => model.get('version'),
                            'accuracy' => model.get('accuracy'),
                            'auc' => model.get('auc'),
                            'training_rows' => model.get('training_rows'),
                            'trained_at' => model.get('trained_at')
                        });
                        break;
                    }
                }
                out.put('model_count', models.size());
            }
        } catch (Exception e) {
            out.put('model_error', e.getMessage());
        }

        // ── Installation checklist ──────────────────────────
        Boolean reachable = (Boolean) out.get('backend_reachable');
        Boolean hasModel = out.get('active_model') != null;
        List<Map<String, Object>> checks = new List<Map<String, Object>>{
            new Map<String, Object>{
                'label' => 'Named Credential QuoteForge_API configured',
                'passed' => reachable,
                'hint' => reachable
                    ? null
                    : 'Setup → Named Credentials → edit QuoteForge_API. URL must end in /api.'
            },
            new Map<String, Object>{
                'label' => 'QuoteForge backend reachable',
                'passed' => reachable,
                'hint' => reachable ? null : (String) out.get('backend_error')
            },
            new Map<String, Object>{
                'label' => 'Deal Insights model trained',
                'passed' => hasModel,
                'hint' => hasModel
                    ? null
                    : 'Open QuoteForge Admin → Deal Insights → Models → Retrain now'
            }
        };
        out.put('checks', checks);
        return JSON.serialize(out);
    }

    // ─── Session 6.5 — Mapping wizard + Accuracy proxies ─────────────

    /** Proxy for GET /api/insights/schema — powers the Mapping LWC's Step 1. */
    @AuraEnabled(cacheable=true)
    public static String getInsightsSchema() {
        return authedGet('/insights/schema');
    }

    /** Proxy for GET /api/insights/mapping — powers the Mapping LWC's Step 2. */
    @AuraEnabled(cacheable=true)
    public static String getInsightsMapping() {
        return authedGet('/insights/mapping');
    }

    /** Proxy for POST /api/insights/mapping — saves the mapping from the LWC. */
    @AuraEnabled
    public static String saveInsightsMapping(String mappingJson) {
        return authedPost('/insights/mapping', mappingJson);
    }

    /** Proxy for GET /api/insights/accuracy — powers the Model Accuracy LWC. */
    @AuraEnabled(cacheable=true)
    public static String getModelAccuracy() {
        return authedGet('/insights/accuracy');
    }

    /** Proxy for POST /api/insights/train — kicks off a new training run. */
    @AuraEnabled
    public static String triggerRetrain() {
        return authedPost('/insights/train', '{}');
    }

    // ─── Phase 4 — Tab data endpoints ────────────────────────────────

    /** Model history table + active model metrics for Model Management tab. */
    @AuraEnabled(cacheable=true)
    public static String listInsightsModels() {
        return authedGet('/insights/models');
    }

    /** Tail of training_log.txt — polled every 2s while training runs. */
    @AuraEnabled(cacheable=false)
    public static String getTrainingLog(Integer tail) {
        Integer n = (tail == null || tail <= 0) ? 200 : Math.min(tail, 2000);
        return authedGet('/insights/training-log?tail=' + String.valueOf(n));
    }

    /** Training job status — "running" / "done" / "error" + metrics snapshot. */
    @AuraEnabled(cacheable=false)
    public static String getInsightsStatus() {
        return authedGet('/insights/status');
    }

    // ─── ICP CRUD proxies ──────────────────────────────────────────

    @AuraEnabled(cacheable=true)
    public static String listICPs() {
        return authedGet('/icp');
    }

    @AuraEnabled(cacheable=true)
    public static String getICP(String icpId) {
        return authedGet('/icp/' + icpId);
    }

    @AuraEnabled
    public static String createICP(String bodyJson) {
        return authedPost('/icp', bodyJson);
    }

    @AuraEnabled
    public static String updateICP(String icpId, String bodyJson) {
        return authedPut('/icp/' + icpId, bodyJson);
    }

    @AuraEnabled
    public static String deleteICP(String icpId) {
        return authedDelete('/icp/' + icpId);
    }

    @AuraEnabled
    public static String activateICP(String icpId) {
        return authedPost('/icp/' + icpId + '/activate', '{}');
    }

    @AuraEnabled(cacheable=true)
    public static String scoreOppAgainstICP(String opportunityId) {
        return authedGet('/icp/score/' + opportunityId);
    }

    // ─── Shared HTTP helpers (JSON in, JSON out, authed, hardened) ───

    private static String authedGet(String path) {
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + path);
            req.setMethod('GET');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(30000);
            HttpResponse res = new Http().send(req);
            if (res.getStatusCode() == 200) return res.getBody();
            return JSON.serialize(new Map<String, Object>{
                'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                'status' => res.getStatusCode(),
                'body_preview' => (res.getBody() == null ? '' : res.getBody().left(200))
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(),
                'exception_type' => e.getTypeName()
            });
        }
    }

    private static String authedPut(String path, String body) {
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + path);
            req.setMethod('PUT');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(body == null ? '{}' : body);
            req.setTimeout(60000);
            HttpResponse res = new Http().send(req);
            if (res.getStatusCode() == 200) return res.getBody();
            return JSON.serialize(new Map<String, Object>{
                'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                'status' => res.getStatusCode(),
                'body_preview' => (res.getBody() == null ? '' : res.getBody().left(200))
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(), 'exception_type' => e.getTypeName()
            });
        }
    }

    private static String authedDelete(String path) {
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + path);
            req.setMethod('DELETE');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setTimeout(30000);
            HttpResponse res = new Http().send(req);
            if (res.getStatusCode() == 204 || res.getStatusCode() == 200) {
                return JSON.serialize(new Map<String, Object>{'deleted' => true});
            }
            return JSON.serialize(new Map<String, Object>{
                'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                'status' => res.getStatusCode(),
                'body_preview' => (res.getBody() == null ? '' : res.getBody().left(200))
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(), 'exception_type' => e.getTypeName()
            });
        }
    }

    private static String authedPost(String path, String body) {
        try {
            String token = getAuthToken();
            HttpRequest req = new HttpRequest();
            req.setEndpoint(QUOTEFORGE_API + path);
            req.setMethod('POST');
            req.setHeader('Content-Type', 'application/json');
            req.setHeader('Authorization', 'Bearer ' + token);
            req.setHeader('ngrok-skip-browser-warning', 'true');
            req.setBody(body == null ? '{}' : body);
            req.setTimeout(120000);
            HttpResponse res = new Http().send(req);
            if (res.getStatusCode() == 200) return res.getBody();
            return JSON.serialize(new Map<String, Object>{
                'error' => 'Backend returned HTTP ' + res.getStatusCode(),
                'status' => res.getStatusCode(),
                'body_preview' => (res.getBody() == null ? '' : res.getBody().left(200))
            });
        } catch (Exception e) {
            return JSON.serialize(new Map<String, Object>{
                'error' => e.getMessage(),
                'exception_type' => e.getTypeName()
            });
        }
    }
}
