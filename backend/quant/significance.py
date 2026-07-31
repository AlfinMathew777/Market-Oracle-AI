"""Statistical significance of the prediction track record.

Answers the diligence question every accuracy number invites: *is this hit
rate distinguishable from luck?*

Method — label-shuffle permutation test (adapted from HKUDS/Vibe-Trading's
Monte Carlo permutation validation, MIT):

  Null hypothesis: predicted directions carry no information about actual
  directions. Shuffling the predicted labels against the fixed actual labels
  preserves BOTH marginal distributions (our bull/bear prediction mix AND the
  market's up/down base rate), so the null distribution reflects what accuracy
  a signal-free predictor with our exact biases would score. The p-value is
  the probability of seeing our observed accuracy (or better) under that null.

This is stronger than comparing against a 50% coin flip: in a trending market
an uninformed predictor that leans bullish scores above 50% for free — the
permutation null prices that in.
"""

from __future__ import annotations

import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PERMUTATIONS = 10_000
DEFAULT_SEED = 42
SIGNIFICANCE_LEVEL = 0.05
_MIN_SAMPLE = 10  # below this, a p-value is numerology — refuse to compute

_DIRECTIONAL = {"bullish", "bearish"}


def permutation_test_accuracy(
    pairs: list[tuple[str, str]],
    n_permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Label-shuffle permutation test on (predicted, actual) direction pairs.

    Args:
        pairs: (predicted_direction, actual_direction) tuples. Pairs where
               either side is not bullish/bearish are excluded — NEUTRAL
               abstains from the track record by system policy.
        n_permutations: shuffle count; p-value resolution is ~1/n.
        seed: RNG seed for reproducibility (same inputs → same p-value).

    Returns:
        Dict with observed accuracy, p_value, null distribution summary, and
        an `is_significant` verdict at the 0.05 level. On insufficient data,
        returns {"error": ..., "n_predictions": ...} instead.
    """
    directional = [
        (p.lower(), a.lower())
        for p, a in pairs
        if p and a and p.lower() in _DIRECTIONAL and a.lower() in _DIRECTIONAL
    ]
    n = len(directional)
    if n < _MIN_SAMPLE:
        return {
            "error": f"need at least {_MIN_SAMPLE} resolved directional predictions, have {n}",
            "n_predictions": n,
        }

    predicted = [p for p, _ in directional]
    actual = [a for _, a in directional]
    observed_hits = sum(1 for p, a in directional if p == a)
    observed_accuracy = observed_hits / n

    rng = random.Random(seed)  # noqa: S311 — statistical simulation, not crypto
    shuffled = list(predicted)
    at_or_above = 0
    null_accuracies: list[float] = []
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        hits = sum(1 for p, a in zip(shuffled, actual, strict=True) if p == a)
        acc = hits / n
        null_accuracies.append(acc)
        if acc >= observed_accuracy:
            at_or_above += 1

    # Add-one (phipson-smyth) correction: a permutation p-value of exactly 0
    # overstates certainty; the observed labelling is itself one permutation.
    p_value = (at_or_above + 1) / (n_permutations + 1)

    null_sorted = sorted(null_accuracies)
    null_mean = sum(null_accuracies) / n_permutations
    variance = sum((a - null_mean) ** 2 for a in null_accuracies) / n_permutations
    null_p95 = null_sorted[min(n_permutations - 1, int(0.95 * n_permutations))]

    is_significant = p_value < SIGNIFICANCE_LEVEL
    return {
        "observed_accuracy_pct": round(observed_accuracy * 100, 2),
        "n_predictions": n,
        "n_correct": observed_hits,
        "p_value": round(p_value, 5),
        "is_significant": is_significant,
        "significance_level": SIGNIFICANCE_LEVEL,
        "null_mean_accuracy_pct": round(null_mean * 100, 2),
        "null_std_pct": round(variance ** 0.5 * 100, 2),
        "null_p95_accuracy_pct": round(null_p95 * 100, 2),
        "n_permutations": n_permutations,
        "seed": seed,
        "interpretation": (
            f"Observed accuracy {observed_accuracy * 100:.1f}% vs uninformed "
            f"baseline {null_mean * 100:.1f}% — "
            + (
                f"significant at the {SIGNIFICANCE_LEVEL:.0%} level (p={p_value:.4f}): "
                "unlikely to be luck."
                if is_significant
                else f"NOT significant (p={p_value:.4f}): consistent with chance "
                "at this sample size."
            )
        ),
    }


async def run_accuracy_significance(
    ticker: str | None = None,
    days: int = 365,
    n_permutations: int = DEFAULT_PERMUTATIONS,
) -> dict[str, Any]:
    """Permutation-test the live prediction_log track record.

    Pulls resolved directional predictions and runs the label-shuffle test.
    Fail-soft: any DB error returns an error payload, never raises.
    """
    try:
        from database import get_resolved_direction_pairs

        rows = await get_resolved_direction_pairs(ticker=ticker, days=days)
        pairs = [
            (row.get("predicted_direction") or "", row.get("actual_direction") or "")
            for row in rows
        ]
        result = permutation_test_accuracy(pairs, n_permutations=n_permutations)
        result["window_days"] = days
        result["ticker"] = ticker or "ALL"
        return result
    except Exception as e:  # noqa: BLE001 — significance is read-only reporting
        logger.error("accuracy significance failed: %s", e)
        return {"error": str(e), "ticker": ticker or "ALL", "window_days": days}
