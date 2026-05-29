# QuoteForge — One-Click Install Guide

End-to-end runbook for shipping QuoteForge as a Connected App that any
Salesforce admin installs and authorizes with a single click. Assumes
zero prior infra.

---

## What you get when this is done

* QuoteForge backend running on a public HTTPS URL (Render).
* A Salesforce Connected App that an admin installs from your packaging
  org, opens, and clicks **Connect** — Salesforce handles OAuth consent,
  the backend stores the org's tokens, and quotes can be pushed.
* No tunnels, no `localhost`, no manual token copy/paste.

---

## Prereqs (one-time, ~10 min)

| Need                                  | How                                                           |
| ------------------------------------- | ------------------------------------------------------------- |
| GitHub account with this repo pushed  | already done if you're reading this from the repo             |
| Render account                        | https://render.com (free, GitHub sign-in)                     |
| Salesforce **packaging org**          | free Developer Edition at https://developer.salesforce.com/signup |
| Salesforce CLI installed              | `npm install -g @salesforce/cli` (or `brew install salesforce-cli`) |

---

## Step 1 — Deploy the backend to Render

1. Log in to Render → **New → Blueprint**.
2. Point it at this repo. Render reads `render.yaml` at the root and
   provisions:
   * `quoteforge-backend` (Docker web service from `backend/Dockerfile`).
   * `quoteforge-db` (managed Postgres 16, connected via `DATABASE_URL`).
3. When prompted for secrets, fill these in (everything else is wired
   automatically by `render.yaml`):

   ```text
   SECRET_KEY              <openssl rand -hex 32>
   TOKEN_ENCRYPTION_KEY    <python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
   OPENAI_API_KEY          sk-...    (optional — falls back to template AI)
   ANTHROPIC_API_KEY       sk-ant-... (optional — buyer-room module)
   SALESFORCE_CLIENT_ID    leave blank for now — you'll fill this after Step 2
   SALESFORCE_CLIENT_SECRET leave blank for now
   QF_DEFAULT_ADMIN_PASSWORD <pick one — the seeded admin login>
   QF_DEFAULT_USER_PASSWORD  <pick one>
   ```

4. Apply. First build takes ~6 minutes (lightgbm wheel).
5. Note the public URL Render assigns, e.g.
   `https://quoteforge-backend.onrender.com`. You'll need it twice below.
6. Smoke-test:
   ```sh
   curl https://quoteforge-backend.onrender.com/healthz
   # → {"ok": true}
   ```

---

## Step 2 — Create the Connected App in your packaging org

1. Open VS Code at `quoteforge_v3/salesforce_package/`.
2. Search-and-replace `YOUR-RENDER-SERVICE.onrender.com` across these
   three files, swapping in your real Render hostname:
   * `force-app/main/default/connectedApps/QuoteForge.connectedApp-meta.xml`
   * `force-app/main/default/namedCredentials/QuoteForge_API.namedCredential-meta.xml`
   * `force-app/main/default/remoteSiteSettings/QuoteForge_API.remoteSite-meta.xml`
3. Authorize the Salesforce CLI against your packaging Dev Edition org:
   ```sh
   sf org login web --alias quoteforge-pkg
   ```
4. Deploy just the Connected App (this is the only metadata Salesforce
   requires before it issues a Consumer Key):
   ```sh
   cd quoteforge_v3/salesforce_package
   sf project deploy start \
       --target-org quoteforge-pkg \
       --source-dir force-app/main/default/connectedApps
   ```
5. In Salesforce Setup → **App Manager**, find **QuoteForge** → click
   the dropdown ▾ → **View** → **Manage Consumer Details** (you may be
   prompted for an email verification code). Copy the **Consumer Key**
   and **Consumer Secret**.

---

## Step 3 — Paste the Consumer Key/Secret into Render

1. Render dashboard → `quoteforge-backend` → **Environment** tab.
2. Set:
   ```text
   SALESFORCE_CLIENT_ID     = <Consumer Key from Step 2.5>
   SALESFORCE_CLIENT_SECRET = <Consumer Secret from Step 2.5>
   ```
3. **Save Changes**. Render redeploys automatically.

---

## Step 4 — Deploy the rest of the Salesforce package

```sh
cd quoteforge_v3/salesforce_package
sf project deploy start --target-org quoteforge-pkg
```

