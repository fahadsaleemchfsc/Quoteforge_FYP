"""
Merge LoRA adapter into base model — produces a standalone model
that can be loaded without PEFT.

This is needed before converting to GGUF for Ollama.
"""
import argparse
import logging
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def merge(model_path: str, output_path: str = None):
    """Merge LoRA adapter weights into the base model."""
    model_path = Path(model_path)

    # Read metadata to find base model
    import json
    meta_file = model_path / "quoteforge_meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        base_model_id = meta["base_model"]
    else:
        # Fallback: read adapter config
        adapter_config = json.loads((model_path / "adapter_config.json").read_text())
        base_model_id = adapter_config["base_model_name_or_path"]

    logger.info(f"Base model: {base_model_id}")
    logger.info(f"LoRA adapter: {model_path}")

    # Output path
    if not output_path:
        output_path = str(model_path) + "-merged"
    output_path = Path(output_path)
    output_path.mkdir(exist_ok=True)

    # Load base model in fp16 for merging
    logger.info("Loading base model in fp16...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Load LoRA and merge
    logger.info("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base_model, str(model_path))

    logger.info("Merging LoRA into base model...")
    merged = model.merge_and_unload()

    # Save
    logger.info(f"Saving merged model to {output_path}...")
    merged.save_pretrained(str(output_path), safe_serialization=True)

    # Copy tokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(model_path))
    tokenizer.save_pretrained(str(output_path))

    logger.info(f"✅ Merged model saved to: {output_path}")
    logger.info(f"")
    logger.info(f"Next: Convert to GGUF for Ollama:")
    logger.info(f"  python scripts/convert_to_gguf.py --model-path {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True, help="Path to LoRA-trained model")
    parser.add_argument("--output-path", default=None, help="Output path for merged model")
    args = parser.parse_args()
    merge(args.model_path, args.output_path)
