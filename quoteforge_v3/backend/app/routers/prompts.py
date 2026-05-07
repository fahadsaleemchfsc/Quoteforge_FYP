from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.ai_prompt import AIPrompt
from app.schemas.prompt import PromptCreate, PromptUpdate
from app.services.ai_service import test_prompt as run_test_prompt

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _serialize(p: AIPrompt) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "section": p.section,
        "prompt_text": p.prompt_text,
        "version": p.version,
        "status": p.status,
        "tokens": p.tokens,
        "lastUsed": p.last_used.isoformat() if p.last_used else "Never",
    }


@router.get("")
async def list_prompts(
    status: str = Query("", alias="status"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(AIPrompt)
    if status and status.lower() not in ("", "all"):
        query = query.where(AIPrompt.status == status)
    result = await db.execute(query.order_by(AIPrompt.id))
    return [_serialize(p) for p in result.scalars().all()]


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _serialize(p)


@router.post("")
async def create_prompt(data: PromptCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    p = AIPrompt(**data.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _serialize(p)


@router.put("/{prompt_id}")
async def update_prompt(prompt_id: int, data: PromptUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    await db.commit()
    return _serialize(p)


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await db.delete(p)
    await db.commit()
    return {"message": "Prompt deleted"}


@router.post("/{prompt_id}/test")
async def test_prompt_endpoint(prompt_id: int, context: dict = None, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await run_test_prompt(db, prompt_id, context)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.patch("/{prompt_id}/activate")
async def activate_prompt(prompt_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(AIPrompt).where(AIPrompt.id == prompt_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    p.status = "active"
    await db.commit()
    return _serialize(p)
