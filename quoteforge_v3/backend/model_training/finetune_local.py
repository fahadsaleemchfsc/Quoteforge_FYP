"""
Local Fine-Tuning Pipeline with LoRA (Low-Rank Adaptation)
===========================================================
Fine-tunes Mistral-7B or Llama-3-8B for QuoteForge proposal generation
using Parameter-Efficient Fine-Tuning (PEFT) with QLoRA.

This demonstrates that QuoteForge can work with open-source models,
providing a self-hosted alternative to proprietary APIs.

Requirements:
  pip install torch transformers peft bitsandbytes datasets accelerate trl

Note: Requires a GPU with at least 8GB VRAM for QLoRA training.
      On CPU/Mac, this will run in evaluation mode only.
"""

import json
import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TRAINING_DIR = Path(__file__).parent.parent / "training_data"
OUTPUT_DIR = Path(__file__).parent / "checkpoints"
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class TrainingConfig:
    """Configuration for LoRA fine-tuning."""
    # Model
    base_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    # Alternatives: "meta-llama/Meta-Llama-3-8B-Instruct", "microsoft/phi-2"

    # LoRA parameters
    lora_r: int = 16          # LoRA rank (lower = fewer params, faster training)
    lora_alpha: int = 32      # LoRA alpha (scaling factor)
    lora_dropout: float = 0.05
    target_modules: list = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"])

    # Training parameters
    num_epochs: int = 3
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.1
    max_seq_length: int = 2048
    weight_decay: float = 0.01

    # Quantization (QLoRA)
    use_4bit: bool = True
    bnb_4bit_compute_dtype: str = "float16"
    bnb_4bit_quant_type: str = "nf4"

    # Output
    output_dir: str = str(OUTPUT_DIR / "quoteforge-lora")
    logging_steps: int = 10
    save_steps: int = 100
    eval_steps: int = 100


def load_training_data():
    """Load training data from JSONL files."""
    train_path = TRAINING_DIR / "hf_train.jsonl"
    val_path = TRAINING_DIR / "hf_val.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(
            f"Training data not found at {train_path}. "
            "Run generate_training_data.py first."
        )

    def load_jsonl(path):
        data = []
        with open(path) as f:
            for line in f:
                data.append(json.loads(line))
        return data

    train_data = load_jsonl(train_path)
    val_data = load_jsonl(val_path) if val_path.exists() else []

    logger.info(f"Loaded {len(train_data)} training samples, {len(val_data)} validation samples")
    return train_data, val_data


def format_for_training(samples, tokenizer):
    """Format samples into the chat template format."""
    formatted = []
    for sample in samples:
        # Use the instruction-response format
        instruction = sample["instruction"]
        output = sample["output"]

        # Format as chat
        messages = [
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": output},
        ]

        try:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        except Exception:
            # Fallback format
            text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"

        formatted.append({"text": text})

    return formatted


def train(config: TrainingConfig):
    """Run the LoRA fine-tuning pipeline."""
    try:
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            BitsAndBytesConfig,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
        from datasets import Dataset
    except ImportError as e:
        logger.error(
            f"Missing dependency: {e}\n"
            "Install with: pip install torch transformers peft bitsandbytes datasets accelerate trl"
        )
        return

    # Check device
    if torch.cuda.is_available():
        device = "cuda"
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
        logger.info("Using Apple Silicon MPS")
    else:
        device = "cpu"
        logger.warning("No GPU available. Training will be very slow on CPU.")

    # Load data
    train_data, val_data = load_training_data()

    # Load tokenizer
    logger.info(f"Loading tokenizer: {config.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Format data
    train_formatted = format_for_training(train_data, tokenizer)
    val_formatted = format_for_training(val_data, tokenizer) if val_data else None

    train_dataset = Dataset.from_list(train_formatted)
    val_dataset = Dataset.from_list(val_formatted) if val_formatted else None

    logger.info(f"Train dataset: {len(train_dataset)} samples")
    if val_dataset:
        logger.info(f"Val dataset: {len(val_dataset)} samples")

    # Quantization config (QLoRA)
    bnb_config = None
    if config.use_4bit and device == "cuda":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=config.bnb_4bit_quant_type,
            bnb_4bit_compute_dtype=getattr(torch, config.bnb_4bit_compute_dtype),
            bnb_4bit_use_double_quant=True,
        )
        logger.info("Using QLoRA 4-bit quantization")

    # Load model
    logger.info(f"Loading model: {config.base_model}")
    model_kwargs = {"trust_remote_code": True}
    if bnb_config:
        model_kwargs["quantization_config"] = bnb_config
    if device != "cpu":
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(config.base_model, **model_kwargs)

    if config.use_4bit and device == "cuda":
        model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=config.target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    trainable_params, total_params = model.get_nb_trainable_parameters()
    logger.info(
        f"Trainable parameters: {trainable_params:,} / {total_params:,} "
        f"({100 * trainable_params / total_params:.2f}%)"
    )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        warmup_ratio=config.warmup_ratio,
        weight_decay=config.weight_decay,
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        eval_strategy="steps" if val_dataset else "no",
        eval_steps=config.eval_steps if val_dataset else None,
        save_total_limit=3,
        fp16=(device == "cuda"),
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
        max_seq_length=config.max_seq_length,
    )

    # Train
    logger.info("Starting fine-tuning...")
    trainer.train()

    # Save
    logger.info(f"Saving model to {config.output_dir}")
    trainer.save_model()
    tokenizer.save_pretrained(config.output_dir)

    logger.info("Fine-tuning complete!")
    logger.info(f"Model saved to: {config.output_dir}")
    logger.info(f"\nTo use this model in QuoteForge, update the AI service to load from:")
    logger.info(f"  {config.output_dir}")


def test_inference(config: TrainingConfig, prompt: str = None):
    """Test inference with the fine-tuned model."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return

    model_path = config.output_dir
    if not Path(model_path).exists():
        logger.error(f"Model not found at {model_path}. Run training first.")
        return

    logger.info(f"Loading fine-tuned model from {model_path}")

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    base_model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, model_path)
    model.eval()

    if not prompt:
        prompt = (
            "Generate the Cover Letter section for this proposal.\n\n"
            "Client: TechStart Inc\n"
            "Industry: SaaS Technology\n"
            "Region: US\n"
            "Deal: Cloud Migration Project\n"
            "Total: $128,000.00\n"
            "Compliance: SOC 2, GDPR\n"
        )

    messages = [{"role": "user", "content": prompt}]

    try:
        input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        input_text = f"### Instruction:\n{prompt}\n\n### Response:\n"

    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
        )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print("\n" + "─" * 60)
    print(response)
    print("─" * 60)


if __name__ == "__main__":
    config = TrainingConfig()

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_inference(config)
    else:
        train(config)
