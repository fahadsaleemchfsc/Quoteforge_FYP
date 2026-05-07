from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


def _serialize(t: Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "type": t.type,
        "format": t.format,
        "status": t.status,
        "content": t.content,
        "usageCount": t.usage_count,
        "author": t.author,
        "lastModified": t.last_modified.strftime("%b %d, %Y") if t.last_modified else "",
    }


@router.get("")
async def list_templates(
    status: str = Query("", alias="status"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Template)
    if status and status != "all":
        query = query.where(Template.status == status)
    result = await db.execute(query.order_by(Template.id))
    return [_serialize(t) for t in result.scalars().all()]


@router.get("/{template_id}")
async def get_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize(t)


@router.post("")
async def create_template(data: TemplateCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    t = Template(**data.model_dump())
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _serialize(t)


@router.put("/{template_id}")
async def update_template(template_id: int, data: TemplateUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    await db.commit()
    return _serialize(t)


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(t)
    await db.commit()
    return {"message": "Template deleted"}


@router.get("/{template_id}/preview")
async def preview_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        **_serialize(t),
        "preview": f"Preview of {t.name} — {t.type} template in {t.format} format.",
    }


@router.post("/{template_id}/duplicate")
async def duplicate_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    dup = Template(
        name=f"{t.name} (Copy)",
        type=t.type,
        format=t.format,
        status="draft",
        content=t.content,
        author=t.author,
    )
    db.add(dup)
    await db.commit()
    await db.refresh(dup)
    return _serialize(dup)


@router.patch("/{template_id}/activate")
async def activate_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    t.status = "active"
    await db.commit()
    return _serialize(t)


@router.patch("/{template_id}/archive")
async def archive_template(template_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Template).where(Template.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    t.status = "archived"
    await db.commit()
    return _serialize(t)