This pushes the Named Credential, Remote Site Setting, Apex classes,
LWCs, flexipages, and tabs.

If you intend customers to install from a packaging org (not just deploy
source), build a managed package:

```sh
sf package create --name QuoteForge --package-type Managed --path force-app
sf package version create --package QuoteForge --installation-key-bypass --wait 10
# Returns an installation URL like https://login.salesforce.com/packaging/installPackage.apexp?p0=04t...
```

Share that URL with customer admins. **One click to install.**

---

## Step 5 — Customer admin connects in one click

The admin who installed the package:

1. Opens the **QuoteForge** app (App Launcher → QuoteForge).
2. On the Dashboard, the **QuoteForge — Salesforce Connection** card is
   the first thing they see, with a **Connect to Salesforce** button.
3. They click it. A Salesforce login popup opens. They consent.
4. The popup closes (or shows the success page), and the card flips to
   **Connected · 00DXXXXXXXX** within ~3 seconds.

That's it. Quotes can now be pushed:

```sh
# From any backend client (the LWC or curl)
curl -X POST https://quoteforge-backend.onrender.com/api/integrations/salesforce/push-quote \
     -H "Authorization: Bearer <JWT>" \
     -H "Content-Type: application/json" \
     -d '{"doc_id": "DOC-2457", "opportunity_id": "006xx0000004C92"}'
```

---

## Verification checklist

- [ ] `GET /healthz` returns `{"ok": true}` on Render
- [ ] `GET /api/integrations/salesforce/status` (with JWT) returns
      `{"connected": false, "configured": true}` before consent
- [ ] After clicking Connect, the same call returns
      `{"connected": true, "org_id": "...", "instance_url": "..."}`
- [ ] Pushing a quote creates a Salesforce **Quote** record linked to
      the supplied Opportunity (verify in Setup → Object Manager → Quote)
- [ ] Clicking Disconnect on the LWC card flips the badge back to
      *Not connected* and revokes the token at Salesforce

---

## Troubleshooting

| Symptom                                                         | Likely cause                                                                                   | Fix                                                                                                                                            |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| LWC card shows **Backend not configured**                       | `SALESFORCE_CLIENT_ID` or `SALESFORCE_CLIENT_SECRET` missing on Render                          | Re-do Step 3 and wait for the redeploy.                                                                                                        |
| Salesforce popup shows *redirect_uri_mismatch*                  | The `<callbackUrl>` in the Connected App doesn't match `PUBLIC_BASE_URL` on Render               | Either edit the Connected App in Setup → App Manager → QuoteForge → Edit, or fix the metadata XML and redeploy. Must match scheme + host + path exactly. |
| Card stays on *Not connected* after consent                     | The popup closed before the success redirect, or the backend couldn't reach Salesforce's token endpoint | Check Render logs for `Salesforce token exchange failed`. Network/CORS errors will surface there.                                              |
| `Salesforce did not return a refresh_token`                     | The Connected App is missing the **Perform requests at any time (refresh_token, offline_access)** scope | Edit the Connected App, save, wait ~10 min for the scope change to propagate, then retry.                                                       |
| `TOKEN_ENCRYPTION_KEY unset` warning in logs                    | Dev fallback is active — tokens won't survive a restart                                         | Generate a key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and set it on Render.              |
| `503` on first request after sleep                              | Render free tier dynos sleep after 15 min idle                                                  | Upgrade to a paid plan, or hit `/healthz` from an external uptime monitor every 5 min.                                                          |
| `FIELD_INTEGRITY_EXCEPTION` on push-quote                       | The Opportunity isn't in the connected org, or the user lacks edit access on Quote               | Confirm the `opportunity_id` belongs to the same org you connected, and that the consenting user has Create on Quote.                          |

---

## What this guide is *not*

* **AppExchange listing.** That's a separate Salesforce Security Review
  (weeks-long). Customers can still install the package via the URL from
  Step 4, just not search for it on the AppExchange.
* **Multi-region.** `render.yaml` pins to `oregon`. Edit it before
  applying the blueprint if you need EU or APAC.
* **High availability.** The backend runs on a single dyno with
  in-process schedulers (CRM sync, insights retrain). Scaling
  horizontally requires moving those out — see `app/gateway/workers/`.
