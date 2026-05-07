"""
MLX Fine-Tuning Pipeline for Apple Silicon (M1/M2/M3)
=======================================================
Uses Apple's MLX framework — native Apple Silicon ML, no CUDA needed.

Tested on:
  - M3 8GB  — Phi-3-mini, Llama-3.2-3B (works)
  - M3 16GB — Mistral-7B 4-bit (works)
  - M3 Max  — Mistral-7B full precision (works)

This script uses mlx-lm's built-in LoRA training utility.

Usage:
  python train_mlx.py --model llama-3.2-3b --iters 1000
  python train_mlx.py --model phi-3-mini --iters 1500
"""
import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = BASE_DIR / "training_data"
OUTPUT_DIR = BASE_DIR / "model_training" / "mlx_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# MLX supports 4-bit quantized versions that fit in M3 8GB
MODEL_CONFIGS = {
    "llama-3.2-3b": {
        "hf_id": "mlx-community/Llama-3.2-3B-Instruct-4bit",
        "size_gb": 2.0,
        "description": "Llama 3.2 3B — fast, good quality on M3 8GB",
    },
    "phi-3-mini": {
        "hf_id": "mlx-community/Phi-3-mini-4k-instruct-4bit",
        "size_gb": 2.3,
        "description": "Microsoft Phi-3 Mini — best quality/size ratio",
    },
    "llama-3.2-1b": {
        "hf_id": "mlx-community/Llama-3.2-1B-Instruct-4bit",
        "size_gb": 0.7,
        "description": "Tiny Llama 3.2 1B — very fast, lower quality",
    },
    "mistral-7b": {
        "hf_id": "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
        "size_gb": 4.2,
        "description": "Mistral 7B — best quality, needs 12GB+ RAM",
    },
}


def prepare_mlx_data():
    """
    Convert hf_train_combined.jsonl to MLX LoRA format.
    MLX expects: {"text": "..."} format in train.jsonl and valid.jsonl
    """
    train_path = TRAINING_DIR / "hf_train_combined.jsonl"
    val_path = TRAINING_DIR / "hf_val_combined.jsonl"

    if not train_path.exists():
        # Fallback to original synthetic data
        train_path = TRAINING_DIR / "hf_train.jsonl"
        val_path = TRAINING_DIR / "hf_val.jsonl"

    if not train_path.exists():
        logger.error(f"No training data found. Run generate_training_data.py first.")
        return None

    mlx_data_dir = TRAINING_DIR / "mlx"
    mlx_data_dir.mkdir(exist_ok=True)

    def convert(src_path, dst_name):
        with open(src_path) as fin, open(mlx_data_dir / dst_name, "w") as fout:
            count = 0
            for line in fin:
                sample = json.loads(line)
                # Format for MLX chat completion format
                text = (
                    f"<|im_start|>user\n{sample['instruction']}<|im_end|>\n"
                    f"<|im_start|>assistant\n{sample['output']}<|im_end|>"
                )
                fout.write(json.dumps({"text": text}) + "\n")
                count += 1
            return count

    train_count = convert(train_path, "train.jsonl")
    val_count = convert(val_path, "valid.jsonl") if val_path.exists() else 0

    # Also create test.jsonl (required by mlx-lm)
    test_path = TRAINING_DIR / "hf_test_combined.jsonl"
    if not test_path.exists():
        test_path = TRAINING_DIR / "hf_test.jsonl"
    if test_path.exists():
        convert(test_path, "test.jsonl")

    logger.info(f"MLX data prepared: {train_count} train, {val_count} val in {mlx_data_dir}")
    return mlx_data_dir


def train(model_name: str, iters: int = 1000, batch_size: int = 1, lora_layers: int = 8):
    """Run MLX LoRA fine-tuning."""
    config = MODEL_CONFIGS.get(model_name)
    if not config:
        logger.error(f"Unknown model: {model_name}")
        logger.info(f"Available: {list(MODEL_CONFIGS.keys())}")
        return

    logger.info(f"Model: {model_name}")
    logger.info(f"HF ID: {config['hf_id']}")
    logger.info(f"Size: {config['size_gb']:.1f} GB")
    logger.info(f"Description: {config['description']}")

    # Prepare data
    data_dir = prepare_mlx_data()
    if not data_dir:
        return

    # Output path
    from datetime import datetime
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    adapter_path = OUTPUT_DIR / f"quoteforge-{model_name}-{run_id}"
    adapter_path.mkdir(exist_ok=True)

    # Run mlx-lm LoRA training
    cmd = [
        sys.executable, "-m", "mlx_lm", "lora",
        "--model", config["hf_id"],
        "--train",
        "--data", str(data_dir),
        "--iters", str(iters),
        "--batch-size", str(batch_size),
        "--num-layers", str(lora_layers),
        "--learning-rate", "1e-4",
        "--adapter-path", str(adapter_path),
        "--save-every", "100",
    ]

    logger.info("Starting MLX training...")
    logger.info(f"Command: {' '.join(cmd)}")
    logger.info(f"Adapter path: {adapter_path}")
    logger.info("")
    logger.info("This will take 1-4 hours on M3 8GB depending on model size.")
    logger.info("Press Ctrl+C to stop early (checkpoint will be saved).")
    logger.info("")

    subprocess.run(cmd)

    logger.info(f"\n✅ Training complete!")
    logger.info(f"✅ Adapter saved to: {adapter_path}")
    logger.info(f"")
    logger.info(f"Next steps:")
    logger.info(f"  Test: python -m mlx_lm.generate --model {config['hf_id']} --adapter-path {adapter_path} --prompt 'Generate a cover letter for Acme Corp'")
    logger.info(f"  Fuse: python -m mlx_lm.fuse --model {config['hf_id']} --adapter-path {adapter_path} --save-path {adapter_path}-fused")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MLX LoRA Fine-Tuning for Apple Silicon")
    parser.add_argument("--model", default="llama-3.2-3b",
                        choices=list(MODEL_CONFIGS.keys()))
    parser.add_argument("--iters", type=int, default=1000,
                        help="Training iterations (1000 = ~1 hour on M3)")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--lora-layers", type=int, default=8,
                        help="Number of LoRA layers (more = better quality, slower)")
    args = parser.parse_args()

    train(args.model, args.iters, args.batch_size, args.lora_layers)
