# QuoteForge — Salesforce Package

Everything the sales ops admin deploys inside their own Salesforce org:

- `QuoteForgeController.cls` — Apex controller invoked by the LWCs
- `QuoteForge_Document__c` — custom object for storing generated proposals
- `QuoteForge.mcpServerDefinition` — registers QuoteForge's Agentic Commerce
  Gateway so Agentforce Studio + Headless 360 surfaces can list it alongside
  native tools
- `QuoteForge` Lightning App — branded App Launcher tile whose landing
  page bundles the Deal Insights leaderboard, Prompt Builder launcher, and
  recent-quotes table. Navigation also pins Opportunities / Contacts /
  Accounts so reps stay inside the QuoteForge workspace.
- LWC components:
  - `quoteForgeGenerator` — one-click generation from an Opportunity record page
  - `quoteForgeQuickTrigger` — home-page widget, type a deal name → PDF
  - `quoteForgeDealBuilder` — contact-page widget, natural-language → Opportunity
  - `quoteForgePromptBuilder` — natural-language → signed quote preview
    with guardrail verdict + commit. Runs through the Agent Gateway's
    `request_quote` + `accept_offer` pipeline, so guardrails fire identically
    whether a buyer agent or a human rep initiates the quote
  - `quoteForgeDealInsights` — win-probability card on the Opportunity page
    (percentage + Haiku explanation + SHAP driver breakdown)
  - `quoteForgeAppHome` — landing LWC for the QuoteForge app's Home tab

---

## Install options

### Option A — One-click install via unlocked package URL

Preferred for demo / shared-org installs. The package URL installs all
Apex, LWCs, flexipages, tabs, custom objects, and the Lightning App
in one click. Named Credential is **not** bundled — admin sets it up
once after install (step 2 below).

1. Open the install URL in a browser (already logged into the target org):
   ```
   https://login.salesforce.com/packaging/installPackage.apexp?p0=04tXXXXXXXXXXXXXXX
   ```
   Replace `04tXXXX…` with the current package-version ID. The project
   maintainer publishes the latest URL in the top-level `README.md`.
2. Choose **Install for All Users** → **Install**. Wait ~5 min.
3. Jump to step 2 below to create the Named Credential.

### Option B — SFDX source deploy (for developers iterating on the package)

```bash
cd salesforce_package
sf org login web --alias qf-sandbox --instance-url https://test.salesforce.com
sf project deploy start --target-org qf-sandbox
```

## Post-install setup

### 1. Create the Named Credential `QuoteForge_API` (required — first step)

The Apex controller resolves the backend URL through a Named Credential named
exactly `QuoteForge_API`. This is what lets you rotate ngrok tunnels, switch
between sandbox and production, or move to a real HTTPS endpoint without
redeploying Apex.

In your Salesforce org:

1. **Setup → Quick Find →** type **"Named Credentials"** and open the page.
2. Click **New Named Credential**.
3. Fill in:
   - **Label:** `QuoteForge API`
   - **Name:** `QuoteForge_API`  *(must match exactly — Apex references `callout:QuoteForge_API`)*
   - **URL:** your backend's base URL including `/api`, e.g.
     - ngrok (dev): `https://abc-123.ngrok-free.app/api`
     - Hetzner (prod): `https://api.quoteforge.io/api`
   - **Identity Type:** `Anonymous`
     *(the Apex controller handles its own JWT auth — the Named Credential only supplies the URL)*
   - **Authentication Protocol:** `No Authentication`
   - **Callout Options → Generate Authorization Header:** unchecked
4. Save.

> **If you rotate your ngrok URL:** just edit the Named Credential's URL
> field. Zero Apex / LWC redeploy. The whole package adapts immediately.

### 2. Add your backend domain to Remote Site Settings (pre-Named-Credential callouts only)

Named Credentials normally cover this — but if you hit any callout errors
mentioning an "unauthorized endpoint", also add the hostname under
**Setup → Remote Site Settings**.

### 3. Deploy the package

