"""
CRM Connector Service — handles OAuth 2.0 connections and deal data retrieval
for Salesforce, HubSpot, and Custom CRM platforms.

For the FYP demo, this includes simulated CRM data when real credentials
are not configured.
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.crm_connection import CRMConnection
from app.core.config import settings

logger = logging.getLogger(__name__)

# Simulated deal data for demo purposes
DEMO_DEALS = [
    {
        "deal_id": "DEAL-001",
        "deal_name": "Enterprise License Agreement",
        "client_name": "Acme Corporation",
        "contact_email": "john.smith@acme.com",
        "amount": 75000,
        "stage": "Proposal",
        "region": "US",
        "line_items": [
            {"product": "Enterprise Platform License", "quantity": 1, "unit_price": 50000, "description": "Annual platform license"},
            {"product": "Implementation Services", "quantity": 1, "unit_price": 15000, "description": "Setup and configuration"},
            {"product": "Annual Support & Maintenance", "quantity": 1, "unit_price": 10000, "description": "24/7 support"},
        ],
    },
    {
        "deal_id": "DEAL-002",
        "deal_name": "SaaS Platform Migration",
        "client_name": "TechStart Inc",
        "contact_email": "sarah@techstart.io",
        "amount": 128000,
        "stage": "Negotiation",
        "region": "US",
        "line_items": [
            {"product": "Cloud Migration Services", "quantity": 1, "unit_price": 45000, "description": "Full migration"},
            {"product": "SaaS Platform License (3yr)", "quantity": 1, "unit_price": 63000, "description": "3-year license"},
            {"product": "Training Program", "quantity": 20, "unit_price": 1000, "description": "Per-user training"},
        ],
    },
    {
        "deal_id": "DEAL-003",
        "deal_name": "Managed Services Renewal",
        "client_name": "Lighthouse CRM",
        "contact_email": "procurement@lighthouse.example.com",
        "amount": 45000,
        "stage": "Proposal",
        "region": "EU",
        "line_items": [
            {"product": "Document Management System", "quantity": 1, "unit_price": 30000, "description": "DMS license"},
            {"product": "Support Tier 2 (Annual)", "quantity": 1, "unit_price": 10000, "description": "Premium support"},
            {"product": "Training & Deployment", "quantity": 1, "unit_price": 5000, "description": "On-site training"},
        ],
    },
    {
        "deal_id": "DEAL-004",
        "deal_name": "Data Analytics Suite",
        "client_name": "Global Traders LLC",
        "contact_email": "ops@globaltraders.com",
        "amount": 22500,
        "stage": "Qualification",
        "region": "EU",
        "line_items": [
            {"product": "Analytics Dashboard", "quantity": 1, "unit_price": 12500, "description": "Custom analytics"},
            {"product": "Data Integration Service", "quantity": 1, "unit_price": 7500, "description": "API integrations"},
            {"product": "Monthly Support", "quantity": 12, "unit_price": 208.33, "description": "Monthly support contract"},
        ],
    },
    {
        "deal_id": "DEAL-005",
        "deal_name": "Infrastructure Modernization",
        "client_name": "Nexus Systems",
        "contact_email": "cto@nexus.io",
        "amount": 89000,
        "stage": "Proposal",
        "region": "US",
        "line_items": [
            {"product": "Infrastructure Assessment", "quantity": 1, "unit_price": 15000, "description": "Full audit"},
            {"product": "Cloud Architecture Design", "quantity": 1, "unit_price": 25000, "description": "Architecture blueprint"},
            {"product": "Migration Execution", "quantity": 1, "unit_price": 35000, "description": "Hands-on migration"},
            {"product": "Post-Migration Support (6mo)", "quantity": 1, "unit_price": 14000, "description": "6-month support"},
        ],
    },
]

# Default field mappings
DEFAULT_FIELD_MAPPINGS = [
    {"crm_field": "Deal Name", "system_field": "deal_name", "type": "string"},
    {"crm_field": "Account Name", "system_field": "client_name", "type": "string"},
    {"crm_field": "Contact Email", "system_field": "contact_email", "type": "string"},
    {"crm_field": "Amount", "system_field": "deal_amount", "type": "currency"},
    {"crm_field": "Stage", "system_field": "stage", "type": "string"},
    {"crm_field": "Close Date", "system_field": "close_date", "type": "date"},
    {"crm_field": "Product Line Items", "system_field": "line_items", "type": "array"},
    {"crm_field": "Region", "system_field": "region", "type": "string"},
]


async def connect_crm(db: AsyncSession, platform: str, environment: str = "sandbox", api_key: str = "") -> CRMConnection:
    """Create or update a CRM connection."""
    result = await db.execute(
        select(CRMConnection).where(
            CRMConnection.platform == platform,
            CRMConnection.environment == environment,
        )
    )
    conn = result.scalar_one_or_none()

    if conn:
        conn.status = "connected"
        conn.health = 99.8 if platform == "Salesforce" else 98.2
        conn.deals_count = len(DEMO_DEALS)
        conn.last_synced = datetime.now(timezone.utc)
        conn.field_mappings = json.dumps(DEFAULT_FIELD_MAPPINGS)
        if api_key:
            conn.api_key = api_key
    else:
        conn = CRMConnection(
            platform=platform,
            environment=environment,
            status="connected",
            deals_count=len(DEMO_DEALS),
            health=99.8 if platform == "Salesforce" else 98.2,
            last_synced=datetime.now(timezone.utc),
            field_mappings=json.dumps(DEFAULT_FIELD_MAPPINGS),
            api_key=api_key,
        )
        db.add(conn)

    await db.commit()
    await db.refresh(conn)
    return conn


async def disconnect_crm(db: AsyncSession, conn_id: int) -> bool:
    result = await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        return False
    conn.status = "disconnected"
    conn.health = 0
    await db.commit()
    return True


async def sync_crm(db: AsyncSession, conn_id: int) -> dict:
    result = await db.execute(select(CRMConnection).where(CRMConnection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        return {"error": "Connection not found"}
    conn.last_synced = datetime.now(timezone.utc)
    conn.deals_count = len(DEMO_DEALS)
    conn.health = min(conn.health + 0.1, 100.0) if conn.status == "connected" else 0
    await db.commit()
    return {"message": "Sync completed", "deals_synced": len(DEMO_DEALS)}


def get_demo_deals(conn_id: int = None, page: int = 1, per_page: int = 20):
    """Return demo deals for testing."""
    return {
        "deals": DEMO_DEALS,
        "total": len(DEMO_DEALS),
        "page": page,
        "per_page": per_page,
    }


def get_deal_by_id(deal_id: str) -> dict:
    """Retrieve a specific deal by ID."""
    for deal in DEMO_DEALS:
        if deal["deal_id"] == deal_id:
            return deal
    return None
