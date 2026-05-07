from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user, require_admin, hash_password
from app.models.user import User
from app.schemas.user import UserOut, UserInvite, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    search: str = Query("", alias="search"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(User)
    if search:
        query = query.where(
            User.name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
        )
    result = await db.execute(query.order_by(User.id))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "department": u.department,
            "status": u.status,
            "avatar": u.avatar,
            "quotesGenerated": u.quotes_generated,
            "lastLogin": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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


@router.post("/invite")
async def invite_user(data: UserInvite, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(select(User).where(User.email == data.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    initials = "".join(w[0].upper() for w in data.name.split()[:2])
    user = User(
        name=data.name,
        email=data.email.lower(),
        password_hash=hash_password("welcome123"),  # default password
        role=data.role,
        department=data.department,
        avatar=initials,
        status="active",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User invited", "id": user.id, "default_password": "welcome123"}


@router.put("/{user_id}")
async def update_user(user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    return {"message": "User updated"}


@router.patch("/{user_id}/deactivate")
async def deactivate_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "inactive"
    await db.commit()
    return {"message": "User deactivated"}


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}
