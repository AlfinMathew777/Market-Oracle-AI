"""Stage 6 — calibrated track record. THE GATE.

Honest measurement of whether the SWARM's real predictions (prediction_log) beat
chance. Not the backtest TA rule — a different system entirely.

Rigor, not flattery:
  - survivorship: only resolved CORRECT/INCORRECT count; NEUTRAL/UNVALIDATABLE excluded.
  - labels RE-DERIVED from persisted actual_price_change_pct through the SAME ±0.5%
    deadband the reputation loop uses — never the ambiguous prediction_correct column.
  - calibration, not just accuracy: hit rate per stated-confidence bucket (does 70%
    mean ~70%?).
  - honest baseline: the best naive constant predictor on the same set. "Do we beat
    the baseline" is the question — accuracy alone is meaningless.
  - horizons NOT blended: 24h-provisional and 7-day-authoritative reported separately.
  - sample-size honesty: N stated, Wilson 95% interval; a small N is flagged loudly.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from trust.scoring import score_predictions
from validation.constants import MIN_MOVE_PCT
from validation.outcome_checker import classify_outcome

# below this many resolved directional outcomes, a hit rate is NOT established.
_SMALL_SAMPLE = 30
_CONF_BUCKETS = ((0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def _actual_direction(change_pct: float) -> str:
    if change_pct > MIN_MOVE_PCT:
        return "up"
    if change_pct < -MIN_MOVE_PCT:
        return "down"
    return "flat"


def _wilson_95(correct: int, n: int) -> tuple[float, float] | None:
    """Wilson score 95% interval for a binomial hit rate — honest about small N."""
    if n == 0:
        return None
    z = 1.96
    p = correct / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def compute_track_record(rows: list[dict]) -> dict:
    """One horizon's track record from resolved prediction_log rows.

    Each row needs: predicted_direction, confidence (0-1), actual_price_change_pct.
    Pure — no I/O — so the gate logic is fully testable.
    """
    correct = incorrect = excluded = 0
    up = down = 0
    buckets: dict = {b: [0, 0] for b in _CONF_BUCKETS}  # bucket → [n_directional, n_correct]

    for r in rows:
        change = r.get("actual_price_change_pct")
        if change is None:
            excluded += 1
            continue
        outcome = classify_outcome(r.get("predicted_direction", "neutral"), float(change))
        if outcome not in ("CORRECT", "INCORRECT"):
            excluded += 1  # survivorship — neutral/unvalidatable do not count.
            continue

        is_correct = outcome == "CORRECT"
        correct += is_correct
        incorrect += not is_correct
        actual = _actual_direction(float(change))
        up += actual == "up"
        down += actual == "down"

        conf = float(r.get("confidence") or 0.0)
        for b in _CONF_BUCKETS:
            if b[0] <= conf < b[1]:
                buckets[b][0] += 1
                buckets[b][1] += is_correct
                break

    n = correct + incorrect
    hit_rate = round(correct / n, 4) if n else None

    # baseline: best naive constant direction on the same resolved set.
    frac_up = up / n if n else 0.0
    baseline = round(max(frac_up, 1 - frac_up), 4) if n else None

    calibration = [
        {
            "confidence_bucket": f"{int(b[0] * 100)}-{int(min(b[1], 1.0) * 100)}%",
            "predicted_midpoint": round((b[0] + min(b[1], 1.0)) / 2, 3),
            "n": cnt[0],
            "actual_hit_rate": round(cnt[1] / cnt[0], 4) if cnt[0] else None,
        }
        for b, cnt in buckets.items()
        if cnt[0] > 0
    ]

    return {
        "n_resolved_directional": n,
        "n_correct": correct,
        "n_incorrect": incorrect,
        "n_excluded_neutral": excluded,
        "hit_rate": hit_rate,
        "wilson_ci_95": _wilson_95(correct, n),
        "baseline_naive": baseline,
        "beats_baseline": (hit_rate > baseline) if (hit_rate is not None and baseline is not None) else None,
        "calibration_curve": calibration,
        "sample_warning": (
            f"N={n} resolved outcomes — below {_SMALL_SAMPLE}; hit rate is NOT established, "
            "treat as provisional." if n < _SMALL_SAMPLE else None
        ),
        # proper probabilistic scoring on the SAME rows — no survivorship:
        # neutrals are scored too (a probabilistic forecast never abstains).
        "scoring": score_predictions(rows),
    }


async def fetch_resolved_rows() -> tuple[list[dict], list[dict]]:
    """Resolved prediction_log rows split by horizon: (rows_24h, rows_7d).

    Shared by the track-record gate and the calibration report so both always
    score exactly the same resolved set. Raises on DB failure — callers decide
    how to degrade honestly.
    """
    from database import get_db, init_db

    await init_db()
    rows_24h: list[dict] = []
    rows_7d: list[dict] = []
    async with get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r, strict=False))
        async with db.execute(
            """SELECT predicted_direction, confidence, actual_price_change_pct, actual_driver
               FROM prediction_log
               WHERE resolved_at IS NOT NULL
                 AND actual_price_change_pct IS NOT NULL"""
        ) as cur:
            for row in await cur.fetchall():
                driver = (row.get("actual_driver") or "").lower()
                (rows_24h if "24h" in driver else rows_7d).append(row)
    return rows_24h, rows_7d


async def get_track_record() -> dict:
    """Read resolved swarm predictions and report 24h and 7-day records separately."""
    try:
        rows_24h, rows_7d = await fetch_resolved_rows()
    except Exception as e:  # noqa: BLE001 — empty/missing data → honest zero record.
        return {"error": str(e), "provisional_24h": compute_track_record([]),
                "authoritative_7d": compute_track_record([])}

    return {
        "measures": "swarm predictions (prediction_log), NOT the backtest TA rule",
        "deadband_pct": MIN_MOVE_PCT,
        "provisional_24h": compute_track_record(rows_24h),
        "authoritative_7d": compute_track_record(rows_7d),
    }


async def get_calibration() -> dict:
    """Probabilistic calibration report over the same resolved rows THE GATE uses.

    3-class Brier, log loss, BSS vs uniform/climatology, equal-count reliability
    bins, ECE, and the Murphy decomposition — overall plus per horizon.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        rows_24h, rows_7d = await fetch_resolved_rows()
    except Exception as e:  # noqa: BLE001 — empty/missing data → honest zero record.
        empty = score_predictions([])
        return {**empty, "n": 0, "generated_at": generated_at,
                "deadband_pct": MIN_MOVE_PCT, "error": str(e),
                "horizons": {"provisional_24h": score_predictions([]),
                             "authoritative_7d": score_predictions([])}}

    all_rows = [*rows_24h, *rows_7d]
    return {
        **score_predictions(all_rows),
        "n": len(all_rows),
        "generated_at": generated_at,
        "deadband_pct": MIN_MOVE_PCT,
        "horizons": {
            "provisional_24h": score_predictions(rows_24h),
            "authoritative_7d": score_predictions(rows_7d),
        },
    }
