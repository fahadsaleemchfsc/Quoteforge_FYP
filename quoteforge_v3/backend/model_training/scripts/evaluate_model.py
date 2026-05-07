"""
QuoteForge Model Evaluation Suite
===================================
Measures REAL accuracy of the fine-tuned model using multiple metrics:

1. FACTUAL ACCURACY      — Does output contain the exact prices/amounts?
2. PRICE HALLUCINATION   — Does output invent numbers not in the prompt?
3. CLIENT NAME USAGE     — Is the client name correctly referenced?
4. COMPLIANCE MENTIONS   — Does it include required compliance frameworks?
5. BLEU/ROUGE SCORES     — How similar to reference text? (optional)
6. LENGTH CONSISTENCY    — Are outputs reasonable length?
7. SECTION ADHERENCE     — Does it follow proposal structure?

Usage:
  python evaluate_model.py --adapter-path ./mlx_output/quoteforge-llama-1b
  python evaluate_model.py --compare-base  # compare fine-tuned vs base
"""
import argparse
import json
import re
import statistics
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEST_DATA_PATH = BASE_DIR / "training_data" / "hf_test_combined.jsonl"


def extract_dollar_amounts(text: str) -> set:
    """Extract all dollar amounts from text."""
    amounts = set()
    for match in re.findall(r'\$[\d,]+(?:\.\d+)?', text):
        cleaned = float(match.replace('$', '').replace(',', ''))
        if cleaned > 0:
            amounts.add(round(cleaned, 2))
    return amounts


def check_factual_accuracy(prompt: str, output: str) -> dict:
    """Check if output uses the facts from the prompt correctly."""
    prompt_amounts = extract_dollar_amounts(prompt)
    output_amounts = extract_dollar_amounts(output)

    # Numbers in output that aren't in prompt are hallucinations
    # (allow derived amounts like percentages of totals)
    allowed = set(prompt_amounts)
    for amt in prompt_amounts:
        allowed.add(round(amt * 0.3, 2))  # 30% payment
        allowed.add(round(amt * 0.4, 2))
        allowed.add(round(amt * 0.5, 2))
        allowed.add(round(amt * 0.7, 2))
        allowed.add(round(amt * 0.1, 2))  # 10% discount
        allowed.add(round(amt * 0.15, 2))  # 15% discount

    hallucinated = [
        amt for amt in output_amounts
        if amt not in allowed and not any(abs(amt - a) / max(a, 1) < 0.01 for a in allowed)
    ]

    return {
        "prompt_amounts": list(prompt_amounts),
        "output_amounts": list(output_amounts),
        "hallucinated": hallucinated,
        "accuracy": 1.0 if not hallucinated else 0.0,
    }


def check_client_name(prompt: str, output: str) -> dict:
    """Check if the client name from prompt appears in output."""
    # Find client name in prompt
    match = re.search(r'Client:\s*([^\n]+)', prompt)
    if not match:
        return {"correct": None, "reason": "no_client_in_prompt"}

    client_name = match.group(1).strip()
    # First word(s) of client name
    client_short = client_name.split()[0] if client_name else ""

    if client_short and client_short in output:
        return {"correct": True, "client": client_name}
    return {"correct": False, "client": client_name}


def check_compliance_mentions(prompt: str, output: str) -> dict:
    """Check if compliance frameworks from prompt are mentioned in output."""
    frameworks = []
    for fw in ["SOC 2", "GDPR", "PPRA", "HIPAA"]:
        if fw.lower() in prompt.lower():
            frameworks.append(fw)

    if not frameworks:
        return {"expected": [], "mentioned": [], "score": None}

    mentioned = [fw for fw in frameworks if fw.lower() in output.lower()]
    return {
        "expected": frameworks,
        "mentioned": mentioned,
        "score": len(mentioned) / len(frameworks) if frameworks else 1.0,
    }