```bash
# from the repo root
cd salesforce_package
sf org login web --alias qf-sandbox --instance-url https://test.salesforce.com
sf project deploy start --target-org qf-sandbox
```

Or use VS Code's Salesforce Extension Pack: *SFDX: Deploy Source to Org*.

### 4. Give users access to the custom object

**Setup → Object Manager → QuoteForge Document → Permissions** — grant your
sales profile read/create access.

### 5. Drop the LWCs onto record pages

- **Lightning App Builder** → edit an Opportunity record page → drag
  `quoteForgeGenerator` into the right sidebar → Save → Activate.
- Repeat for the Home page (`quoteForgeQuickTrigger`) and Contact page
  (`quoteForgeDealBuilder`).
- For the new **prompt-to-quote** flow: edit the Contact (or Opportunity /
  Account) record page → drag `quoteForgePromptBuilder` into the right sidebar
  → Save → Activate. Reps can now type free-text prompts and commit signed
  quotes through the Agent Gateway guardrails.

### 6. (Optional) Headless 360 / Agentforce registration

The package ships an `McpServerDefinition` metadata record — visible in
**Setup → Quick Find → "MCP"** or **Agentforce Studio → Tools** depending on
your org's Headless 360 feature flags. This entry is what makes QuoteForge's
agent-facing MCP server discoverable by Agentforce plugins alongside native
tools.

The record itself is deliberately lean (label + description). URL, auth, and
the active/inactive flag live in org-side Setup UI (MCP Server Access) and in
the Named Credential you configured in Step 1. To wire the access side:

1. **Setup → MCP Server Access** (or equivalent Agentforce Studio screen).
2. Create a new access pointing at the `QuoteForge` definition.
3. URL: `callout:QuoteForge_API/mcp` (reuses the existing Named Credential).
4. Mark active. Agent surfaces can now invoke `get_products`, `request_quote`,
   and `accept_offer` without re-authenticating.

If your org doesn't yet surface MCP admin screens, the metadata record still
deploys cleanly — it just waits until the feature is enabled.

---

## Authentication flow

The Apex controller makes two kinds of calls:

1. **Auth:** `POST callout:QuoteForge_API/auth/login` with admin credentials.
   Returns a JWT. Cached in an Apex static for the transaction.
2. **Work:** `POST callout:QuoteForge_API/quotes/generate` etc., carrying
   `Authorization: Bearer <jwt>`.

For a hardened production deployment you'd replace the JWT dance with a
Named Credential configured with *Per-User* OAuth 2.0 Client Credentials, but
that requires the QuoteForge backend to publish a compatible OAuth endpoint.
Out of scope for the current build.

---

## Development tips

- **Rotating ngrok:** edit the Named Credential's URL field. Nothing else.
- **Testing callouts locally:** Salesforce will refuse plain-HTTP callouts.
  Always use HTTPS. `ngrok http 8000` is the cheapest way to expose localhost.
- **Seeing logs:** Setup → Debug Logs → enable for your user, then watch
  `HTTP CALLOUT` lines alongside `USER_DEBUG` entries emitted by the
  controller.

---

## What changed in this version

- `QUOTEFORGE_API` constant is now `callout:QuoteForge_API` (Named Credential) —
  no more hardcoded URLs in Apex.
- Rotating your backend URL is a Setup edit, not a redeploy.
- **sourceApiVersion bumped to 66.0** for Headless 360 alignment.
- **New metadata:** `McpServerDefinition/QuoteForge` — registers the Agentic
  Commerce Gateway MCP server for Agentforce Studio + Headless 360 discovery.
- **New Apex methods:** `generateQuoteFromPrompt(contactId, opportunityId, promptText)`
  and `commitQuoteFromPrompt(offerId, signature, opportunityId)` — thin
  callout wrappers over `/api/sf/prompt-to-quote` and `/api/sf/commit-quote`.
- **New LWC:** `quoteForgePromptBuilder` — natural-language quote flow on
  Contact / Opportunity / Account record pages. Runs through the same
  `request_quote` adapter as the buyer-agent MCP path, so guardrails and
  signed offers are identical across surfaces.
