import re
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import (
    verify_password, create_access_token, get_current_user, hash_password,
    is_super_admin,
)
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    """Lowercase, dash-separated, alnum-only slug from a workspace name.

    Falls back to 'workspace' if the input is all-symbols. The /register
    endpoint suffixes a short random tail if the bare slug collides, so
    this just needs to produce a stable base.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is deactivated. Contact your administrator.")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_slug": user.tenant.slug if user.tenant else None,
    })

    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "department": user.department,
            "status": user.status,
            "avatar": user.avatar,
            "quotesGenerated": user.quotes_generated,
            "lastLogin": user.last_login.isoformat() if user.last_login else None,
            "isSuperAdmin": is_super_admin(user),
        },
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Self-serve workspace creation — powers /signup in the frontend.

    Provisions a new Tenant plus its first admin User in a single
    transaction, then issues a JWT exactly like /login so the caller
    can drop straight into the app.
    """
    email = req.email.lower()

    # Email-uniqueness check first — clearer error than a UNIQUE
    # violation surfacing as a 500 from the DB layer.
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists. Try signing in.",
        )

    # Slug uniqueness — append a 4-char random tail on collision so
    # two "Acme" workspaces can coexist.
    base = _slugify(req.workspace_name)
    slug = base
    for _ in range(5):
        slug_clash = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if slug_clash.scalar_one_or_none() is None:
            break
        slug = f"{base}-{secrets.token_hex(2)}"
    else:
        raise HTTPException(
            status_code=409,
            detail="Could not allocate a workspace slug — try a different name.",
        )

    tenant = Tenant(slug=slug, name=req.workspace_name.strip())
    db.add(tenant)
    await db.flush()  # populate tenant.id before we FK to it

    user = User(
        name=email.split("@", 1)[0].replace(".", " ").title(),
        email=email,
        password_hash=hash_password(req.password),
        role="admin",
        status="active",
        tenant_id=tenant.id,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant.slug,
    })
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "department": user.department,
            "status": user.status,
            "avatar": user.avatar,
            "quotesGenerated": user.quotes_generated,
            "lastLogin": user.last_login.isoformat() if user.last_login else None,
            "workspace": {"slug": tenant.slug, "name": tenant.name},
        },
    )


@router.post("/logout")
async def logout():
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "status": user.status,
        "avatar": user.avatar,
        "quotesGenerated": user.quotes_generated,
        "lastLogin": user.last_login.isoformat() if user.last_login else None,
        "isSuperAdmin": is_super_admin(user),
    }


@router.post("/refresh")
async def refresh_token(user: User = Depends(get_current_user)):
    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_slug": user.tenant.slug if user.tenant else None,
    })
    return {"access_token": token, "token_type": "bearer"}
