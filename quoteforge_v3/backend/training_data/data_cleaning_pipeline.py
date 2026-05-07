"""
Production Data Cleaning Pipeline
===================================
Takes raw training data and produces a high-quality dataset ready for fine-tuning.

Cleaning stages:
  1. Quality Filter    — remove samples below threshold
  2. Deduplication     — remove near-duplicates (fuzzy matching)
  3. PII Scrubbing     — remove emails, phones, SSNs, credit cards
  4. Format Validation — ensure valid structure
  5. Length Filter     — remove too-short or too-long samples
  6. Content Balance   — ensure diversity across sections/regions
  7. Quality Score     — rank samples for training priority
"""
import json
import re
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from difflib import SequenceMatcher

OUTPUT_DIR = Path(__file__).parent


# ─── PII Patterns ─────────────────────────────────────────────────
PII_PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'(\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "credit_card": re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),
    "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    "url": re.compile(r'https?://\S+'),
}


def scrub_pii(text: str) -> tuple[str, dict]:
    """Remove PII from text. Returns (cleaned_text, stats_of_what_was_removed)."""
    stats = defaultdict(int)
    cleaned = text
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(cleaned)
        if matches:
            stats[pii_type] = len(matches)
            cleaned = pattern.sub(f'[REDACTED_{pii_type.upper()}]', cleaned)
    return cleaned, dict(stats)


# ─── Quality Checks ───────────────────────────────────────────────

def check_quality(sample: dict) -> tuple[bool, list[str]]:
    """Quality gate — returns (passes, list_of_issues)."""
    issues = []
    instruction = sample.get("instruction", "")
    output = sample.get("output", "")

    # 1. Length checks
    if len(instruction) < 30:
        issues.append("instruction_too_short")
    if len(instruction) > 5000:
        issues.append("instruction_too_long")
    if len(output) < 50:
        issues.append("output_too_short")
    if len(output) > 8000:
        issues.append("output_too_long")

    # 2. Must contain basic structure
    if not output.strip():
        issues.append("empty_output")

    # 3. No obvious garbage
    garbage_patterns = [
        r'^\s*$',                    # empty
        r'^(test|debug|xxx|todo)',   # placeholder text
        r'^[\W_]+$',                 # all punctuation
        r'^lorem ipsum',             # fake text
    ]
    for pattern in garbage_patterns:
        if re.search(pattern, output.lower()[:50]):
            issues.append(f"garbage_pattern:{pattern}")

    # 4. Output must be substantially different from instruction
    similarity = SequenceMatcher(None, instruction[:500], output[:500]).ratio()
    if similarity > 0.85:
        issues.append("output_too_similar_to_instruction")

    # 5. Repetition check — spammy content
    words = output.split()
    if len(words) > 20:
        word_counts = Counter(words)
        most_common = word_counts.most_common(1)[0]
        if most_common[1] > len(words) * 0.15:
            issues.append(f"repetitive_word:{most_common[0]}")

    # 6. Alphanumeric ratio (proposals should be mostly text)
    alpha = sum(1 for c in output if c.isalpha())
    total = len(output)
    if total > 0 and alpha / total < 0.4:
        issues.append("low_alpha_ratio")

    return len(issues) == 0, issues


# ─── Deduplication ────────────────────────────────────────────────

def fingerprint(text: str) -> str:
    """Normalize text for similarity comparison."""
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    normalized = re.sub(r'[^\w\s]', '', normalized)
    return normalized[:500]  # First 500 chars


def deduplicate(samples: list, similarity_threshold: float = 0.85) -> tuple[list, int]:
    """Remove near-duplicates. Returns (unique_samples, duplicates_removed)."""
    unique = []
    seen_fingerprints = []
    duplicates = 0

    for sample in samples:
        fp = fingerprint(sample.get("output", ""))

        # Quick exact match check via hash
        exact_hash = hashlib.md5(fp.encode()).hexdigest()
        if exact_hash in {s["hash"] for s in seen_fingerprints}:
            duplicates += 1
            continue

        # Fuzzy similarity check against recent samples (O(n*k) where k is limit)
        is_duplicate = False
        for prev in seen_fingerprints[-100:]:  # Check last 100 only (speed)
            similarity = SequenceMatcher(None, fp, prev["fp"]).quick_ratio()
            if similarity > similarity_threshold:
                ratio = SequenceMatcher(None, fp, prev["fp"]).ratio()
                if ratio > similarity_threshold:
                    is_duplicate = True
                    break

        if is_duplicate:
            duplicates += 1
        else:
            unique.append(sample)
            seen_fingerprints.append({"fp": fp, "hash": exact_hash})

    return unique, duplicates


# ─── Balance Check ────────────────────────────────────────────────

def analyze_balance(samples: list) -> dict:
    """Check distribution across categories."""
    section_counts = Counter()
    length_buckets = Counter()
    region_mentions = Counter()

    for sample in samples:
        instr = sample.get("instruction", "").lower()
        output = sample.get("output", "")

        # Detect section type
        if "cover letter" in instr:
            section_counts["cover_letter"] += 1
        elif "scope" in instr:
            section_counts["scope"] += 1
        elif "pricing" in instr:
            section_counts["pricing"] += 1
        elif "deliverables" in instr:
            section_counts["deliverables"] += 1
        elif "terms" in instr:
            section_counts["terms"] += 1
        elif "summary" in instr:
            section_counts["summary"] += 1
        else:
            section_counts["other"] += 1

        # Region
        for region in ["SOC 2", "GDPR", "PPRA", "EU", "Pakistan", "United States"]:
            if region.lower() in instr.lower():
                region_mentions[region] += 1

        # Length bucket
        output_len = len(output)
        if output_len < 300:
            length_buckets["short"] += 1
        elif output_len < 1000:
            length_buckets["medium"] += 1
        else:
            length_buckets["long"] += 1

    return {
        "sections": dict(section_counts),
        "regions": dict(region_mentions),
        "length_distribution": dict(length_buckets),
        "total": len(samples),
    }


