"""
Continuous Learning Pipeline
==============================
Each customer's QuoteForge instance continuously improves by learning
from their approved proposals.

Flow:
  1. User generates a proposal
  2. User reviews → either "Approve & Send" or "Edit"
  3. If edited, the edits become training signal
  4. Every N approved proposals, trigger incremental fine-tuning
  5. New model version deployed silently (gradual rollout)

Key principle: DATA STAYS IN THE CUSTOMER'S ORG.
  - Training runs on customer's infrastructure
  - Their model is THEIR model (not shared with other customers)
  - Each customer ends up with a unique, personalized model
"""
import json
import logging
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LEARNING_DATA_DIR = BASE_DIR / "training_data" / "continuous"
LEARNING_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── Feedback Collection ─────────────────────────────────────────

async def record_proposal_feedback(
    db: AsyncSession,
    doc_id: str,
    feedback_type: str,  # "approved" | "edited" | "rejected"
    edited_content: dict = None,
    user_notes: str = "",
):
    """
    Record feedback on a generated proposal.
    This is what makes the model smarter over time.
    """
    from app.models.document_log import DocumentLog
    from app.models.audit_log import AuditLog

    result = await db.execute(select(DocumentLog).where(DocumentLog.doc_id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": "Document not found"}

    # Store feedback in audit log
    audit = AuditLog(
        action=f"feedback_{feedback_type}",
        entity_type="document",
        entity_id=doc_id,
        details=json.dumps({
            "feedback_type": feedback_type,
            "edited_content": edited_content or {},
            "user_notes": user_notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(audit)

    # If approved or edited, save as training signal
    if feedback_type in ("approved", "edited"):
        signal_file = LEARNING_DATA_DIR / f"{doc_id}_signal.json"
        signal_data = {
            "doc_id": doc_id,
            "client": doc.client,
            "deal_name": doc.deal_name,
            "amount": doc.amount,
            "compliance_framework": doc.compliance_framework,
            "feedback_type": feedback_type,
            "edited_content": edited_content,
            "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        signal_file.write_text(json.dumps(signal_data, indent=2, default=str))
        logger.info(f"Training signal saved: {doc_id}")

    await db.commit()
    return {"success": True, "feedback_type": feedback_type}


# ─── Training Trigger ────────────────────────────────────────────

async def check_retrain_trigger(db: AsyncSession) -> dict:
    """
    Decide if it's time to retrain.
    Triggers:
      - 50+ new approved proposals since last training
      - OR 7 days since last training AND 10+ approved
      - OR manual trigger
    """
    # Count approved signals since last training
    last_training_file = LEARNING_DATA_DIR / "last_training.json"

    last_training_date = None
    if last_training_file.exists():
        data = json.loads(last_training_file.read_text())
        last_training_date = datetime.fromisoformat(data["completed_at"])

    # Count signal files newer than last training
    new_signals = []
    for signal_file in LEARNING_DATA_DIR.glob("*_signal.json"):
        mtime = datetime.fromtimestamp(signal_file.stat().st_mtime, tz=timezone.utc)
        if last_training_date is None or mtime > last_training_date:
            new_signals.append(signal_file)

    days_since = (datetime.now(timezone.utc) - last_training_date).days if last_training_date else 999

    should_train = (
        len(new_signals) >= 50 or
        (days_since >= 7 and len(new_signals) >= 10)
    )

    return {
        "new_approved_proposals": len(new_signals),
        "days_since_last_training": days_since,
        "should_retrain": should_train,
        "last_training": last_training_date.isoformat() if last_training_date else None,
        "trigger_reason": (
            "volume_threshold" if len(new_signals) >= 50
            else ("time_threshold" if should_train else "waiting")
        ),
    }


# ─── Training Data Preparation ───────────────────────────────────

def prepare_incremental_training_data() -> Path:
    """Compile recent feedback signals into training data."""
    signals = []
    for signal_file in LEARNING_DATA_DIR.glob("*_signal.json"):
        signals.append(json.loads(signal_file.read_text()))

    if not signals:
        return None

    # Convert signals to training format
    training_samples = []
    for signal in signals:
        if signal["feedback_type"] != "approved" and not signal.get("edited_content"):
            continue

        # Build training sample from approved proposal
        prompt = (
            f"Generate a proposal for {signal['client']}.\n"
            f"Deal: {signal['deal_name']}\n"
            f"Amount: ${signal['amount']:,.2f}\n"
            f"Compliance: {signal['compliance_framework']}"
        )

        # If edited, use edited version as target (high-quality signal)
        # If just approved, we'd read the original generated content from file
        if signal.get("edited_content"):
            for section, content in signal["edited_content"].items():
                training_samples.append({
                    "instruction": f"Generate the {section} section for this proposal.\n\n{prompt}",
                    "output": content,
                    "source": "continuous_learning",
                    "signal_type": signal["feedback_type"],
                })

    # Write combined dataset
    output_file = LEARNING_DATA_DIR / f"incremental_train_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(output_file, "w") as f:
        for sample in training_samples:
            f.write(json.dumps(sample, default=str) + "\n")

    logger.info(f"Prepared {len(training_samples)} incremental training samples → {output_file}")
    return output_file


# ─── Scheduled Retraining Task ───────────────────────────────────

async def run_incremental_retraining(force: bool = False) -> dict:
    """
    Run incremental fine-tuning on new approved proposals.
    This is typically triggered by a cron job.
    """
    # Check if we should train
    from app.core.database import async_session

    async with async_session() as db:
        trigger = await check_retrain_trigger(db)

    if not force and not trigger["should_retrain"]:
        return {
            "status": "skipped",
            "reason": trigger["trigger_reason"],
            "details": trigger,
        }

    # Prepare training data
    training_file = prepare_incremental_training_data()
    if not training_file:
        return {"status": "skipped", "reason": "no_training_data"}

    # Trigger MLX training (in subprocess to avoid blocking)
    try:
        training_data_dir = LEARNING_DATA_DIR / "mlx_incremental"
        training_data_dir.mkdir(exist_ok=True)

        # Convert to MLX format
        mlx_file = training_data_dir / "train.jsonl"
        with open(training_file) as fin, open(mlx_file, "w") as fout:
            for line in fin:
                s = json.loads(line)
                text = f"<|im_start|>user\n{s['instruction']}<|im_end|>\n<|im_start|>assistant\n{s['output']}<|im_end|>"
                fout.write(json.dumps({"text": text}) + "\n")

        # Copy as valid.jsonl too
        (training_data_dir / "valid.jsonl").write_text(mlx_file.read_text())
        (training_data_dir / "test.jsonl").write_text(mlx_file.read_text())

        # Start training in background
        adapter_path = BASE_DIR / "model_training" / "mlx_output" / f"quoteforge-v{datetime.now().strftime('%Y%m%d')}"

        cmd = [
            "python", "-m", "mlx_lm", "lora",
            "--model", "mlx-community/Llama-3.2-1B-Instruct-4bit",
            "--train",
            "--data", str(training_data_dir),
            "--resume-adapter-file", str(BASE_DIR / "model_training" / "mlx_output" / "quoteforge-v2" / "adapters.safetensors"),
            "--iters", "200",  # Light incremental update
            "--batch-size", "1",
            "--num-layers", "8",
            "--learning-rate", "5e-5",  # Lower LR for incremental
            "--adapter-path", str(adapter_path),
            "--max-seq-length", "1024",
        ]

        # Log training start
        last_training_file = LEARNING_DATA_DIR / "last_training.json"
        last_training_file.write_text(json.dumps({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "samples": sum(1 for _ in open(training_file)),
            "adapter_path": str(adapter_path),
            "base_adapter": "quoteforge-v2",
        }, indent=2))

        # Run in background (don't await — let it finish async)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return {
            "status": "training_started",
            "pid": process.pid,
            "samples": sum(1 for _ in open(training_file)),
            "adapter_path": str(adapter_path),
            "expected_duration_minutes": 5,
            "details": trigger,
        }

    except Exception as e:
        logger.error(f"Retraining failed to start: {e}")
        return {"status": "failed", "error": str(e)}


# ─── Stats Dashboard ─────────────────────────────────────────────

async def get_learning_stats(db: AsyncSession) -> dict:
    """Return stats about the continuous learning pipeline."""
    trigger_info = await check_retrain_trigger(db)

    # Count all signals ever collected
    total_signals = len(list(LEARNING_DATA_DIR.glob("*_signal.json")))

    # Count by feedback type
    approved = 0
    edited = 0
    for signal_file in LEARNING_DATA_DIR.glob("*_signal.json"):
        try:
            data = json.loads(signal_file.read_text())
            if data["feedback_type"] == "approved":
                approved += 1
            elif data["feedback_type"] == "edited":
                edited += 1
        except Exception:
            pass

    # Check current model version
    current_adapter = BASE_DIR / "model_training" / "mlx_output" / "quoteforge-v2"
    current_version = "v2" if current_adapter.exists() else "v1"

    return {
        "current_model_version": current_version,
        "total_feedback_collected": total_signals,
        "approved_proposals": approved,
        "edited_proposals": edited,
        "new_since_last_training": trigger_info["new_approved_proposals"],
        "days_since_last_training": trigger_info["days_since_last_training"],
        "next_training_when": (
            "50 approved proposals" if trigger_info["new_approved_proposals"] < 50
            else "ready to train"
        ),
        "ready_to_retrain": trigger_info["should_retrain"],
    }