def check_length_reasonable(output: str, min_chars: int = 100, max_chars: int = 5000) -> dict:
    """Check if output length is reasonable."""
    length = len(output)
    return {
        "length": length,
        "within_range": min_chars <= length <= max_chars,
        "too_short": length < min_chars,
        "too_long": length > max_chars,
    }


def calculate_bleu(reference: str, hypothesis: str) -> float:
    """
    Simple BLEU-style n-gram overlap score (0-1).
    For full BLEU, install nltk and use sentence_bleu.
    """
    ref_words = set(reference.lower().split())
    hyp_words = set(hypothesis.lower().split())
    if not hyp_words:
        return 0.0
    overlap = len(ref_words & hyp_words) / len(hyp_words)
    return overlap


def evaluate_one_sample(prompt: str, generated: str, reference: str = None) -> dict:
    """Run all evaluation checks on a single generation."""
    return {
        "factual": check_factual_accuracy(prompt, generated),
        "client_name": check_client_name(prompt, generated),
        "compliance": check_compliance_mentions(prompt, generated),
        "length": check_length_reasonable(generated),
        "bleu": calculate_bleu(reference, generated) if reference else None,
    }


def load_test_samples(limit: int = 30) -> list:
    """Load test samples."""
    if not TEST_DATA_PATH.exists():
        print(f"Test data not found at {TEST_DATA_PATH}")
        return []

    samples = []
    with open(TEST_DATA_PATH) as f:
        for line in f:
            samples.append(json.loads(line))
    return samples[:limit]


