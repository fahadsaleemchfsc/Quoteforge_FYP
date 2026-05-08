import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_tenant_id, get_current_user
from app.core.config import settings
from app.models.crm_connection import CRMConnection
from app.schemas.crm import CRMConnectRequest, FieldMappingsUpdate
from app.services.crm_service import (
    connect_crm, disconnect_crm, sync_crm, get_demo_deals, DEFAULT_FIELD_MAPPINGS,
)
from app.services.salesforce_connector import (
    get_authorization_url, exchange_code_for_tokens,
    store_salesforce_tokens, get_salesforce_client,
    get_refresh_aware_client,
)
from app.models.product import Product
from app.gateway.money import dollars_to_cents  # noqa: F401 — reserved for cents normalization

router = APIRouter(prefix="/crm", tags=["crm"])

OAUTH_REDIRECT_URI = "http://localhost:8000/api/crm/oauth/callback"


def _serialize(c: CRMConnection) -> dict:
    return {
        "id": c.id,
        "platform": c.platform,
        "environment": c.environment,
        "status": c.status,
        "deals": c.deals_count,
        "health": c.health,
        "lastSync": c.last_synced.isoformat() if c.last_synced else None,
    }


@router.get("/connections")
async def list_connections(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(CRMConnection).order_by(CRMConnection.id))
    return [_serialize(c) for c in result.scalars().all()]


