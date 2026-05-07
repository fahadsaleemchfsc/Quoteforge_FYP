"""
Salesforce CRM Connector — Real OAuth 2.0 + REST API Integration
=================================================================
Handles the complete Salesforce integration:
1. OAuth 2.0 Authorization Code flow
2. Token management (access + refresh)
3. REST API data retrieval (Opportunities, Accounts, Contacts, Products)
4. Field mapping to QuoteForge schema

Supports both Production (login.salesforce.com) and Sandbox (test.salesforce.com)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.crm_connection import CRMConnection
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Salesforce OAuth URLs ────────────────────────────────────────
SF_AUTH_URLS = {
    "production": "https://login.salesforce.com",
    "sandbox": "https://test.salesforce.com",
}

SF_API_VERSION = "v59.0"


# ─── OAuth 2.0 Flow ──────────────────────────────────────────────

def get_authorization_url(
    client_id: str,
    redirect_uri: str,
    environment: str = "production",
    state: str = "",
) -> str:
    """Generate Salesforce OAuth authorization URL for user redirect."""
    base = SF_AUTH_URLS.get(environment, SF_AUTH_URLS["production"])
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "full refresh_token",
        "state": state,
    }
    return f"{base}/services/oauth2/authorize?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    environment: str = "production",
) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    base = SF_AUTH_URLS.get(environment, SF_AUTH_URLS["production"])
    token_url = f"{base}/services/oauth2/token"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(token_url, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        })

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} — {response.text}")
            return {"error": response.text}

        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "instance_url": data["instance_url"],
            "token_type": data.get("token_type", "Bearer"),
            "issued_at": data.get("issued_at", ""),
        }


async def _persist_refreshed_tokens(
    db: AsyncSession, conn_id: int, *, access_token: str, instance_url: str,
) -> None:
    """Update CRMConnection.oauth_tokens with freshly rotated values."""
    conn = (await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))).scalar_one_or_none()
    if conn is None:
        return
    try:
        tokens = json.loads(conn.oauth_tokens or "{}")
    except json.JSONDecodeError:
        tokens = {}
    tokens["access_token"] = access_token
    tokens["instance_url"] = instance_url
    tokens["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    conn.oauth_tokens = json.dumps(tokens)
    if conn.status in ("reauth_required", "disconnected"):
        conn.status = "connected"
    await db.commit()


async def _mark_connection_reauth_required(db: AsyncSession, conn_id: int, reason: str) -> None:
    """Flip connection status so the UI can surface a Re-authenticate button."""
    conn = (await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))).scalar_one_or_none()
    if conn is None:
        return
    conn.status = "reauth_required"
    conn.health = 0.0
    logger.info("marked connection %s reauth_required: %s", conn_id, reason[:160])
    await db.commit()


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    environment: str = "production",
) -> dict:
    """Use refresh token to get a new access token."""
    base = SF_AUTH_URLS.get(environment, SF_AUTH_URLS["production"])
    token_url = f"{base}/services/oauth2/token"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(token_url, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        })

        if response.status_code != 200:
            return {"error": response.text}

        data = response.json()
        return {
            "access_token": data["access_token"],
            "instance_url": data["instance_url"],
        }


# ─── Salesforce REST API Client ──────────────────────────────────

class SalesforceClient:
    """Client for Salesforce REST API using stored OAuth tokens.

    When `refresh_context` is provided at construction, any 401 response on
    `_get` / `_post` / `_query` triggers one automatic refresh-and-retry:

        refresh_context = {
            "db": AsyncSession,        # used to persist refreshed tokens
            "conn_id": int,            # CRMConnection PK
            "refresh_token": str,
            "client_id": str,
            "client_secret": str,
            "environment": str,
        }

    If the refresh itself fails, the connection is marked status='reauth_required'
    so the admin UI can surface a "Re-authenticate" button. Callers that pass
    no refresh_context keep the legacy raise-on-401 behavior.
    """

    def __init__(
        self,
        instance_url: str,
        access_token: str,
        *,
        refresh_context: dict | None = None,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.api_base = f"{self.instance_url}/services/data/{SF_API_VERSION}"
        self._refresh_context = refresh_context

    @property
    def headers(self) -> dict:
        # Recomputed each access so a refreshed token is picked up.
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _refresh_if_possible(self) -> bool:
        """Try to refresh our access token using the stored refresh_token.
        Returns True on success. Updates self.access_token + persists to DB."""
        ctx = self._refresh_context
        if not ctx:
            return False
        new_tokens = await refresh_access_token(
            refresh_token=ctx["refresh_token"],
            client_id=ctx["client_id"],
            client_secret=ctx["client_secret"],
            environment=ctx["environment"],
        )
        if "error" in new_tokens:
            logger.warning("salesforce refresh failed: %s", new_tokens["error"])
            # Mark the connection reauth_required so the UI can surface it.
            await _mark_connection_reauth_required(ctx["db"], ctx["conn_id"], new_tokens["error"])
            return False

        self.access_token = new_tokens["access_token"]
        if new_tokens.get("instance_url"):
            self.instance_url = new_tokens["instance_url"].rstrip("/")
            self.api_base = f"{self.instance_url}/services/data/{SF_API_VERSION}"
        await _persist_refreshed_tokens(
            ctx["db"], ctx["conn_id"],
            access_token=self.access_token,
            instance_url=self.instance_url,
        )
        return True

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_base}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers, params=params)
            if response.status_code == 401 and await self._refresh_if_possible():
                # Second try with refreshed token, URL may have moved instance.
                response = await client.get(
                    f"{self.api_base}{endpoint}",
                    headers=self.headers, params=params,
                )
            if response.status_code == 401:
                raise PermissionError("Salesforce token expired — refresh failed or unavailable")
            response.raise_for_status()
            return response.json()

    async def _post(self, endpoint: str, data: dict) -> dict:
        url = f"{self.api_base}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self.headers, json=data)
            if response.status_code == 401 and await self._refresh_if_possible():
                response = await client.post(
                    f"{self.api_base}{endpoint}",
                    headers=self.headers, json=data,
                )
            response.raise_for_status()
            return response.json()

    async def _query(self, soql: str) -> list:
        """Execute SOQL query and return all records."""
        result = await self._get("/query", params={"q": soql})
        records = result.get("records", [])
        # Handle pagination
        while result.get("nextRecordsUrl"):
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.instance_url}{result['nextRecordsUrl']}",
                    headers=self.headers,
                )
                result = resp.json()
                records.extend(result.get("records", []))
        return records

    # ─── Data Retrieval Methods ───────────────────────────────

    async def get_opportunities(self, limit: int = 50) -> list:
        """Fetch open Opportunities with Account info."""
        soql = f"""
            SELECT Id, Name, Amount, StageName, CloseDate, Probability,
                   Account.Name, Account.BillingCountry,
                   (SELECT Id, Product2.Name, Quantity, UnitPrice, TotalPrice
                    FROM OpportunityLineItems)
            FROM Opportunity
            WHERE IsClosed = false
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """
        try:
            records = await self._query(soql)
            return [self._map_opportunity(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to fetch opportunities: {e}")
            # Fallback: simpler query without line items
            try:
                soql_simple = f"""
                    SELECT Id, Name, Amount, StageName, CloseDate,
                           Account.Name, Account.BillingCountry
                    FROM Opportunity
                    WHERE IsClosed = false
                    ORDER BY LastModifiedDate DESC
                    LIMIT {limit}
                """
                records = await self._query(soql_simple)
                return [self._map_opportunity(r) for r in records]
            except Exception as e2:
                logger.error(f"Simple query also failed: {e2}")
                return []

    async def get_opportunity_by_id(self, opp_id: str) -> dict:
        """Fetch a single Opportunity with full details."""
        # First try with line items
        try:
            soql = f"""
                SELECT Id, Name, Amount, StageName, CloseDate, Probability, Description,
                       Account.Name, Account.BillingCountry, Account.BillingCity,
                       Account.BillingState, Account.Phone, Account.Website,
                       (SELECT Id, Product2.Name, Product2.Description, Quantity,
                        UnitPrice, TotalPrice
                        FROM OpportunityLineItems)
                FROM Opportunity
                WHERE Id = '{opp_id}'
            """
            records = await self._query(soql)
        except Exception:
            # Fallback without line items
            soql = f"""
                SELECT Id, Name, Amount, StageName, CloseDate, Probability, Description,
                       Account.Name, Account.BillingCountry, Account.BillingCity,
                       Account.Phone, Account.Website
                FROM Opportunity
                WHERE Id = '{opp_id}'
            """
            records = await self._query(soql)
        if not records:
            return None
        return self._map_opportunity(records[0])

    async def get_accounts(self, limit: int = 50) -> list:
        """Fetch Accounts."""
        soql = f"""
            SELECT Id, Name, BillingCountry, BillingCity, BillingState,
                   Phone, Website, Industry, NumberOfEmployees
            FROM Account
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """
        return await self._query(soql)

    async def test_connection(self) -> dict:
        """Test the connection by fetching org info."""
        try:
            # Simple API call to verify credentials
            result = await self._get("/sobjects")
            return {
                "connected": True,
                "encoding": result.get("encoding", ""),
                "max_batch_size": result.get("maxBatchSize", 0),
                "sobjects_count": len(result.get("sobjects", [])),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def log_activity(self, opportunity_id: str, subject: str, description: str) -> dict:
        """Log a Task/Activity on the Opportunity for CRM tracking."""
        try:
            return await self._post("/sobjects/Task", {
                "WhatId": opportunity_id,
                "Subject": subject,
                "Description": description,
                "Status": "Completed",
                "Priority": "Normal",
                "ActivityDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
            return {"error": str(e)}

    # ─── Worker-facing operations ─────────────────────────────

    async def health_check(self) -> dict:
        """Minimal live probe. Returns {healthy, latency_ms, error?}."""
        import time
        start = time.monotonic()
        try:
            # The cheapest write-free probe we can run.
            await self._get("/query", params={"q": "SELECT Id FROM Organization LIMIT 1"})
            return {
                "healthy": True,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "error": None,
            }
        except PermissionError as e:
            return {"healthy": False, "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": f"auth: {e}"}
        except Exception as e:  # noqa: BLE001 — surface verbatim to admin UI
            return {"healthy": False, "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": str(e)[:200]}

    async def query_pricebook_entries(self, pricebook_id: str | None = None) -> list[dict]:
        """Fetch active Pricebook entries. Defaults to Standard Pricebook."""
        where = "IsActive = true"
        if pricebook_id:
            where += f" AND Pricebook2Id = '{pricebook_id}'"
        soql = (
            "SELECT Id, Pricebook2Id, UnitPrice, CurrencyIsoCode, "
            "Product2.Id, Product2.Name, Product2.ProductCode, Product2.Family, "
            "Product2.Description "
            f"FROM PricebookEntry WHERE {where}"
        )
        return await self._query(soql)

    async def create_opportunity_with_line_items(
        self,
        *,
        account_name: str,
        deal_name: str,
        amount: float,
        close_date: str,          # YYYY-MM-DD
        stage: str = "Closed Won",
        line_items: list[dict] | None = None,   # [{sku, quantity, unit_price}]
    ) -> dict:
        """Create a new Opportunity (and optionally its line items). Used when
        the offer was initiated from the Buyer Room / MCP rather than from an
        existing SF Opportunity."""
        # 1. Resolve or create Account.
        acct_id: str | None = None
        try:
            existing = await self._query(
                f"SELECT Id FROM Account WHERE Name = '{account_name.replace(chr(39), chr(92)+chr(39))}' LIMIT 1"
            )
            if existing:
                acct_id = existing[0]["Id"]
        except Exception as e:      # noqa: BLE001
            logger.info("Account lookup failed, will create: %s", e)
        if acct_id is None:
            acct_resp = await self._post("/sobjects/Account", {"Name": account_name})
            acct_id = acct_resp.get("id")

        # 2. Create Opportunity.
        opp_resp = await self._post("/sobjects/Opportunity", {
            "Name": deal_name,
            "AccountId": acct_id,
            "Amount": amount,
            "CloseDate": close_date,
            "StageName": stage,
        })
        opp_id = opp_resp.get("id")

        return {"opportunity_id": opp_id, "account_id": acct_id}

    async def create_quoteforge_document(
        self,
        opportunity_id: str,
        file_path: str,
        doc_metadata: dict,
    ) -> dict:
        """
        Full product flow:
        1. Upload the PDF/DOCX to Salesforce as ContentVersion (Files)
        2. Create a QuoteForge_Document__c record with all metadata
        3. Link the file to BOTH the Opportunity and the custom object
        4. Log activity on the Opportunity

        This is how PandaDoc, Conga, and DocuSign model their data.
        """
        import base64
        from pathlib import Path

        fp = Path(file_path)
        if not fp.exists():
            return {"error": f"File not found: {file_path}"}

        file_data = base64.b64encode(fp.read_bytes()).decode("utf-8")
        results = {"steps": {}}

        try:
            # ─── Step 1: Upload file as ContentVersion ────────
            cv_result = await self._post("/sobjects/ContentVersion", {
                "Title": doc_metadata.get("title", "QuoteForge Proposal"),
                "PathOnClient": fp.name,
                "VersionData": file_data,
                "Description": doc_metadata.get("description", "Generated by QuoteForge"),
            })
            content_version_id = cv_result.get("id")
            results["steps"]["content_version"] = content_version_id
            logger.info(f"ContentVersion created: {content_version_id}")

            # Get ContentDocumentId
            cv_record = await self._get(f"/sobjects/ContentVersion/{content_version_id}")
            content_document_id = cv_record.get("ContentDocumentId")
            results["steps"]["content_document"] = content_document_id

            # ─── Step 2: Link file to Opportunity ─────────────
            cdl_result = await self._post("/sobjects/ContentDocumentLink", {
                "ContentDocumentId": content_document_id,
                "LinkedEntityId": opportunity_id,
                "ShareType": "V",
                "Visibility": "AllUsers",
            })
            results["steps"]["opportunity_link"] = cdl_result.get("id")

            # ─── Step 3: Create QuoteForge_Document__c record ─
            pricing = doc_metadata.get("pricing", {})
            compliance = pricing.get("compliance_framework", "")
            # Convert to multi-select format: "SOC 2;GDPR"
            compliance_values = ";".join(
                c.strip() for c in compliance.replace(" Clause", "").replace(" Data", "").replace(" Security Terms", "").split(",")
                if c.strip()
            ) if compliance else ""

            qf_doc_data = {
                "Name": doc_metadata.get("doc_id", "DOC-000"),
                "Opportunity__c": opportunity_id,
                "Document_Type__c": doc_metadata.get("type", "Proposal"),
                "Output_Format__c": doc_metadata.get("format", "PDF"),
                "Status__c": "Generated",
                "Subtotal__c": pricing.get("subtotal", 0),
                "Discount__c": pricing.get("discount", 0),
                "Tax__c": pricing.get("tax", 0),
                "Total__c": pricing.get("total", 0),
                "Compliance_Framework__c": compliance_values,
                "Template_Name__c": doc_metadata.get("template", "Default"),
                "Generation_Time__c": doc_metadata.get("generation_time", 0),
                "AI_Model__c": doc_metadata.get("ai_model", "llama-3.2"),
                "Region__c": doc_metadata.get("region", "US"),
                "Content_Document_Id__c": content_document_id,
                "Recipient_Email__c": doc_metadata.get("contact_email", ""),
            }

            qf_doc_result = await self._post("/sobjects/QuoteForge_Document__c", qf_doc_data)
            qf_doc_id = qf_doc_result.get("id")
            results["steps"]["quoteforge_document"] = qf_doc_id
            logger.info(f"QuoteForge_Document__c created: {qf_doc_id}")

            # ─── Step 4: Also link file to the custom object ──
            if qf_doc_id:
                try:
                    cdl2 = await self._post("/sobjects/ContentDocumentLink", {
                        "ContentDocumentId": content_document_id,
                        "LinkedEntityId": qf_doc_id,
                        "ShareType": "V",
                        "Visibility": "AllUsers",
                    })
                    results["steps"]["document_link"] = cdl2.get("id")
                except Exception:
                    pass  # Non-critical

            # ─── Step 5: Log Activity ─────────────────────────
            activity_result = await self.log_activity(
                opportunity_id=opportunity_id,
                subject=f"QuoteForge: {doc_metadata.get('type', 'Proposal')} Generated",
                description=(
                    f"Document: {doc_metadata.get('doc_id', '')}\n"
                    f"Type: {doc_metadata.get('type', 'Proposal')} ({doc_metadata.get('format', 'PDF')})\n"
                    f"Total: ${pricing.get('total', 0):,.2f}\n"
                    f"Compliance: {compliance}\n"
                    f"Generation Time: {doc_metadata.get('generation_time', 0)}s\n"
                    f"AI Model: {doc_metadata.get('ai_model', 'llama-3.2')}\n"
                    f"\nGenerated by QuoteForge — AI-Powered Proposal Generation"
                ),
            )
            results["steps"]["activity"] = activity_result.get("id") if isinstance(activity_result, dict) else None

            results["success"] = True
            results["quoteforge_document_id"] = qf_doc_id
            results["content_document_id"] = content_document_id
            results["message"] = (
                f"Proposal uploaded to Salesforce. "
                f"QuoteForge Document: {qf_doc_id}, "
                f"File: {content_document_id}"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to create QuoteForge document in Salesforce: {e}")
            results["success"] = False
            results["error"] = str(e)
            return results

    # ─── Field Mapping ────────────────────────────────────────

    def _map_opportunity(self, record: dict) -> dict:
        """Map Salesforce Opportunity to QuoteForge deal schema."""
        account = record.get("Account") or {}
        contact = record.get("Contact") or {}

        # Map line items
        line_items = []
        oli_records = record.get("OpportunityLineItems")
        if oli_records and isinstance(oli_records, dict):
            for item in oli_records.get("records", []):
                product = item.get("Product2") or {}
                line_items.append({
                    "product": product.get("Name", "Unknown Product"),
                    "description": product.get("Description", ""),
                    "quantity": int(item.get("Quantity", 1)),
                    "unit_price": float(item.get("UnitPrice", 0)),
                    "total_price": float(item.get("TotalPrice", 0)),
                })

        # Determine region from billing country
        country = (account.get("BillingCountry") or "").upper()
        region = "US"
        if country in ("PAKISTAN", "PK"):
            region = "PK"
        elif country in ("GERMANY", "FRANCE", "ITALY", "SPAIN", "NETHERLANDS",
                         "BELGIUM", "AUSTRIA", "SWEDEN", "DENMARK", "FINLAND",
                         "IRELAND", "PORTUGAL", "GREECE", "DE", "FR", "IT",
                         "ES", "NL", "BE", "AT", "SE", "DK", "FI", "IE", "PT", "GR"):
            region = "EU"
        elif country in ("UNITED KINGDOM", "UK", "GB"):
            region = "EU"

        return {
            "deal_id": record.get("Id", ""),
            "deal_name": record.get("Name", ""),
            "deal_amount": float(record.get("Amount", 0) or 0),
            "stage": record.get("StageName", ""),
            "close_date": record.get("CloseDate", ""),
            "probability": record.get("Probability", 0),
            "description": record.get("Description", ""),
            "client_name": account.get("Name", ""),
            "client_country": account.get("BillingCountry", ""),
            "client_city": account.get("BillingCity", ""),
            "client_phone": account.get("Phone", ""),
            "client_website": account.get("Website", ""),
            "contact_name": contact.get("Name", ""),
            "contact_email": contact.get("Email", ""),
            "contact_phone": contact.get("Phone", ""),
            "contact_title": contact.get("Title", ""),
            "region": region,
            "line_items": line_items,
            "source": "salesforce",
            "source_id": record.get("Id", ""),
        }


# ─── Database Integration ─────────────────────────────────────────

async def store_salesforce_tokens(
    db: AsyncSession,
    tokens: dict,
    environment: str = "production",
) -> CRMConnection:
    """Store OAuth tokens in the database."""
    result = await db.execute(
        select(CRMConnection).where(
            CRMConnection.platform == "Salesforce",
            CRMConnection.environment == environment,
        )
    )
    conn = result.scalar_one_or_none()

    token_data = json.dumps({
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "instance_url": tokens["instance_url"],
    })

    if conn:
        conn.status = "connected"
        conn.oauth_tokens = token_data
        conn.health = 100.0
        conn.last_synced = datetime.now(timezone.utc)
    else:
        conn = CRMConnection(
            platform="Salesforce",
            environment=environment,
            status="connected",
            oauth_tokens=token_data,
            health=100.0,
            last_synced=datetime.now(timezone.utc),
            field_mappings=json.dumps([
                {"crm_field": "Opportunity.Name", "system_field": "deal_name"},
                {"crm_field": "Account.Name", "system_field": "client_name"},
                {"crm_field": "Contact.Email", "system_field": "contact_email"},
                {"crm_field": "Amount", "system_field": "deal_amount"},
                {"crm_field": "StageName", "system_field": "stage"},
                {"crm_field": "CloseDate", "system_field": "close_date"},
                {"crm_field": "OpportunityLineItems", "system_field": "line_items"},
                {"crm_field": "Account.BillingCountry", "system_field": "region"},
            ]),
        )
        db.add(conn)

    await db.commit()
    await db.refresh(conn)
    return conn


async def get_refresh_aware_client(db: AsyncSession, conn_id: int) -> Optional[SalesforceClient]:
    """Factory that returns a SalesforceClient whose internal _get/_post/_query
    auto-refresh on 401. Intended for worker + long-running code paths."""
    conn = (
        await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))
    ).scalar_one_or_none()
    if conn is None or not conn.oauth_tokens:
        return None
    try:
        tokens = json.loads(conn.oauth_tokens)
    except json.JSONDecodeError:
        return None

    return SalesforceClient(
        instance_url=tokens["instance_url"],
        access_token=tokens["access_token"],
        refresh_context={
            "db": db,
            "conn_id": conn.id,
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": settings.SALESFORCE_CLIENT_ID,
            "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            "environment": conn.environment,
        },
    )


async def get_salesforce_client(
    db: AsyncSession, tenant_id: str, conn_id: int | None = None,
) -> Optional[SalesforceClient]:
    """Get an authenticated Salesforce client for the given tenant from
    stored tokens. tenant_id is required — there is no global lookup, every
    crm_connections row is owned by exactly one tenant.

    When conn_id is supplied, the lookup is by id but still scoped to
    tenant_id (defense-in-depth: prevents tenant A from reading tenant B's
    connection by passing B's id)."""
    if conn_id is not None:
        result = await db.execute(
            select(CRMConnection).where(
                CRMConnection.id == conn_id,
                CRMConnection.tenant_id == tenant_id,
            )
        )
    else:
        result = await db.execute(
            select(CRMConnection).where(
                CRMConnection.tenant_id == tenant_id,
                CRMConnection.platform == "Salesforce",
                CRMConnection.status == "connected",
            )
        )
    conn = result.scalar_one_or_none()

    if not conn or not conn.oauth_tokens:
        return None

    try:
        tokens = json.loads(conn.oauth_tokens)
    except json.JSONDecodeError:
        return None

    client = SalesforceClient(
        instance_url=tokens["instance_url"],
        access_token=tokens["access_token"],
    )

    # Test the connection
    test = await client.test_connection()
    if not test.get("connected"):
        # Try refreshing the token
        if tokens.get("refresh_token"):
            new_tokens = await refresh_access_token(
                refresh_token=tokens["refresh_token"],
                client_id=settings.SALESFORCE_CLIENT_ID,
                client_secret=settings.SALESFORCE_CLIENT_SECRET,
                environment=conn.environment,
            )
            if "error" not in new_tokens:
                tokens["access_token"] = new_tokens["access_token"]
                tokens["instance_url"] = new_tokens["instance_url"]
                conn.oauth_tokens = json.dumps(tokens)
                await db.commit()

                client = SalesforceClient(
                    instance_url=tokens["instance_url"],
                    access_token=tokens["access_token"],
                )
            else:
                logger.error(f"Token refresh failed: {new_tokens['error']}")
                conn.status = "disconnected"
                conn.health = 0
                await db.commit()
                return None

    # Record a real liveness signal — no more hardcoded 99.8 fiction.
    hc = await client.health_check()
    conn.health = 100.0 if hc.get("healthy") else 0.0
    conn.last_synced = datetime.now(timezone.utc)
    await db.commit()

    return client
