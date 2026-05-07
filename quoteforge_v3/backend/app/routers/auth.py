from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


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
