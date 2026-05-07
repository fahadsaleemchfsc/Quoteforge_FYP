"""Session 6.5 — tests for the pure-logic bits of /api/insights/accuracy.

Endpoint itself needs a DB + active model, so we test the math in isolation:
  - confusion matrix tally over synthetic holdout rows
  - accuracy-by-confidence-bucket aggregation
"""
from __future__ import annotations


def _confusion_matrix(holdout: list[dict]) -> dict[str, int]:
    """Mirrors the logic in the /accuracy endpoint so we can test it cleanly."""
    tp = fp = tn = fn = 0
    for h in holdout:
        predicted_win = h.get("probability", 0) >= 0.5
        actual_win = bool(h.get("actual"))
        if predicted_win and actual_win: tp += 1
        elif predicted_win and not actual_win: fp += 1
        elif not predicted_win and not actual_win: tn += 1
        else: fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def test_confusion_matrix_on_perfect_holdout():
    holdout = (
        [{"probability": 0.9, "actual": 1}] * 20
        + [{"probability": 0.1, "actual": 0}] * 30
    )
    cm = _confusion_matrix(holdout)
    assert cm == {"tp": 20, "fp": 0, "tn": 30, "fn": 0}


def test_confusion_matrix_on_worst_case_inversion():
    holdout = (
        [{"probability": 0.9, "actual": 0}] * 10
        + [{"probability": 0.1, "actual": 1}] * 10
    )
    cm = _confusion_matrix(holdout)
    assert cm == {"tp": 0, "fp": 10, "tn": 0, "fn": 10}


def test_confusion_matrix_mixed_case():
    holdout = [
        {"probability": 0.9, "actual": 1},    # tp
        {"probability": 0.9, "actual": 0},    # fp
        {"probability": 0.1, "actual": 0},    # tn
        {"probability": 0.1, "actual": 1},    # fn
        {"probability": 0.5, "actual": 1},    # tp (>=0.5 threshold)
        {"probability": 0.49, "actual": 0},   # tn
    ]
    cm = _confusion_matrix(holdout)
    assert cm == {"tp": 2, "fp": 1, "tn": 2, "fn": 1}


def _bucketize(holdout: list[dict]) -> list[dict]:
    """Mirrors the accuracy-by-confidence-bucket computation."""
    buckets = [(0.8, 1.01, "80-100%"), (0.6, 0.8, "60-80%"),
               (0.4, 0.6, "40-60%"), (0.2, 0.4, "20-40%"),
               (0.0, 0.2, "0-20%")]
    out = []
    for lo, hi, label in buckets:
        subset = [h for h in holdout if lo <= h.get("probability", 0) < hi]
        won = sum(1 for h in subset if h.get("actual"))
        total = len(subset)
        out.append({
            "bucket": label, "count": total,
            "actual_win_rate": round(won / total, 3) if total else 0.0,
        })
    return out


def test_buckets_calibrate_well_on_deliberately_calibrated_data():
    # If predicted probability == actual win rate within each bucket, the
    # model is perfectly calibrated. Build such a holdout.
    holdout = []
    # 80-100% bucket: 90% win rate
    holdout += [{"probability": 0.9, "actual": 1}] * 9
    holdout += [{"probability": 0.9, "actual": 0}] * 1
    # 20-40% bucket: 30% win rate
    holdout += [{"probability": 0.3, "actual": 1}] * 3
    holdout += [{"probability": 0.3, "actual": 0}] * 7

    rows = _bucketize(holdout)
    by = {r["bucket"]: r for r in rows}
    assert by["80-100%"]["count"] == 10
    assert by["80-100%"]["actual_win_rate"] == 0.9
    assert by["20-40%"]["count"] == 10
    assert by["20-40%"]["actual_win_rate"] == 0.3


def test_empty_holdout_yields_zero_rate_no_divide_error():
    rows = _bucketize([])
    for r in rows:
        assert r["count"] == 0
        assert r["actual_win_rate"] == 0.0
