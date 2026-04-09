"""Confidence calibration for Market Oracle AI predictions.

Analyses historical prediction_log to measure the gap between stated
confidence and actual accuracy per confidence bucket.

Ideal calibration: a bucket stated at 65% confidence should be correct
~65% of the time. If the system is systematically over-confident, the
calibration gap is positive and the recommended adjustment is negative.

Usage:
    stats = await get_calibration_stats(ticker="BHP.AX", days=90)
    adjustment = stats["recommended_adjustment"]   # e.g. -0.08
    calibrated = apply_calibration_adjustment(0.70, calibration_gap=0.08)  # → 0.62
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Confidence buckets used for calibration analysis
CONFIDENCE_BUCKETS: list[tuple[float, float, str]] = [
    (0.00, 0.30, "0–30%"),
    (0.30, 0.45, "30–45%"),
    (0.45, 0.55, "45–55%"),
    (0.55, 0.65, "55–65%"),
    (0.65, 0.75, "65–75%"),
    (0.75, 0.85, "75–85%"),
]

# Minimum samples in a bucket before the calibration is considered reliable
_MIN_BUCKET_SAMPLES = 3


async def get_calibration_stats(
    ticker: Optional[str] = None,
    days: int = 90,
) -> dict:
    """Calculate actual accuracy per confidence bucket versus stated confidence.

    Args:
        ticker: Filter to a specific ASX ticker, or None for all tickers.
        days:   Look-back window in days.

    Returns a dict with:
        status                  — "success" | "insufficient_data"
        sample_size             — total resolved predictions analysed
        bucket_stats            — per-bucket accuracy vs stated confidence
        overall_calibration_gap — weighted average gap (stated − actual)
        recommended_adjustment  — suggested confidence adjustment (negate gap)
    """
    from database import get_full_prediction_log

    try:
        predictions = await get_full_prediction_log(ticker=ticker, days=days, limit=500)
    except Exception as e:
        logger.error("[CALIBRATION] Failed to fetch prediction log: %s", e)
        return {"status": "error", "detail": str(e)}

    # Only predictions with a resolved outcome
    resolved = [p for p in predictions if p.get("prediction_correct") is not None]

    if len(resolved) < 10:
        return {
            "status":      "insufficient_data",
            "sample_size": len(resolved),
            "message":     f"Need ≥10 resolved predictions, found {len(resolved)}",
        }

    bucket_stats: dict = {}
    for low, high, label in CONFIDENCE_BUCKETS:
        in_bucket = [
            p for p in resolved
            if low <= p.get("confidence", 0) < high
        ]
        if len(in_bucket) < _MIN_BUCKET_SAMPLES:
            continue

        correct = sum(1 for p in in_bucket if p.get("prediction_correct"))
        actual_accuracy   = correct / len(in_bucket)
        stated_confidence = (low + high) / 2
        calibration_gap   = stated_confidence - actual_accuracy

        bucket_stats[label] = {
            "sample_size":            len(in_bucket),
            "correct":                correct,
            "actual_accuracy":        round(actual_accuracy, 3),
            "stated_confidence_mid":  round(stated_confidence, 3),
            "calibration_gap":        round(calibration_gap, 3),
            "needs_adjustment":       abs(calibration_gap) > 0.10,
        }

    if not bucket_stats:
        return {
            "status":      "insufficient_data",
            "sample_size": len(resolved),
            "message":     "No confidence bucket has enough samples for calibration",
        }

    # Weighted average calibration gap across all buckets
    total_gap = sum(
        b["calibration_gap"] * b["sample_size"]
        for b in bucket_stats.values()
    )
    total_samples = sum(b["sample_size"] for b in bucket_stats.values())
    avg_gap = total_gap / total_samples if total_samples > 0 else 0.0

    return {
        "status":                   "success",
        "sample_size":              len(resolved),
        "bucket_stats":             bucket_stats,
        "overall_calibration_gap":  round(avg_gap, 3),
        # Negate gap: if we overstate by 0.08, reduce future confidence by 0.08
        "recommended_adjustment":   round(-avg_gap, 3),
        "ticker":                   ticker,
        "days":                     days,
    }


def apply_calibration_adjustment(
    raw_confidence: float,
    calibration_gap: float,
) -> float:
    """Shift raw confidence by the calibration correction.

    If the model overstates confidence (gap > 0), confidence is reduced.
    If the model understates confidence (gap < 0), confidence is increased.
    Result is clamped to [0.0, 0.85] — hard cap per CLAUDE.md.

    Args:
        raw_confidence:   Confidence before calibration (0–1 scale).
        calibration_gap:  Stated − actual accuracy (positive = over-confident).

    Returns the calibrated confidence (0–1 scale).
    """
    adjusted = raw_confidence - calibration_gap
    clamped  = max(0.0, min(0.85, adjusted))
    logger.debug(
        "[CALIBRATION] raw=%.2f gap=%+.3f → adjusted=%.2f",
        raw_confidence, calibration_gap, clamped,
    )
    return round(clamped, 4)


async def get_per_ticker_calibration(tickers: list[str], days: int = 90) -> dict:
    """Run calibration analysis for each ticker in the list.

    Returns a dict mapping ticker → calibration stats.
    """
    results: dict = {}
    for ticker in tickers:
        results[ticker] = await get_calibration_stats(ticker=ticker, days=days)
    return results
