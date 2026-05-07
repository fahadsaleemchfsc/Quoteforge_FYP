# QuoteForge — Demo Setup Notes

Notes the operator (or committee) runs through before the live demo. Each
section is independent; do the ones you need.

---

## Golden Opp expected state (v10 — Session 6.5)

- **Prediction:** ~83% (high band, tight confidence range ~81-84%)
- **Drivers shown in LWC (rep-facing labels):**
  - Boosting odds: "Customer engagement", "Deal size", "Recent activity"
  - Risk factors: "Deal tenure", "Industry: Finance", "Quarter: Q2"
- **No "Timeline risk" driver** (`expected_close_distance` is hidden at inference — the distribution-mismatch fix from Session 6.5 Step 1)
- **No raw SHAP numbers** in the driver display — bars only
- **Haiku explanation** is rep-facing: cites $120K, 45 days, Proposal, referral; ends with an action verb

If Golden Opp shows 64% or references "Timeline risk," clear the cache and re-predict:
```bash
sqlite3 quoteforge.db "DELETE FROM deal_insight_predictions WHERE sf_opportunity_id = '006gL00000KlPp8QAF';"
```

## Model Accuracy tab — demo flow

Committee member asks "how do you know this works on real data?":

1. App Launcher → **QuoteForge** → **QuoteForge Accuracy** tab.
2. Point at the top-line metrics: "72% accuracy on 1000 deals the model never saw during training."
3. Scroll to **Accuracy by confidence bucket**. Read aloud: "when we say 80%+, we're right 92% of the time. When we say 40-60%, we're genuinely uncertain."
4. Scroll to **Recent deals check** — 10 closed deals, predictions at close vs. actual outcomes, with ✓ / ✗.
5. Note the absence of a retrain callout — explain "50+ new closed deals would trigger the retrain recommendation."

## Mapping Config tab — demo flow

Committee member asks "does every org configure the same fields?":

1. App Launcher → **QuoteForge** → **QuoteForge Mapping** tab.
2. Step 1 (auto-renders): "Schema inspection complete — 17 fields, 0 custom, 0 record types."
3. Click **Continue to mapping** → Step 2. Walk through: canonical Amount, StageName, CloseDate auto-suggested; Industry, LeadSource, Owner optional.
4. Click **Add Custom Feature** → modal → pick a custom field (any `__c`) → label `priority` → type `categorical` → **Add feature**.
5. Click **Continue** → Step 3. Checkbox grid of record types (empty in Dev Edition — note "no record types to exclude here").
6. Click **Save Mapping** → green success panel + toast: "Mapping saved. Ready to train your model."
7. Open the QuoteForge Admin React page at `/insights/setup` in a browser → same mapping is live. Both surfaces are the same API.

---

## QuoteForge app tabs (Phase 4)

After the Phase 4 deploy, the **QuoteForge** app in App Launcher has **10 tabs** in this order:

| # | Tab | LWC | Audience |
|---|---|---|---|
| 1 | **QuoteForge Dashboard** | `quoteForgeInsightsDashboard` | Rep · landing page |
| 2 | **QuoteForge Predictions** | `quoteForgePredictions` | Rep · searchable table of all open Opps |
| 3 | **QuoteForge ICP Config** | `quoteForgeICPConfig` | Admin · inline ICP builder |
| 4 | **QuoteForge Model Mgmt** | `quoteForgeModelManagement` | Admin · retrain + live log + history |
| 5 | **QuoteForge Mapping** | `quoteForgeMappingConfig` | Admin · field mapping wizard |
| 6 | **QuoteForge Accuracy** | `quoteForgeModelAccuracy` | Customer-facing trust view |
| 7 | **Opportunities** | standard | Rep workflow |
| 8 | **Contacts** | standard | Rep workflow |
| 9 | **Accounts** | standard | Rep workflow |
| 10 | **QuoteForge Settings** | `quoteForgeSettings` | Admin · connection status |

Landing page is now **QuoteForge Dashboard** — `quoteForgeAppHome` is retired.

### Phase 4 demo flow (6-tab walk-through)

1. **App Launcher → QuoteForge** → lands on **Dashboard**. Three KPI tiles (open deals scored · avg win probability · pipeline value) + two leaderboards (top 10 at-risk, top 10 high-probability).
2. Click any row → Opp record page → existing Deal Insights LWC shows the matching prediction + ICP score.
3. Back to the app → **Predictions** tab. Filter by stage, min amount, min win %. Sort by any column. Click row → record page.
4. **ICP Config** tab. Existing "Enterprise Tech" ICP is loaded on the left. Right pane shows the form with 5 weight sliders. Scroll down to the **Test** panel → the default Golden Opp Id is pre-filled → click **Score** → renders `100%` with 4 match-reason pills.
5. **Model Mgmt** tab. Active model card on top (v10 · Mature tier · 5000 rows · AUC 0.805). Click **Retrain now** → the live log panel pulses "LIVE · polling every 2s" and streams boosting-round lines in real time → completes → new row appears at top of the history table, feature-importance chart refreshes.
6. **Mapping** + **Accuracy** tabs still work as shipped in Session 6.5.

