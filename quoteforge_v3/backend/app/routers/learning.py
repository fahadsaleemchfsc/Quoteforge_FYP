"""
Continuous Learning API
=========================
Endpoints for feedback collection and model retraining.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.services.continuous_learning import (
    record_proposal_feedback,
    check_retrain_trigger,
    run_incremental_retraining,
    get_learning_stats,
)

router = APIRouter(prefix="/learning", tags=["continuous-learning"])


@router.post("/feedback")
async def submit_feedback(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Submit feedback on a generated proposal.
    This is what makes the model learn over time.

    Body:
      { "doc_id": "DOC-xxxx",
        "feedback_type": "approved" | "edited" | "rejected",
        "edited_content": { "Cover Letter": "...", "Scope": "..." },  # if edited
        "user_notes": "..." }
    """
    doc_id = data.get("doc_id")
    feedback_type = data.get("feedback_type", "approved")

    if not doc_id:
        raise HTTPException(status_code=400, detail="doc_id required")

    if feedback_type not in ("approved", "edited", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid feedback_type")

    result = await record_proposal_feedback(
        db=db,
        doc_id=doc_id,
        feedback_type=feedback_type,
        edited_content=data.get("edited_content"),
        user_notes=data.get("user_notes", ""),
    )
    return result


@router.get("/stats")
async def learning_stats(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Get continuous learning pipeline stats."""
    return await get_learning_stats(db)


@router.get("/check-retrain")
async def check_retrain(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Check if model should be retrained."""
    return await check_retrain_trigger(db)


@router.post("/retrain")
async def trigger_retrain(
    force: bool = False,
    _=Depends(require_admin),
):
    """Manually trigger incremental retraining (admin only)."""
    return await run_incremental_retraining(force=force)
