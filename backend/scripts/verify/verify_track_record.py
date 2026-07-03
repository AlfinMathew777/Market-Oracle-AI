#!/usr/bin/env python3
"""recompute GET /api/accuracy/track-record from raw prediction_log rows.

labels re-derived from actual_price_change_pct through the +/-0.5% deadband
(strict inequality) — the stored prediction_correct column is never trusted.
horizon split: '24h' in actual_driver -> provisional, else 7-day.
duplicated thresholds: deadband 0.5, wilson z=1.96, small-sample floor 30,
fixed confidence buckets, best-constant-direction baseline.
"""

from __future__ import annotations

from _lib import (
    MIN_MOVE_PCT, actual_class, classify_outcome, finish, make_parser,
    resolved_prediction_rows, score_rows, split_horizons, wilson_95,
)

SMALL_SAMPLE = 30
CONF_BUCKETS = ((0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def track_record(rows: list[dict]) -> dict:
    correct = incorrect = excluded = up = 0
    buckets = {b: [0, 0] for b in CONF_BUCKETS}  # bucket -> [n, n_correct]
    for r in rows:
        change = float(r["actual_price_change_pct"])
        outcome = classify_outcome(r.get("predicted_direction"), change)
        if outcome not in ("CORRECT", "INCORRECT"):
            excluded += 1  # survivorship: neutral/unvalidatable abstain
            continue
        hit = outcome == "CORRECT"
        correct += hit
        incorrect += not hit
        up += actual_class(change) == "up"
        conf = float(r.get("confidence") or 0.0)
        for b in CONF_BUCKETS:
            if b[0] <= conf < b[1]:
                buckets[b][0] += 1
                buckets[b][1] += hit
                break

    n = correct + incorrect
    hit_rate = round(correct / n, 4) if n else None
    frac_up = up / n if n else 0.0
    baseline = round(max(frac_up, 1 - frac_up), 4) if n else None
    curve = [
        {"confidence_bucket": f"{int(b[0] * 100)}-{int(min(b[1], 1.0) * 100)}%",
         "predicted_midpoint": round((b[0] + min(b[1], 1.0)) / 2, 3),
         "n": cnt[0],
         "actual_hit_rate": round(cnt[1] / cnt[0], 4) if cnt[0] else None}
        for b, cnt in buckets.items() if cnt[0] > 0
    ]
    return {
        "n_resolved_directional": n,
        "n_correct": correct,
        "n_incorrect": incorrect,
        "n_excluded_neutral": excluded,
        "hit_rate": hit_rate,
        "wilson_ci_95": wilson_95(correct, n),
        "baseline_naive": baseline,
        "beats_baseline": (hit_rate > baseline) if n else None,
        "calibration_curve": curve,
        "sample_warning": (
            f"N={n} resolved outcomes — below {SMALL_SAMPLE}; hit rate is NOT established, "
            "treat as provisional." if n < SMALL_SAMPLE else None
        ),
        # probabilistic scoring on the same rows — no survivorship
        "scoring": score_rows(rows),
    }


def main() -> None:
    args = make_parser(__file__, "reconstruct the published track record").parse_args()
    rows_24h, rows_7d = split_horizons(resolved_prediction_rows(args.db))
    recon = {
        "deadband_pct": MIN_MOVE_PCT,
        "provisional_24h": track_record(rows_24h),
        "authoritative_7d": track_record(rows_7d),
    }
    finish(recon, args)


if __name__ == "__main__":
    main()
