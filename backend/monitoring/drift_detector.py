"""Distribution-shift (regime drift) detector.

CFA Institute AI Transition Framework imperative #2: model validation must be
"continuous, adversarial, and sensitive to distributional shift." The outcome
checker gives us continuous; the trust stack gives us adversarial; this module
supplies the third leg — detecting when the CURRENT prediction environment has
drifted away from the historical distribution the system's calibration and
archetype reputations were learned in.

Method: Population Stability Index (PSI) between a baseline window of
prediction_log rows (older history) and a recent window, over three signals:

  1. confidence distribution  (5 quantile-anchored bins)
  2. direction mix            (bullish / bearish / neutral shares)
  3. accuracy shift           (recent vs baseline hit rate, resolved rows only)

Standard PSI reading: < 0.10 stable, 0.10-0.25 moderate shift, > 0.25 severe.

Consumers:
  - simulation pipeline: `drift_confidence_multiplier` applies a bounded
    haircut when drift is detected (a reputation learned in one regime is
    less trustworthy in another).
  - alerts: REGIME_DRIFT fires on SEVERE.

Fail-soft: any DB/compute failure reports level NONE with a note — drift
detection must never block or degrade a simulation on its own failure.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# PSI thresholds (industry-standard credit-risk conventions).
PSI_MODERATE = 0.10
PSI_SEVERE = 0.25

# Confidence haircuts per drift level — bounded, never zeroing a signal.
DRIFT_MULTIPLIERS = {"NONE": 1.0, "MODERATE": 0.90, "SEVERE": 0.75}

# Window sizing (days).
RECENT_DAYS = 14
BASELINE_DAYS = 120  # baseline = rows older than RECENT_DAYS within this span

_MIN_ROWS_PER_WINDOW = 10  # below this, drift assessment is noise — report NONE
_N_BINS = 5
_EPS = 1e-4  # PSI smoothing so an empty bin never yields log(0)


def compute_psi(baseline: list[float], recent: list[float], bins: int = _N_BINS) -> float:
    """PSI between two samples using baseline-quantile bin edges.

    Bins are anchored on the baseline's quantiles so "the recent distribution
    moved" is measured against where history actually sat.

    Returns 0.0 when either sample is empty or the baseline is degenerate
    (all values identical — no distribution to shift against).
    """
    if not baseline or not recent:
        return 0.0
    sorted_base = sorted(baseline)
    if sorted_base[0] == sorted_base[-1]:
        return 0.0

    # Quantile edges over the baseline; interior edges only.
    edges = [
        sorted_base[min(len(sorted_base) - 1, int(len(sorted_base) * i / bins))]
        for i in range(1, bins)
    ]

    def _shares(values: list[float]) -> list[float]:
        counts = [0] * bins
        for v in values:
            idx = 0
            for edge in edges:
                if v > edge:
                    idx += 1
            counts[idx] = counts[idx] + 1
        total = len(values)
        return [(c / total) if total else 0.0 for c in counts]

    base_shares = _shares(baseline)
    recent_shares = _shares(recent)

    psi = 0.0
    for b, r in zip(base_shares, recent_shares, strict=True):
        b_s = max(b, _EPS)
        r_s = max(r, _EPS)
        psi += (r_s - b_s) * math.log(r_s / b_s)
    # Small-sample debias: under NO drift, E[PSI] ≈ (bins-1)·(1/n_b + 1/n_r)
    # (chi-square approximation). Without this, windows of ~50 rows read as
    # "moderate drift" from sampling noise alone. Subtract the noise floor so
    # PSI measures shift BEYOND what identical distributions would produce.
    noise_floor = (bins - 1) * (1.0 / len(baseline) + 1.0 / len(recent))
    return round(max(0.0, psi - noise_floor), 4)


def compute_categorical_psi(
    baseline: list[str], recent: list[str], categories: tuple[str, ...]
) -> float:
    """PSI over a fixed category set (e.g. direction mix)."""
    if not baseline or not recent:
        return 0.0

    def _shares(values: list[str]) -> list[float]:
        total = len(values)
        return [sum(1 for v in values if v == c) / total for c in categories]

    psi = 0.0
    for b, r in zip(_shares(baseline), _shares(recent), strict=True):
        b_s = max(b, _EPS)
        r_s = max(r, _EPS)
        psi += (r_s - b_s) * math.log(r_s / b_s)
    # Same small-sample debias as compute_psi (df = k-1 categories).
    noise_floor = (len(categories) - 1) * (1.0 / len(baseline) + 1.0 / len(recent))
    return round(max(0.0, psi - noise_floor), 4)


def classify_drift(psi: float) -> str:
    if psi > PSI_SEVERE:
        return "SEVERE"
    if psi > PSI_MODERATE:
        return "MODERATE"
    return "NONE"


def drift_confidence_multiplier(level: str) -> float:
    """Bounded confidence haircut for a drift level. Unknown levels → 1.0."""
    return DRIFT_MULTIPLIERS.get(level, 1.0)


def assess_drift(
    baseline_rows: list[dict], recent_rows: list[dict]
) -> dict[str, Any]:
    """Pure drift assessment over two windows of prediction_log rows.

    Returns a dict with per-signal PSI values, the overall level (worst
    signal wins), the confidence multiplier, and sample sizes.
    """
    if len(baseline_rows) < _MIN_ROWS_PER_WINDOW or len(recent_rows) < _MIN_ROWS_PER_WINDOW:
        return {
            "level": "NONE",
            "multiplier": 1.0,
            "note": (
                f"insufficient data (baseline={len(baseline_rows)}, "
                f"recent={len(recent_rows)}, need {_MIN_ROWS_PER_WINDOW} each)"
            ),
            "n_baseline": len(baseline_rows),
            "n_recent": len(recent_rows),
        }

    def _confidences(rows: list[dict]) -> list[float]:
        return [float(r.get("confidence") or 0.0) for r in rows]

    def _directions(rows: list[dict]) -> list[str]:
        return [str(r.get("predicted_direction") or "").lower() for r in rows]

    def _accuracy(rows: list[dict]) -> float | None:
        resolved = [r.get("prediction_correct") for r in rows if r.get("prediction_correct") is not None]
        if len(resolved) < 5:
            return None
        return sum(1 for c in resolved if c) / len(resolved)

    psi_confidence = compute_psi(_confidences(baseline_rows), _confidences(recent_rows))
    psi_direction = compute_categorical_psi(
        _directions(baseline_rows), _directions(recent_rows),
        categories=("bullish", "bearish", "neutral"),
    )

    base_acc = _accuracy(baseline_rows)
    recent_acc = _accuracy(recent_rows)
    accuracy_delta = (
        round(recent_acc - base_acc, 4)
        if base_acc is not None and recent_acc is not None
        else None
    )

    worst_psi = max(psi_confidence, psi_direction)
    level = classify_drift(worst_psi)
    # A large accuracy DROP escalates one level — the regime the reputations
    # were earned in is no longer paying.
    if accuracy_delta is not None and accuracy_delta < -0.15 and level == "NONE":
        level = "MODERATE"
    elif accuracy_delta is not None and accuracy_delta < -0.25 and level == "MODERATE":
        level = "SEVERE"

    return {
        "level": level,
        "multiplier": drift_confidence_multiplier(level),
        "psi_confidence": psi_confidence,
        "psi_direction": psi_direction,
        "accuracy_delta": accuracy_delta,
        "n_baseline": len(baseline_rows),
        "n_recent": len(recent_rows),
        "note": "",
    }


async def check_drift(ticker: str | None = None) -> dict[str, Any]:
    """DB-backed drift check: recent window vs baseline window of predictions.

    Fail-soft: any error reports level NONE with a note, never raises.
    """
    try:
        from datetime import UTC, datetime, timedelta

        from database import get_full_prediction_log

        rows = await get_full_prediction_log(
            ticker=ticker, days=BASELINE_DAYS, limit=2000
        )
        cutoff = (datetime.now(UTC) - timedelta(days=RECENT_DAYS)).isoformat()
        recent = [r for r in rows if str(r.get("predicted_at") or "") >= cutoff]
        baseline = [r for r in rows if str(r.get("predicted_at") or "") < cutoff]
        result = assess_drift(baseline, recent)
        result["ticker"] = ticker or "ALL"
        if result["level"] != "NONE":
            logger.warning(
                "[DRIFT] %s: level=%s psi_conf=%s psi_dir=%s acc_delta=%s",
                result["ticker"], result["level"],
                result.get("psi_confidence"), result.get("psi_direction"),
                result.get("accuracy_delta"),
            )
        return result
    except Exception as e:  # noqa: BLE001 — drift detection never breaks a caller
        logger.warning("drift check failed (fail-soft): %s", e)
        return {"level": "NONE", "multiplier": 1.0, "note": f"fail-soft: {e}"}
