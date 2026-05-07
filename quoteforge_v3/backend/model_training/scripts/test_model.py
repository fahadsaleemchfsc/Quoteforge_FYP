"""
Test a fine-tuned model with sample proposal prompts.
Used to verify training quality before deploying.
"""
import argparse
import logging
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_PROMPTS = [
    {
        "name": "US Enterprise Deal",
        "prompt": """Generate the Cover Letter section for this proposal.

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
Compliance: SOC 2, GDPR""",
    },
    {
        "name": "Pakistan PPRA Deal",
        "prompt": """Generate the Terms section for this proposal.

Client: Punjab IT Board
Industry: Government IT
Region: PK
Company Size: Government
Deal: Procurement Management System
Compliance: PPRA""",
    },
    {
        "name": "EU GDPR Deal",
        "prompt": """Generate the Scope section for this proposal.

Client: Continental Insurance
Industry: Insurance
Region: EU
Deal: Data Analytics Suite
Products/Services:
- Analytics Dashboard (Qty: 1, Unit: $12,500)
- Data Integration Service (Qty: 1, Unit: $7,500)""",
    },
]


def test(model_path: str, use_base: bool = False):
    """Load and test the model."""
    model_path = Path(model_path)

    # Figure out if this is a LoRA adapter or merged model
    is_lora = (model_path / "adapter_config.json").exists()

    logger.info(f"Loading model from: {model_path}")
    logger.info(f"Type: {'LoRA adapter' if is_lora else 'Full model'}")

    if is_lora:
        # Load base + adapter
        import json
        meta = json.loads((model_path / "quoteforge_meta.json").read_text())
        base_id = meta["base_model"]

        base = AutoModelForCausalLM.from_pretrained(
            base_id, torch_dtype=torch.float16,
            device_map="auto", trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base, str(model_path))
        tokenizer = AutoTokenizer.from_pretrained(str(model_path))
    else:
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path), torch_dtype=torch.float16,
            device_map="auto", trust_remote_code=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(str(model_path))

    model.eval()

    # Run test prompts
    for test_case in TEST_PROMPTS:
        print("\n" + "=" * 80)
        print(f"TEST: {test_case['name']}")
        print("=" * 80)
        print(f"\n[INPUT]\n{test_case['prompt'][:200]}...\n")

        messages = [{"role": "user", "content": test_case["prompt"]}]
        try:
            input_text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            input_text = f"### Instruction:\n{test_case['prompt']}\n\n### Response:\n"

        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)

        import time
        start = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.7,
                do_sample=True,
                top_p=0.9,
            )
        gen_time = time.time() - start

        response = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )

        print(f"[OUTPUT] (generated in {gen_time:.1f}s)\n{response}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    test(args.model_path)
