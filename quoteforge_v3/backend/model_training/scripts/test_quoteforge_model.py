"""
Test the fine-tuned QuoteForge MLX model on real-world prompts.
Compares base model vs fine-tuned model side-by-side.
"""
import argparse
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

TEST_CASES = [
    {
        "name": "Enterprise US Deal (SOC 2 + GDPR)",
        "prompt": """Generate a Cover Letter section for this proposal.

Client: Acme Corporation
Industry: Manufacturing
Region: US
Deal: Enterprise License Agreement
Amount: $75,000.00
Products: Enterprise Platform License, Implementation Services, Annual Support
Compliance: SOC 2, GDPR""",
    },
    {
        "name": "Pakistan PPRA Government Deal",
        "prompt": """Generate the Terms & Conditions section for this proposal.

Client: Punjab IT Board
Industry: Government
Region: PK
Deal: Document Management System
Amount: $55,000.00
Compliance: PPRA""",
    },
    {
        "name": "FTE Calling Program (matches client's real deal type)",
        "prompt": """Generate the Scope of Work section for this proposal.

Client: DataOps Inc
Deal Type: New Business
Deal: 2 FTE's 6-month Calling Program
Amount: $288,000.00
Products: FTE Calling Program (Qty: 2, Unit: $144,000)""",
    },
    {
        "name": "Pricing Summary",
        "prompt": """Generate the Pricing Summary section for this proposal.

Client: TechStart Inc
Deal: SaaS Platform Migration
Amount: $128,000.00
Line Items:
- Cloud Migration Services ($45,000)
- SaaS Platform License 3yr ($63,000)
- Training Program 20 users ($20,000)""",
    },
]


def test(adapter_path: str, use_base_only: bool = False):
    """Run test cases through the model."""
    from mlx_lm import load, generate

    base_model = "mlx-community/Llama-3.2-1B-Instruct-4bit"

    print("=" * 80)
    print(f"QuoteForge Model Test Suite")
    print("=" * 80)

    if use_base_only:
        print(f"\nLoading BASE model (no fine-tuning): {base_model}")
        model, tokenizer = load(base_model)
        label = "BASE MODEL"
    else:
        print(f"\nLoading FINE-TUNED model")
        print(f"  Base: {base_model}")
        print(f"  Adapter: {adapter_path}")
        model, tokenizer = load(base_model, adapter_path=adapter_path)
        label = "FINE-TUNED QUOTEFORGE"

    print(f"\nRunning {len(TEST_CASES)} test cases...\n")

    for i, test_case in enumerate(TEST_CASES, 1):
        print("=" * 80)
        print(f"TEST {i}/{len(TEST_CASES)}: {test_case['name']}")
        print("=" * 80)
        print(f"\n[PROMPT]")
        print(test_case["prompt"])

        # Format with chat template
        messages = [
            {"role": "system", "content": "You are QuoteForge, a professional B2B proposal writer."},
            {"role": "user", "content": test_case["prompt"]},
        ]
        formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        print(f"\n[OUTPUT — {label}]")
        start = time.time()
        output = generate(
            model,
            tokenizer,
            prompt=formatted,
            max_tokens=400,
            verbose=False,
        )
        duration = time.time() - start

        print(output)
        print(f"\n[Generation: {duration:.1f}s]")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-path",
                        default=str(BASE_DIR / "model_training" / "mlx_output" / "quoteforge-llama-1b"),
                        help="Path to fine-tuned adapter")
    parser.add_argument("--base-only", action="store_true",
                        help="Test base model without fine-tuning (for comparison)")
    args = parser.parse_args()
    test(args.adapter_path, args.base_only)
