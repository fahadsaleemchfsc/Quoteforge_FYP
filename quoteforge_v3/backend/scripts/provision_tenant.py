"""
Provision a new tenant + admin user for a client installing the QuoteForge app.

Idempotent — running twice with the same slug skips creation and warns.

Usage:
    python -m scripts.provision_tenant <slug> <company-name> [admin-email] [admin-password]

Examples:
    python -m scripts.provision_tenant client-sandbox "Client Sandbox"
    python -m scripts.provision_tenant acme "Acme Corp" admin@acme.io mypassword123

Design notes
------------
- Tenant model (app/models/tenant.py) has `id` (UUID str) + `slug` + `name`.
  No `subdomain` column exists on the current schema; the slug serves that role.
- User model (app/models/user.py) has no `tenant_id` FK — the current backend
  resolves tenant context via DEFAULT_TENANT_SLUG in most routers. Admin
  accounts are shared across the install. The script creates the User row
  anyway so the new tenant has a usable admin login, and prints a note.
- Password hashing reuses the existing bcrypt helper in app/core/security.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from typing import Optional

from sqlalchemy import select

from app.core.database import async_session, init_db
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User


def _usage_and_exit(code: int = 2) -> None:
    print(__doc__, file=sys.stderr)
    sys.exit(code)


def _generate_password() -> str:
    # 16 hex chars = 64 bits of entropy. Prefixed so ops can eyeball-spot
    # auto-generated admin credentials in shared logs.
    return f"qf_{secrets.token_hex(8)}"


async def provision(
    slug: str,
    company_name: str,
    admin_email: Optional[str],
    admin_password: Optional[str],
) -> int:
    # Make sure the schema is current — safe to call in a CLI script because
    # init_db uses SQLAlchemy's create_all (idempotent on existing tables).
    await init_db()

    email = admin_email or f"admin@{slug}.io"
    password = admin_password or _generate_password()

    async with async_session() as db:
        existing = (await db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )).scalar_one_or_none()
        if existing is not None:
            existing_user = (await db.execute(
                select(User).where(User.email == email)
            )).scalar_one_or_none()
            print(
                f"⚠  Tenant '{slug}' already exists (id={existing.id}). "
                f"Skipping create — provisioning is idempotent."
            )
            if existing_user is None:
                print(
                    f"   (no User row for {email} — if you need one, run "
                    f"with a different admin email or delete the tenant first.)"
                )
            return 0

        tenant = Tenant(slug=slug, name=company_name)
        db.add(tenant)
        await db.flush()   # populate tenant.id before user insert

        user = User(
            name=f"{company_name} Admin",
            email=email,
            password_hash=hash_password(password),
            role="admin",
            department="",
            status="active",
            avatar="",
        )
        db.add(user)
        await db.commit()
        await db.refresh(tenant)
        await db.refresh(user)

    _print_credentials_block(
        tenant_id=tenant.id,
        slug=slug,
        company_name=company_name,
        email=email,
        password=password,
    )
    return 0


def _print_credentials_block(
    *,
    tenant_id: str,
    slug: str,
    company_name: str,
    email: str,
    password: str,
) -> None:
    bar = "─" * 64
    print()
    print(bar)
    print("  ✓ QuoteForge tenant provisioned")
    print(bar)
    print(f"  Tenant ID       : {tenant_id}")
    print(f"  Tenant slug     : {slug}")
    print(f"  Tenant name     : {company_name}")
    print(f"  Admin email     : {email}")
    print(f"  Admin password  : {password}")
    print(bar)
    print(
        "  Paste these into the client's QuoteForgeController.cls auth block\n"
        "  (the email + password fields in getAuthToken() — search for\n"
        "  'admin@quoteforge.io' / 'admin123' and replace)."
    )
    print(
        "  This is the ONLY time the password appears in plaintext. Store it\n"
        "  securely (1Password, Vault, etc.) before closing this terminal."
    )
    print(bar)
    print()


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2 or len(args) > 4:
        _usage_and_exit()

    slug = args[0].strip()
    company_name = args[1].strip()
    admin_email = args[2].strip() if len(args) >= 3 else None
    admin_password = args[3].strip() if len(args) == 4 else None

    if not slug or not company_name:
        _usage_and_exit()

    return asyncio.run(provision(slug, company_name, admin_email, admin_password))


if __name__ == "__main__":
    raise SystemExit(main())