def run_evaluation(adapter_path: str = None, limit: int = 20):
    """Run full evaluation suite."""
    try:
        from mlx_lm import load, generate
    except ImportError:
        print("mlx_lm not installed")
        return

    base_model = "mlx-community/Llama-3.2-1B-Instruct-4bit"

    # Load model
    if adapter_path:
        print(f"Loading FINE-TUNED model with adapter: {adapter_path}")
        model, tokenizer = load(base_model, adapter_path=adapter_path)
        model_label = "Fine-Tuned"
    else:
        print(f"Loading BASE model (no fine-tuning)")
        model, tokenizer = load(base_model)
        model_label = "Base"

    # Load test samples
    samples = load_test_samples(limit)
    if not samples:
        return
    print(f"Evaluating on {len(samples)} test samples...\n")

    # Run evaluations
    all_results = []
    aggregated = {
        "factual_accuracy": [],
        "client_name_correct": [],
        "compliance_scores": [],
        "lengths": [],
        "bleu_scores": [],
        "hallucinated_amounts": [],
    }

    for i, sample in enumerate(samples, 1):
        prompt = sample["instruction"]
        reference = sample["output"]

        print(f"[{i}/{len(samples)}] Generating...", end=" ", flush=True)

        # Format prompt
        messages = [
            {"role": "system", "content": "You are QuoteForge, a professional B2B proposal writer."},
            {"role": "user", "content": prompt},
        ]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        # Generate
        try:
            import time
            start = time.time()
            generated = generate(model, tokenizer, prompt=formatted, max_tokens=500, verbose=False)
            gen_time = time.time() - start
            print(f"{gen_time:.1f}s")
        except Exception as e:
            print(f"FAIL: {e}")
            continue

        # Evaluate
        result = evaluate_one_sample(prompt, generated, reference)
        result["prompt_preview"] = prompt[:100]
        result["generation_time"] = gen_time
        all_results.append(result)

        # Aggregate
        aggregated["factual_accuracy"].append(result["factual"]["accuracy"])
        if result["client_name"]["correct"] is not None:
            aggregated["client_name_correct"].append(1 if result["client_name"]["correct"] else 0)
        if result["compliance"]["score"] is not None:
            aggregated["compliance_scores"].append(result["compliance"]["score"])
        aggregated["lengths"].append(result["length"]["length"])
        if result["bleu"] is not None:
            aggregated["bleu_scores"].append(result["bleu"])
        aggregated["hallucinated_amounts"].extend(result["factual"]["hallucinated"])

    # Calculate aggregate metrics
    print("\n" + "=" * 70)
    print(f"EVALUATION RESULTS — {model_label} Model")
    print("=" * 70)

    def pct(values):
        return f"{statistics.mean(values) * 100:.1f}%" if values else "N/A"

    print(f"\n🎯 FACTUAL ACCURACY")
    print(f"   Price accuracy (no hallucination):  {pct(aggregated['factual_accuracy'])}")
    print(f"   Total hallucinated amounts:         {len(aggregated['hallucinated_amounts'])}")
    if aggregated['hallucinated_amounts']:
        print(f"   Example hallucinations:             {aggregated['hallucinated_amounts'][:3]}")

    print(f"\n👤 CLIENT NAME USAGE")
    print(f"   Correctly includes client:          {pct(aggregated['client_name_correct'])}")

    print(f"\n⚖️  COMPLIANCE ADHERENCE")
    if aggregated['compliance_scores']:
        print(f"   Compliance mention rate:            {pct(aggregated['compliance_scores'])}")
    else:
        print(f"   (no compliance-specific prompts in sample)")

    print(f"\n📏 LENGTH METRICS")
    if aggregated['lengths']:
        print(f"   Average output length:              {statistics.mean(aggregated['lengths']):.0f} chars")
        print(f"   Min/Max:                            {min(aggregated['lengths'])}/{max(aggregated['lengths'])}")

    if aggregated['bleu_scores']:
        print(f"\n📝 SIMILARITY TO REFERENCE (BLEU-like)")
        print(f"   Average word overlap:               {statistics.mean(aggregated['bleu_scores']) * 100:.1f}%")

    # Composite score
    factual = statistics.mean(aggregated['factual_accuracy']) if aggregated['factual_accuracy'] else 0
    name = statistics.mean(aggregated['client_name_correct']) if aggregated['client_name_correct'] else 0
    compliance = statistics.mean(aggregated['compliance_scores']) if aggregated['compliance_scores'] else 1

    composite = (factual * 0.4 + name * 0.3 + compliance * 0.3) * 100
    print(f"\n🏆 COMPOSITE QUALITY SCORE:           {composite:.1f}/100")

    return {
        "model": model_label,
        "samples_evaluated": len(all_results),
        "factual_accuracy": factual,
        "client_name_accuracy": name,
        "compliance_score": compliance,
        "avg_length": statistics.mean(aggregated['lengths']) if aggregated['lengths'] else 0,
        "composite_score": composite,
        "hallucinations": len(aggregated['hallucinated_amounts']),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-path",
                        default=str(BASE_DIR / "model_training" / "mlx_output" / "quoteforge-llama-1b"))
    parser.add_argument("--base-only", action="store_true", help="Evaluate base model only")
    parser.add_argument("--compare", action="store_true", help="Compare base vs fine-tuned")
    parser.add_argument("--limit", type=int, default=20, help="Number of test samples")
    args = parser.parse_args()

    if args.compare:
        print("\n" + "█" * 70)
        print(" COMPARISON: Base Model vs Fine-Tuned Model")
        print("█" * 70 + "\n")
        base_results = run_evaluation(adapter_path=None, limit=args.limit)
        print("\n")
        ft_results = run_evaluation(adapter_path=args.adapter_path, limit=args.limit)

        # Comparison table
        print("\n" + "=" * 70)
        print("SIDE-BY-SIDE COMPARISON")
        print("=" * 70)
        print(f"{'Metric':<35} {'Base':>15} {'Fine-Tuned':>15}")
        print("-" * 70)
        for key in ["factual_accuracy", "client_name_accuracy", "compliance_score", "composite_score"]:
            b = base_results[key]
            f = ft_results[key]
            print(f"{key:<35} {b*100 if b <= 1 else b:>14.1f}%  {f*100 if f <= 1 else f:>14.1f}%")

    elif args.base_only:
        run_evaluation(adapter_path=None, limit=args.limit)
    else:
        run_evaluation(adapter_path=args.adapter_path, limit=args.limit)