If any tab shows an error banner, the backend is unreachable — restart `uvicorn` + `cloudflared` and update the Named Credential URL per "Backend URL rotation" below.

## Opening the QuoteForge Lightning App

After deploying the package, the **QuoteForge** app appears in the App
Launcher (9-dot grid in the top-left of Salesforce).

1. Click the App Launcher → type `QuoteForge` → click the tile.
2. The landing page (`QuoteForge Home` tab) renders three panels:
   - **Deal Insights Leaderboard** — top 15 open Opportunities ranked by
     win probability from the trained LightGBM model. Clicking a row
     navigates to that Opportunity record.
   - **Prompt Builder launcher** — 5 most-recently-modified open Opps.
     Click one → Opportunity record opens → use the Prompt Builder LWC
     in the sidebar to generate a signed quote from plain English.
   - **Recent Committed Quotes** — last 5 `QuoteForge_Document__c` rows
     in the org, with status pills + links into the record.
3. The app's nav bar also includes **Opportunities**, **Contacts**, and
   **Accounts** so reps can stay inside the QuoteForge app for the whole
   workflow.

If the leaderboard is empty on first open: the backend hasn't trained a
Deal Insights model yet, or is unreachable. Open `QuoteForge Admin →
Deal Insights → Models` and click **Retrain now**, then refresh the page.
Empty states show friendly hints either way.

If any card shows "Backend returned HTTP …" or "non-JSON": the Named
Credential URL is stale or the backend is down — see the "Backend URL
rotation" section below.

---

## Golden Opportunity for Deal Insights (Module 6)

The Deal Insights LWC renders on any Opportunity record page, but the
committee will see the strongest story on a hand-curated "Golden Opp"
whose profile sits firmly in the high-probability band. Seed it before
the demo.

### Profile targets

| Field            | Value                                  | Why |
| ---------------- | -------------------------------------- | --- |
| Account Name     | `Acme Corporation`                     | Creates a reusable Account |
| Account Industry | `Technology`                           | Strong positive SHAP driver |
| Opportunity Name | `Acme Corp Enterprise Expansion`       | Memorable for the demo |
| Amount           | `$250,000`                             | Saturates the amount feature's upper band |
| Stage            | `Proposal/Price Quote`                 | Mid-funnel — realistic |
| Close Date       | today + 45 days                        | Sensible `days_to_close` |
| Lead Source      | `Partner Referral`                     | Strongest positive source |
| Owner            | Your demo user                         | Any |
| Created Date     | today − 30 days (implicit — don't edit) | Keeps `age_days` sane |

### Activities (8 total over past 30 days)

Log these so `activity_count` + `days_since_last_activity` contribute
positively. Mix Tasks and Events; space them evenly:

- 3 × Tasks: "Discovery call notes", "Pricing proposal sent", "Security review"
- 3 × Events: "Kickoff meeting", "Technical deep-dive", "Executive sponsor lunch"
- 2 × Tasks: "Follow-up email", "Contract draft sent"

Most recent activity should be ≤ 3 days old. The model penalizes stale
deals heavily.

### Clickstream for the demo

1. Open the Golden Opp record page.
2. Verify **Deal Insights** LWC renders on the right sidebar (drag it in
   via Lightning App Builder if not already placed).
3. Probability should land in the **60–80%** band (green). If it shows
   < 50%, the training set is noisy — retrain from
   `/insights/models` → "Retrain now", wait ~0.5s, refresh.
4. Click **See drivers** → verify at least one positive driver is
   `activity_count` or `amount`, and that the SHAP bars render.
5. Read the Haiku explanation aloud — it should mention the top positive
   driver and the top risk by name.

### CLI recipe (optional — if you have `sf` with a data-tree template)

Not scripted here because the Dev Edition org's permission set and
Account/Opportunity creation flow depends on your profile. Create the
Account + Opportunity manually through the Salesforce UI (takes ~2 min).

---

## Prompt-to-Quote LWC (Module 5)

1. Open a Contact record page.
2. Drag `quoteForgePromptBuilder` into the right sidebar via Lightning App
   Builder if not already placed.
3. Try one of the preset example prompts (Simple, PK Region, Mixed cart).
4. Submit → preview with line-item table + guardrail verdict should render
   in < 3 seconds.
5. Click **Approve + commit** → quote commits, green success panel shows
   the document ID + a Task is written to the Opportunity (if one was
   linked).

---

## Backend URL rotation (if the Cloudflare/ngrok URL changes)

1. **Setup → Quick Find → Named Credentials → QuoteForge_API**.
2. Edit the URL field to your new backend URL + `/api`.
3. Save. No Apex or LWC redeploy needed.

---

## Resetting the Deal Insights model

If the synthetic training data produced a weird model:

1. Admin UI → `/insights/models` → note the current active version.
2. Click **Retrain now** → new version trains in ~0.5s.
3. If that also looks wrong, update the mapping (`/insights/setup`) —
   adding a custom field forces a re-evaluation of the feature set.

The on-disk model pickles live at
`backend/storage/insights_models/{tenant_id}/v{N}.pkl`. Safe to delete the
directory to fully reset the model state — the DB metadata rows can stay
(they just become orphaned history).
