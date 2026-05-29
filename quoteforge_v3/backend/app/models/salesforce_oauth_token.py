"""Per-org Salesforce OAuth token store.

Distinct from the legacy CRMConnection.oauth_tokens JSON blob (used by the
older /api/crm flow). This is the canonical store for the new
/api/integrations/salesforce/* one-click flow:

  * Primary key is the Salesforce org id (18-char "00D..."), so connecting
    the same org twice from the same tenant overwrites instead of
    duplicating.
  * tenant_id FK ties the connection back to a QuoteForge tenant so
    sf_request() can look up the right token for the caller.
  * access_token / refresh_token are written through the Fernet helpers
    in app/core/crypto — never store plaintext on disk.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class SalesforceOAuthToken(Base):
    __tablename__ = "salesforce_oauth_tokens"

    # 18-char Salesforce org id ("00D..."), returned by the userinfo
    # endpoint after consent. Acts as natural PK — one row per connected
    # org regardless of how many tenants link to it.
    org_id = Column(String(32), primary_key=True)

    # Per-org REST endpoint, e.g. https://acme.my.salesforce.com.
    # Required for every sf_request — never hardcode login.salesforce.com.
    instance_url = Column(String(512), nullable=False)

    # Fernet-encrypted. Use app.core.crypto.{encrypt_str,decrypt_str}.
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)

    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Space-separated scope list as returned by Salesforce. Stored verbatim
    # so we can audit what was actually granted vs requested.
    scopes = Column(String(512), nullable=False, default="")

    # FK to the QuoteForge tenant that initiated the connect flow. Indexed
    # because the hot lookup is "give me the token for tenant X".
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    tenant = relationship("Tenant", lazy="joined")

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
