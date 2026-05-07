"""
QuoteForge QLoRA Fine-Tuning Script
=====================================
Production-ready fine-tuning for Mistral-7B / Llama-3 on consumer GPUs.

Tested on:
  - RTX 3060 (12GB)  — Mistral-7B QLoRA works
  - RTX 3060 (8GB)   — Use Phi-3-mini or Llama-3.2-3B instead
  - RTX 4090 (24GB)  — Full precision LoRA possible
  - A100 (80GB)      — Full fine-tuning possible

Usage:
  python train_qlora.py --model mistral-7b --epochs 3
  python train_qlora.py --model phi-3-mini --epochs 3  # for 8GB GPUs
"""
import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

import torch
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import Dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = BASE_DIR / "training_data"
CHECKPOINTS_DIR = BASE_DIR / "model_training" / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


MODEL_CONFIGS = {
    "mistral-7b": {
        "hf_id": "mistralai/Mistral-7B-Instruct-v0.3",
        "min_vram_gb": 12,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        "max_seq_length": 2048,
    },
    "llama-3.2-3b": {
        "hf_id": "meta-llama/Llama-3.2-3B-Instruct",
        "min_vram_gb": 8,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "max_seq_length": 2048,
    },
    "phi-3-mini": {
        "hf_id": "microsoft/Phi-3-mini-4k-instruct",
        "min_vram_gb": 6,
        "target_modules": ["qkv_proj", "o_proj", "gate_up_proj", "down_proj"],
        "max_seq_length": 2048,
    },
    "qwen-2.5-7b": {
        "hf_id": "Qwen/Qwen2.5-7B-Instruct",
        "min_vram_gb": 12,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "max_seq_length": 2048,
    },
}


def check_gpu():
    """Verify GPU is available and show VRAM."""
    if not torch.cuda.is_available():
        logger.error("CUDA GPU not available! This script requires an NVIDIA GPU.")
        logger.error("On Mac, use Google Colab or a cloud GPU instead.")
        return None

    gpu_name = torch.cuda.get_device_name(0)
    total_vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    logger.info(f"GPU: {gpu_name} ({total_vram_gb:.1f} GB VRAM)")
    return total_vram_gb


def load_dataset():
    """Load the training data."""
    train_path = TRAINING_DIR / "hf_train.jsonl"
    val_path = TRAINING_DIR / "hf_val.jsonl"

    if not train_path.exists():
        logger.error(f"Training data not found: {train_path}")
        logger.error("Run: python training_data/generate_training_data.py")
        return None, None

    def load_jsonl(path):
        data = []
        with open(path) as f:
            for line in f:
                data.append(json.loads(line))
        return data

    train_data = load_jsonl(train_path)
    val_data = load_jsonl(val_path) if val_path.exists() else []
    logger.info(f"Loaded {len(train_data)} train, {len(val_data)} validation samples")
    return train_data, val_data


def format_sample(sample, tokenizer):
    """Format a sample into chat template."""
    messages = [
        {"role": "user", "content": sample["instruction"]},
        {"role": "assistant", "content": sample["output"]},
    ]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    except Exception:
        return f"### Instruction:\n{sample['instruction']}\n\n### Response:\n{sample['output']}"


def train(model_name: str, epochs: int = 3, batch_size: int = 2):
    """Main training function."""
    # Check GPU
    vram = check_gpu()
    if vram is None:
        return

    config = MODEL_CONFIGS.get(model_name)
    if not config:
        logger.error(f"Unknown model: {model_name}")
        logger.error(f"Available: {list(MODEL_CONFIGS.keys())}")
        return

    if vram < config["min_vram_gb"]:
        logger.warning(f"Your GPU has {vram:.1f}GB but {model_name} needs {config['min_vram_gb']}GB")
        logger.warning("Training may OOM. Consider a smaller model.")

    logger.info(f"Training: {model_name} ({config['hf_id']})")
    logger.info(f"Epochs: {epochs}, Batch size: {batch_size}")

    # Output directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = CHECKPOINTS_DIR / f"quoteforge-{model_name}-{run_id}"
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Output: {output_dir}")

    # Load data
    train_data, val_data = load_dataset()
    if not train_data:
        return

    # Tokenizer
    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(config["hf_id"], trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Format datasets
    train_dataset = Dataset.from_list([
        {"text": format_sample(s, tokenizer)} for s in train_data
    ])
    val_dataset = Dataset.from_list([
        {"text": format_sample(s, tokenizer)} for s in val_data
    ]) if val_data else None

    # Quantization config (QLoRA 4-bit — fits in 8-12GB VRAM)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # Load model
    logger.info("Loading model (4-bit quantized)...")
    model = AutoModelForCausalLM.from_pretrained(
        config["hf_id"],
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=16,                    # LoRA rank
        lora_alpha=32,           # Scaling factor
        lora_dropout=0.05,
        target_modules=config["target_modules"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    trainable, total = model.get_nb_trainable_parameters()
    logger.info(f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        eval_strategy="steps" if val_dataset else "no",
        eval_steps=100 if val_dataset else None,
        fp16=True,
        optim="paged_adamw_8bit",  # Memory-efficient optimizer
        report_to="none",
        remove_unused_columns=False,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=config["max_seq_length"],
    )

    # Train
    logger.info("Starting training...")
    trainer.train()

    # Save
    trainer.save_model()
    tokenizer.save_pretrained(str(output_dir))

    # Save metadata
    meta = {
        "model_name": model_name,
        "base_model": config["hf_id"],
        "epochs": epochs,
        "batch_size": batch_size,
        "train_samples": len(train_data),
        "val_samples": len(val_data) if val_data else 0,
        "trained_at": datetime.now().isoformat(),
        "lora_rank": 16,
        "lora_alpha": 32,
    }
    (output_dir / "quoteforge_meta.json").write_text(json.dumps(meta, indent=2))

    logger.info(f"✅ Training complete!")
    logger.info(f"✅ Model saved to: {output_dir}")
    logger.info(f"")
    logger.info(f"Next steps:")
    logger.info(f"  1. Test: python scripts/test_model.py --model-path {output_dir}")
    logger.info(f"  2. Merge LoRA: python scripts/merge_lora.py --model-path {output_dir}")
    logger.info(f"  3. Convert to GGUF for Ollama: python scripts/convert_to_gguf.py --model-path {output_dir}")
    logger.info(f"  4. Serve with vLLM: python serving/vllm_server.py --model {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuoteForge QLoRA Fine-Tuning")
    parser.add_argument("--model", default="mistral-7b", choices=list(MODEL_CONFIGS.keys()),
                        help="Base model to fine-tune")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    args = parser.parse_args()

    train(args.model, args.epochs, args.batch_size)