# ─── Quality Scoring ──────────────────────────────────────────────

def quality_score(sample: dict) -> float:
    """
    Score a sample 0-100 based on quality signals.
    Higher score = better for training.
    """
    score = 50.0  # Baseline
    output = sample.get("output", "")
    instruction = sample.get("instruction", "")

    # Bonus: has structured sections (bullets, headers)
    if re.search(r'^\s*\d+\.\s', output, re.MULTILINE):  # Numbered list
        score += 5
    if re.search(r'^\s*[-*]\s', output, re.MULTILINE):  # Bullets
        score += 5
    if re.search(r'^[A-Z\s]+:$|^[A-Z\s]+\n[-=]+', output, re.MULTILINE):  # Headers
        score += 5

    # Bonus: appropriate length
    output_len = len(output)
    if 500 <= output_len <= 2000:
        score += 10
    elif 200 <= output_len <= 3000:
        score += 5

    # Bonus: mentions specific business terms
    business_terms = ['deliverables', 'milestone', 'payment', 'scope', 'compliance',
                      'warranty', 'liability', 'intellectual property', 'confidential']
    hits = sum(1 for t in business_terms if t.lower() in output.lower())
    score += min(hits * 2, 15)

    # Bonus: has dollar amounts (shows it used the pricing data)
    if re.search(r'\$[\d,]+', output):
        score += 5

    # Penalty: too much filler
    if output.lower().count('we are pleased') + output.lower().count('thank you') > 3:
        score -= 10

    # Penalty: vague content
    vague_words = ['some', 'things', 'stuff', 'etc', 'and so on', 'and more']
    for word in vague_words:
        if word in output.lower():
            score -= 2

    return max(0, min(100, score))


# ─── Main Pipeline ────────────────────────────────────────────────

def clean_dataset(input_path: str, output_path: str, verbose: bool = True):
    """Run the full cleaning pipeline."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Load raw samples
    print(f"Loading: {input_path}")
    samples = []
    with open(input_path) as f:
        for line in f:
            samples.append(json.loads(line))
    print(f"Raw samples: {len(samples):,}")

    stats = {
        "raw": len(samples),
        "quality_failed": 0,
        "duplicates_removed": 0,
        "pii_scrubbed": 0,
        "final": 0,
    }

    # Stage 1: Quality filter
    print("\n[Stage 1] Quality filter...")
    filtered = []
    quality_issues = defaultdict(int)
    for sample in samples:
        passes, issues = check_quality(sample)
        if passes:
            filtered.append(sample)
        else:
            stats["quality_failed"] += 1
            for issue in issues:
                quality_issues[issue] += 1
    print(f"  Passed: {len(filtered):,} | Failed: {stats['quality_failed']:,}")
    if verbose and quality_issues:
        for issue, count in sorted(quality_issues.items(), key=lambda x: -x[1])[:5]:
            print(f"    {issue}: {count}")

    # Stage 2: PII Scrubbing
    print("\n[Stage 2] PII scrubbing...")
    pii_totals = defaultdict(int)
    for sample in filtered:
        sample["output"], output_pii = scrub_pii(sample["output"])
        sample["instruction"], instr_pii = scrub_pii(sample["instruction"])
        for k, v in output_pii.items():
            pii_totals[k] += v
        for k, v in instr_pii.items():
            pii_totals[k] += v
        if output_pii or instr_pii:
            stats["pii_scrubbed"] += 1
    print(f"  Samples with PII scrubbed: {stats['pii_scrubbed']:,}")
    if verbose and pii_totals:
        for pii_type, count in pii_totals.items():
            print(f"    {pii_type}: {count}")

    # Stage 3: Deduplication
    print("\n[Stage 3] Deduplication (fuzzy matching)...")
    unique, dup_count = deduplicate(filtered, similarity_threshold=0.85)
    stats["duplicates_removed"] = dup_count
    print(f"  Unique: {len(unique):,} | Duplicates removed: {dup_count:,}")

    # Stage 4: Quality scoring + sorting
    print("\n[Stage 4] Quality scoring...")
    for sample in unique:
        sample["_quality_score"] = quality_score(sample)

    scores = [s["_quality_score"] for s in unique]
    print(f"  Score distribution: min={min(scores):.1f} avg={sum(scores)/len(scores):.1f} max={max(scores):.1f}")

    # Sort by quality (highest first for training priority)
    unique.sort(key=lambda x: -x["_quality_score"])

    # Stage 5: Balance analysis
    print("\n[Stage 5] Dataset balance analysis...")
    balance = analyze_balance(unique)
    print(f"  Sections: {balance['sections']}")
    print(f"  Length: {balance['length_distribution']}")
    print(f"  Region mentions: {balance['regions']}")

    # Save
    stats["final"] = len(unique)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for sample in unique:
            # Remove internal score from saved data
            sample_to_save = {k: v for k, v in sample.items() if not k.startswith("_")}
            f.write(json.dumps(sample_to_save, default=str) + "\n")

    # Summary
    print("\n" + "=" * 60)
    print("CLEANING SUMMARY")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k:30s} {v:>8,}")
    retention = stats["final"] / stats["raw"] * 100 if stats["raw"] > 0 else 0
    print(f"  {'retention_rate':30s} {retention:>7.1f}%")
    print(f"\n✅ Cleaned dataset saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="training_data/hf_train_combined.jsonl")
    parser.add_argument("--output", default="training_data/hf_train_cleaned.jsonl")
    args = parser.parse_args()

    clean_dataset(args.input, args.output)