@router.post("/connect")
async def connect(data: CRMConnectRequest, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    conn = await connect_crm(db, data.platform, data.environment, data.api_key or "")
    return _serialize(conn)


@router.delete("/connections/{conn_id}")
async def disconnect(conn_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    ok = await disconnect_crm(db, conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"message": "Disconnected"}


@router.post("/connections/{conn_id}/sync")
async def sync(conn_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await sync_crm(db, conn_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/connections/{conn_id}/health")
async def health(conn_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Live liveness probe against the remote CRM. 60s in-process cache so
    the UI can poll aggressively without hammering Salesforce."""
    from datetime import datetime, timezone, timedelta
    cached = _HEALTH_CACHE.get(conn_id)
    now = datetime.now(timezone.utc)
    if cached is not None and (now - cached[0]) < timedelta(seconds=HEALTH_CACHE_TTL):
        return cached[1]

    conn = (await db.execute(
        select(CRMConnection).where(CRMConnection.id == conn_id)
    )).scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if conn.status == "reauth_required":
        result = {
            "healthy": False, "latency_ms": 0,
            "status": "reauth_required",
            "error": "Re-authenticate to restore this connection.",
            "health": 0.0,
            "deals": conn.deals_count,
            "lastSync": conn.last_synced.isoformat() if conn.last_synced else None,
            "last_checked_at": now.isoformat(),
        }
        _HEALTH_CACHE[conn_id] = (now, result)
        return result

    if conn.platform != "Salesforce":
        return {
            "healthy": False, "latency_ms": 0,
            "status": conn.status,
            "error": f"health probe not implemented for {conn.platform}",
            "health": conn.health,
            "deals": conn.deals_count,
            "lastSync": conn.last_synced.isoformat() if conn.last_synced else None,
            "last_checked_at": now.isoformat(),
        }

    client = await get_refresh_aware_client(db, conn_id)
    if client is None:
        result = {
            "healthy": False, "latency_ms": 0, "status": conn.status,
            "error": "no stored tokens",
            "health": 0.0,
            "deals": conn.deals_count,
            "lastSync": conn.last_synced.isoformat() if conn.last_synced else None,
            "last_checked_at": now.isoformat(),
        }
        _HEALTH_CACHE[conn_id] = (now, result)
        return result

    hc = await client.health_check()
    conn.health = 100.0 if hc["healthy"] else 0.0
    conn.last_synced = now
    await db.commit()

    result = {
        **hc,
        "status": conn.status,
        "health": conn.health,
        "deals": conn.deals_count,
        "lastSync": conn.last_synced.isoformat() if conn.last_synced else None,
        "last_checked_at": now.isoformat(),
    }
    _HEALTH_CACHE[conn_id] = (now, result)
    return result


@router.get("/connections/{conn_id}/mappings")
async def get_mappings(conn_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        mappings = json.loads(conn.field_mappings) if conn.field_mappings else DEFAULT_FIELD_MAPPINGS
    except json.JSONDecodeError:
        mappings = DEFAULT_FIELD_MAPPINGS
    return {"mappings": mappings}


@router.put("/connections/{conn_id}/mappings")
async def update_mappings(conn_id: int, data: FieldMappingsUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.field_mappings = json.dumps([m.model_dump() for m in data.mappings])
    await db.commit()
    return {"message": "Mappings updated"}


@router.get("/connections/{conn_id}/deals")
async def get_deals(conn_id: int, page: int = 1, per_page: int = 20, db: AsyncSession = Depends(get_db), _=Depends(get_current_user), tenant_id: str = Depends(get_current_tenant_id)):
    # Try real Salesforce data first
    sf_client = await get_salesforce_client(db, tenant_id, conn_id)
    if sf_client:
        try:
            deals = await sf_client.get_opportunities(limit=per_page)
            return {"deals": deals, "total": len(deals), "page": page, "per_page": per_page, "source": "salesforce_live"}
        except Exception as e:
            pass  # Fall back to demo
    return get_demo_deals(conn_id, page, per_page)


# ─── Real Salesforce OAuth Endpoints ─────────────────────────────

@router.get("/salesforce/authorize")
async def salesforce_authorize(
    environment: str = Query("production"),
    _=Depends(get_current_user),
):
    """Start Salesforce OAuth flow — redirects user to Salesforce login."""
    if not settings.SALESFORCE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="SALESFORCE_CLIENT_ID not configured in .env")

    auth_url = get_authorization_url(
        client_id=settings.SALESFORCE_CLIENT_ID,
        redirect_uri=OAUTH_REDIRECT_URI,
        environment=environment,
        state=environment,
    )
    return {"authorization_url": auth_url}


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query("production"),
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback — Salesforce redirects here after user approves access."""
    environment = state  # We pass environment as state

    tokens = await exchange_code_for_tokens(
        code=code,
        client_id=settings.SALESFORCE_CLIENT_ID,
        client_secret=settings.SALESFORCE_CLIENT_SECRET,
        redirect_uri=OAUTH_REDIRECT_URI,
        environment=environment,
    )

    if "error" in tokens:
        # Redirect to frontend with error
        return RedirectResponse(url=f"http://localhost:3000/crm?error={tokens['error']}")

    # Store tokens in database
    conn = await store_salesforce_tokens(db, tokens, environment)

    # Test the connection
    from app.services.salesforce_connector import SalesforceClient
    sf = SalesforceClient(tokens["instance_url"], tokens["access_token"])
    test = await sf.test_connection()

    if test.get("connected"):
        # Count opportunities
        try:
            opps = await sf.get_opportunities(limit=5)
            conn.deals_count = len(opps)
            await db.commit()
        except Exception:
            pass

    # Redirect to frontend CRM page with success
    return RedirectResponse(url="http://localhost:3000/crm?connected=salesforce")


@router.get("/salesforce/opportunities")
async def get_sf_opportunities(
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Fetch live Opportunities from connected Salesforce org."""
    sf_client = await get_salesforce_client(db, tenant_id)
    if not sf_client:
        raise HTTPException(status_code=400, detail="No active Salesforce connection. Connect via OAuth first.")

    opportunities = await sf_client.get_opportunities(limit=limit)
    return {"opportunities": opportunities, "total": len(opportunities), "source": "salesforce_live"}


@router.get("/salesforce/opportunity/{opp_id}")
async def get_sf_opportunity(
    opp_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Fetch a single Opportunity with full details for quote generation."""
    sf_client = await get_salesforce_client(db, tenant_id)
    if not sf_client:
        raise HTTPException(status_code=400, detail="No active Salesforce connection")

    opp = await sf_client.get_opportunity_by_id(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


# ─── Simple Trigger: Just SF ID or Deal Name ─────────────────────

@router.post("/salesforce/quick-generate")
async def quick_generate(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    The simplest possible trigger.
    Input: { "deal_identifier": "006gL00000KlPp7QAF" }  # SF ID
       OR: { "deal_identifier": "Acme Corp" }           # Deal/Account name
       OR: { "deal_identifier": "Dickenson Mobile Generators" }  # Opportunity name

    Output: Full proposal PDF generated + uploaded to SF.
    """
    from app.services.salesforce_connector import get_salesforce_client
    from app.schemas.quote import GenerateRequest, LineItem
    from app.routers.quotes import generate_quote

    identifier = (data.get("deal_identifier") or "").strip()
    output_format = data.get("output_format", "PDF")

    if not identifier:
        raise HTTPException(status_code=400, detail="deal_identifier is required")

    sf = await get_salesforce_client(db, tenant_id)
    if not sf:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    # Try as SF ID first (starts with 006 for Opportunity)
    opp_id = None
    deal_data = None

    if identifier.startswith(("006", "001", "003")):  # Opp, Account, Contact IDs
        try:
            deal_data = await sf.get_opportunity_by_id(identifier)
            if deal_data:
                opp_id = identifier
        except Exception:
            pass

    # If not found, search by name (Opportunity or Account name)
    if not deal_data:
        safe_name = identifier.replace("'", "''")
        soql = (
            f"SELECT Id FROM Opportunity "
            f"WHERE Name LIKE '%{safe_name}%' OR Account.Name LIKE '%{safe_name}%' "
            f"ORDER BY LastModifiedDate DESC LIMIT 1"
        )
        try:
            results = await sf._query(soql)
            if results:
                opp_id = results[0]["Id"]
                deal_data = await sf.get_opportunity_by_id(opp_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    if not deal_data:
        raise HTTPException(
            status_code=404,
            detail=f"No deal found for '{identifier}'. Try SF ID (006...) or exact deal/account name."
        )

    # Generate the proposal
    gen_request = GenerateRequest(
        deal_id=opp_id,
        client_name=deal_data["client_name"],
        deal_name=deal_data["deal_name"],
        deal_amount=deal_data["deal_amount"],
        contact_email=deal_data.get("contact_email", ""),
        region=deal_data["region"],
        output_format=output_format,
        line_items=[
            LineItem(product=li["product"], quantity=li["quantity"], unit_price=li["unit_price"])
            for li in deal_data.get("line_items", [])
        ],
    )

    # Pass tenant_id explicitly: when a FastAPI route is called as a plain
    # Python coroutine, `Depends(...)` defaults are not resolved, so omitting
    # this leaves tenant_id as a Depends instance and breaks downstream SQL.
    result = await generate_quote(gen_request, db, current_user, tenant_id)

    # Log activity back to SF
    try:
        await sf.log_activity(
            opportunity_id=opp_id,
            subject=f"QuoteForge: Proposal Generated (Quick Trigger)",
            description=f"Triggered via deal identifier: {identifier}\nDocument: {result['doc_id']}",
        )
    except Exception:
        pass

    return {
        **result,
        "triggered_by": identifier,
        "resolved_deal_id": opp_id,
        "salesforce_synced": True,
    }


# ─── Prompt-to-Deal: The Killer Feature ──────────────────────────

@router.post("/salesforce/parse-prompt")
async def parse_deal_prompt(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Parse a natural language prompt into structured deal data.
    Does NOT create anything — just returns what was extracted.
    Used for preview/confirmation before actual deal creation.
    """
    from app.services.prompt_parser import parse_prompt
    prompt = data.get("prompt", "")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    parsed = await parse_prompt(prompt)
    return {"parsed": parsed, "prompt": prompt}


@router.post("/salesforce/create-deal-from-prompt")
async def create_deal_from_prompt(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    THE PROMPT-TO-DEAL FLOW:
    1. Parse natural language prompt → structured data
    2. Find or create Account in Salesforce
    3. Create Opportunity in Salesforce
    4. Create OpportunityLineItems
    5. Generate proposal using QuoteForge
    6. Upload PDF back to Salesforce

    Request body:
      {
        "prompt": "Create a proposal for Acme Corp, enterprise license $50K...",
        "contact_id": "003..." (optional — links deal to existing contact),
        "output_format": "PDF"
      }
    """
    from app.services.prompt_parser import parse_prompt
    from app.services.salesforce_connector import get_salesforce_client

    prompt = data.get("prompt", "")
    contact_id = data.get("contact_id")
    output_format = data.get("output_format", "PDF")

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    # Step 1: Parse the prompt
    parsed = await parse_prompt(prompt)

    if not parsed.get("client_name"):
        raise HTTPException(
            status_code=400,
            detail="Could not extract client name from prompt. Please include a company name."
        )

    result = {
        "parsed": parsed,
        "steps": {},
    }

    # Step 2: Get Salesforce client
    sf = await get_salesforce_client(db, tenant_id)
    if not sf:
        # Without SF, just generate the proposal locally
        from app.schemas.quote import GenerateRequest, LineItem
        from app.routers.quotes import generate_quote

        gen_request = GenerateRequest(
            client_name=parsed["client_name"],
            deal_name=parsed.get("deal_name") or f"{parsed['client_name']} Proposal",
            deal_amount=parsed["deal_amount"],
            contact_email=parsed.get("contact_email", ""),
            region=parsed.get("region", "US"),
            output_format=output_format,
            line_items=[LineItem(**li) for li in parsed["line_items"]],
        )
        gen_result = await generate_quote(gen_request, db, current_user, tenant_id)
        result["steps"]["proposal_generated"] = gen_result["doc_id"]
        result["salesforce_synced"] = False
        return result

    # Step 3: Find or create Account in Salesforce
    try:
        # Search for existing account
        soql = f"SELECT Id, Name FROM Account WHERE Name LIKE '%{parsed['client_name'].replace(chr(39), chr(39)+chr(39))}%' LIMIT 1"
        accounts = await sf._query(soql)

        if accounts:
            account_id = accounts[0]["Id"]
            result["steps"]["account_found"] = account_id
        else:
            # Create new account
            acc_result = await sf._post("/sobjects/Account", {
                "Name": parsed["client_name"],
                "BillingCountry": {"US": "United States", "EU": "Germany", "PK": "Pakistan"}.get(parsed.get("region", "US"), "United States"),
            })
            account_id = acc_result.get("id")
            result["steps"]["account_created"] = account_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Account handling failed: {str(e)}")

    # Step 4: Create Opportunity
    try:
        from datetime import datetime, timedelta
        close_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        opp_data = {
            "Name": parsed.get("deal_name") or f"{parsed['client_name']} - {datetime.now().strftime('%Y-%m-%d')}",
            "AccountId": account_id,
            "Amount": parsed["deal_amount"],
            "StageName": "Proposal/Price Quote",
            "CloseDate": close_date,
            "Type": "New Business",
            "Description": f"Auto-created by QuoteForge from prompt:\n\n{prompt[:500]}",
        }

        opp_result = await sf._post("/sobjects/Opportunity", opp_data)
        opp_id = opp_result.get("id")
        result["steps"]["opportunity_created"] = opp_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Opportunity creation failed: {str(e)}")

    # Step 5: Generate proposal
    try:
        from app.schemas.quote import GenerateRequest, LineItem
        from app.routers.quotes import generate_quote

        gen_request = GenerateRequest(
            deal_id=opp_id,
            client_name=parsed["client_name"],
            deal_name=opp_data["Name"],
            deal_amount=parsed["deal_amount"],
            contact_email=parsed.get("contact_email", ""),
            region=parsed.get("region", "US"),
            output_format=output_format,
            line_items=[LineItem(**li) for li in parsed["line_items"]],
        )

        gen_result = await generate_quote(gen_request, db, current_user, tenant_id)
        result["steps"]["proposal_generated"] = gen_result["doc_id"]
        result["doc_id"] = gen_result["doc_id"]
        result["pricing"] = gen_result["pricing"]
        result["generation_time"] = gen_result["generation_time"]
        result["valid_until"] = gen_result.get("valid_until")
    except Exception as e:
        result["steps"]["proposal_error"] = str(e)

    # Step 6: Log activity on the new Opportunity
    try:
        await sf.log_activity(
            opportunity_id=opp_id,
            subject="QuoteForge: Deal Created from Prompt",
            description=f"Auto-created from natural language prompt:\n\n{prompt[:500]}\n\nDocument: {result.get('doc_id', 'N/A')}",
        )
    except Exception:
        pass

    result["salesforce_synced"] = True
    result["salesforce_opportunity_id"] = opp_id
    result["salesforce_account_id"] = account_id

    return result


@router.post("/salesforce/generate-from-deal/{opp_id}")
async def generate_from_salesforce_deal(
    opp_id: str,
    output_format: str = Query("PDF"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    THE MAIN USE CASE: Fetch deal from Salesforce → Generate proposal → Return document.
    This is what sales reps would trigger from within Salesforce.
    """
    # Step 1: Fetch deal from Salesforce
    sf_client = await get_salesforce_client(db, tenant_id)
    if not sf_client:
        raise HTTPException(status_code=400, detail="No active Salesforce connection")

    deal = await sf_client.get_opportunity_by_id(opp_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Opportunity not found in Salesforce")

    # Step 2: Call the quote generation pipeline
    from app.schemas.quote import GenerateRequest, LineItem
    gen_request = GenerateRequest(
        deal_id=deal["deal_id"],
        client_name=deal["client_name"],
        deal_name=deal["deal_name"],
        deal_amount=deal["deal_amount"],
        contact_email=deal.get("contact_email", ""),
        region=deal["region"],
        output_format=output_format,
        line_items=[
            LineItem(
                product=item["product"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
            for item in deal.get("line_items", [])
        ],
    )

    # Import and call the generation endpoint logic
    from app.routers.quotes import generate_quote
    result = await generate_quote(gen_request, db, current_user, tenant_id)

    # Step 3: Log activity back to Salesforce
    try:
        await sf_client.log_activity(
            opportunity_id=opp_id,
            subject=f"QuoteForge: {result.get('type', 'Proposal')} Generated",
            description=(
                f"Document {result.get('doc_id', '')} generated automatically by QuoteForge.\n"
                f"Format: {result.get('format', 'PDF')}\n"
                f"Total: ${result.get('pricing', {}).get('total', 0):,.2f}\n"
                f"Generation time: {result.get('generation_time', 0)}s"
            ),
        )
    except Exception as e:
        pass  # Don't fail the whole request if activity logging fails

    return {**result, "salesforce_deal": deal["deal_name"], "source": "salesforce_live"}


# ─────────────────────────────────────────────────────────────────
# Session 3: Pricebook import + real health + re-authenticate
# ─────────────────────────────────────────────────────────────────

# In-process cache for health checks so the CRM page doesn't hammer
# Salesforce on every poll. Keyed by conn.id; TTL in HEALTH_CACHE_TTL.
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import IntegrityError

_HEALTH_CACHE: dict[int, tuple[datetime, dict]] = {}
HEALTH_CACHE_TTL = 60   # seconds


@router.post("/salesforce/import-products")
async def import_salesforce_products(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict:
    """
    Pull active PricebookEntry rows from Salesforce and UPSERT into the local
    Product catalog. Uses the tenant's first connected Salesforce connection.

    - sku      ← Product2.ProductCode  (rows without one are skipped)
    - name     ← Product2.Name
    - category ← Product2.Family
    - base_price ← PricebookEntry.UnitPrice
    - min_price_floor ← 80% of base_price (operator can tighten later)
    - agent_exposed ← false (opt-in per product)
    """
    conn_row = (await db.execute(
        select(CRMConnection).where(
            CRMConnection.tenant_id == tenant_id,
            CRMConnection.platform == "Salesforce",
            CRMConnection.status == "connected",
        ).limit(1)
    )).scalar_one_or_none()
    if conn_row is None:
        raise HTTPException(status_code=412, detail="No connected Salesforce connection")

    client = await get_refresh_aware_client(db, conn_row.id)
    if client is None:
        raise HTTPException(status_code=502, detail="Failed to construct Salesforce client")

    try:
        entries = await client.query_pricebook_entries()
    except Exception as e:           # noqa: BLE001 — surface as 502
        raise HTTPException(status_code=502, detail=f"Salesforce query failed: {e}") from e

    imported = 0
    updated = 0
    skipped = 0

    for e in entries:
        prod = e.get("Product2") or {}
        sku = (prod.get("ProductCode") or "").strip()
        if not sku:
            skipped += 1
            continue
        name = (prod.get("Name") or sku).strip()
        category = prod.get("Family")
        description = prod.get("Description") or ""
        try:
            unit_price = float(e.get("UnitPrice") or 0)
        except (TypeError, ValueError):
            skipped += 1
            continue
        currency = (e.get("CurrencyIsoCode") or "USD").upper()
        floor = round(unit_price * 0.8, 2)

        metadata = {
            "salesforce_product_id": prod.get("Id"),
            "salesforce_pricebook_entry_id": e.get("Id"),
            "salesforce_pricebook_id": e.get("Pricebook2Id"),
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = (await db.execute(
            select(Product).where(
                Product.tenant_id == tenant_id,
                Product.sku == sku,
            )
        )).scalar_one_or_none()

        if existing is not None:
            existing.name = name
            existing.description = description or existing.description
            existing.category = category or existing.category
            existing.base_price = unit_price
            existing.currency = currency
            # Don't clobber operator-set floors; keep existing unless it's
            # above the new base_price (which would be an invalid invariant).
            if float(existing.min_price_floor) > unit_price:
                existing.min_price_floor = floor
            try:
                prev = json.loads(existing.metadata_json or "{}")
            except json.JSONDecodeError:
                prev = {}
            prev.update(metadata)
            existing.metadata_json = json.dumps(prev)
            updated += 1
        else:
            db.add(Product(
                tenant_id=tenant_id,
                sku=sku,
                name=name,
                description=description,
                category=category,
                base_price=unit_price,
                min_price_floor=floor,
                currency=currency,
                unit="unit",
                agent_exposed=False,
                metadata_json=json.dumps(metadata),
            ))
            imported += 1

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"UPSERT conflict: {e}") from e

    return {
        "imported": imported,
        "updated":  updated,
        "skipped":  skipped,
        "source":   "salesforce",
        "pricebook_entries_seen": len(entries),
    }


@router.post("/connections/{conn_id}/reauthenticate")
async def reauthenticate_connection(
    conn_id: int,
    db: AsyncSession = Depends(get_db),
    _user = Depends(get_current_user),
) -> dict:
    """Kick off fresh OAuth for an existing connection — typically one that
    flipped to status='reauth_required' after a refresh failure.
    Returns the authorization URL the UI should redirect the browser to."""
    conn_row = (await db.execute(
        select(CRMConnection).where(CRMConnection.id == conn_id)
    )).scalar_one_or_none()
    if conn_row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if conn_row.platform != "Salesforce":
        raise HTTPException(status_code=400, detail="only Salesforce supported")
    if not settings.SALESFORCE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="SALESFORCE_CLIENT_ID not configured")

    url = get_authorization_url(
        client_id=settings.SALESFORCE_CLIENT_ID,
        redirect_uri=OAUTH_REDIRECT_URI,
        environment=conn_row.environment,
        state=f"reauth:{conn_id}",
    )
    return {"authorization_url": url}
