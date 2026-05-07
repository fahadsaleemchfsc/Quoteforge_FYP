"""
OpenAI Fine-Tuning Pipeline for QuoteForge
=============================================
Fine-tunes GPT-4o-mini on professional proposal generation data.

Usage:
  1. Set OPENAI_API_KEY in .env
  2. Run generate_training_data.py first
  3. python finetune_openai.py upload     — Upload training files
  4. python finetune_openai.py create     — Start fine-tuning job
  5. python finetune_openai.py status     — Check job status
  6. python finetune_openai.py test       — Test fine-tuned model
"""

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TRAINING_DIR = Path(__file__).parent.parent / "training_data"
MODEL_BASE = "gpt-4o-mini-2024-07-18"  # Base model for fine-tuning
SUFFIX = "quoteforge-v1"

# Track IDs
STATE_FILE = Path(__file__).parent / "finetune_state.json"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def upload_files():
    """Upload training and validation files to OpenAI."""
    state = load_state()

    train_file = TRAINING_DIR / "openai_train.jsonl"
    val_file = TRAINING_DIR / "openai_val.jsonl"

    if not train_file.exists():
        print("ERROR: Training data not found. Run generate_training_data.py first.")
        return

    print("Uploading training file...")
    train_resp = client.files.create(file=open(train_file, "rb"), purpose="fine-tune")
    state["train_file_id"] = train_resp.id
    print(f"  Train file ID: {train_resp.id}")

    if val_file.exists():
        print("Uploading validation file...")
        val_resp = client.files.create(file=open(val_file, "rb"), purpose="fine-tune")
        state["val_file_id"] = val_resp.id
        print(f"  Validation file ID: {val_resp.id}")

    save_state(state)
    print("\nFiles uploaded successfully!")


def create_job():
    """Create a fine-tuning job."""
    state = load_state()

    if "train_file_id" not in state:
        print("ERROR: Upload files first (python finetune_openai.py upload)")
        return

    print(f"Creating fine-tuning job...")
    print(f"  Base model: {MODEL_BASE}")
    print(f"  Suffix: {SUFFIX}")

    params = {
        "training_file": state["train_file_id"],
        "model": MODEL_BASE,
        "suffix": SUFFIX,
        "hyperparameters": {
            "n_epochs": 3,
            "batch_size": "auto",
            "learning_rate_multiplier": "auto",
        },
    }

    if "val_file_id" in state:
        params["validation_file"] = state["val_file_id"]

    job = client.fine_tuning.jobs.create(**params)
    state["job_id"] = job.id
    state["job_status"] = job.status
    save_state(state)

    print(f"\nFine-tuning job created!")
    print(f"  Job ID: {job.id}")
    print(f"  Status: {job.status}")
    print(f"\nRun 'python finetune_openai.py status' to check progress.")


def check_status():
    """Check fine-tuning job status."""
    state = load_state()

    if "job_id" not in state:
        print("ERROR: No active job. Create one first.")
        return

    job = client.fine_tuning.jobs.retrieve(state["job_id"])
    state["job_status"] = job.status
    if job.fine_tuned_model:
        state["fine_tuned_model"] = job.fine_tuned_model
    save_state(state)

    print(f"Job ID: {job.id}")
    print(f"Status: {job.status}")
    print(f"Model: {job.model}")

    if job.fine_tuned_model:
        print(f"\nFine-tuned model: {job.fine_tuned_model}")
        print(f"\nTo use this model, update AI_MODEL in .env:")
        print(f"  AI_MODEL={job.fine_tuned_model}")

    if job.status == "running":
        # Show recent events
        events = client.fine_tuning.jobs.list_events(fine_tuning_job_id=job.id, limit=5)
        print(f"\nRecent events:")
        for event in reversed(events.data):
            print(f"  [{event.created_at}] {event.message}")

    if job.error:
        print(f"\nError: {job.error}")


def test_model():
    """Test the fine-tuned model with a sample prompt."""
    state = load_state()
    model = state.get("fine_tuned_model")

    if not model:
        print("ERROR: No fine-tuned model available yet.")
        print("Using base model for testing...")
        model = MODEL_BASE

    print(f"Testing model: {model}\n")

    test_prompt = """Generate the Cover Letter section for this proposal.

Client: Acme Corporation
Industry: Manufacturing
Region: US
Company Size: Enterprise
Deal: Enterprise License Agreement
Products/Services:
- Enterprise Platform License (Qty: 1, Unit: $50,000.00)
- Implementation Services (Qty: 1, Unit: $15,000.00)
- Annual Support & Maintenance (Qty: 1, Unit: $10,000.00)
Subtotal: $75,000.00
Discount: $11,250.00
Tax: $4,781.25
Total: $68,531.25
Compliance: SOC 2, GDPR
"""

    print("Prompt:", test_prompt[:100], "...\n")
    print("Generating...\n")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are QuoteForge, a professional B2B proposal writer. Generate accurate, professional proposal content based on the provided deal data. Never fabricate prices, quantities, or compliance requirements. Use the exact figures provided."},
            {"role": "user", "content": test_prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )

    output = response.choices[0].message.content
    print("─" * 60)
    print(output)
    print("─" * 60)
    print(f"\nTokens used: {response.usage.total_tokens}")
    print(f"Model: {model}")


def list_models():
    """List all fine-tuned models."""
    jobs = client.fine_tuning.jobs.list(limit=10)
    print("Recent fine-tuning jobs:")
    for job in jobs.data:
        print(f"  {job.id} | {job.status} | {job.fine_tuned_model or 'pending'} | {job.model}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python finetune_openai.py [upload|create|status|test|list]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    commands = {
        "upload": upload_files,
        "create": create_job,
        "status": check_status,
        "test": test_model,
        "list": list_models,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: upload, create, status, test, list")
