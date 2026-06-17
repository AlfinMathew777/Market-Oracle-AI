"""Stage 6 — the gate: survivorship, calibration, baseline, sample-size honesty."""

import pytest
from trust.track_record import compute_track_record

pytestmark = pytest.mark.unit


def _rows():
    # 4 directional (3 correct, 1 wrong) + 2 that must be excluded by survivorship.
    return [
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": 3.0},   # CORRECT
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": 3.0},   # CORRECT
        {"predicted_direction": "bearish", "confidence": 0.65, "actual_price_change_pct": -3.0},  # CORRECT
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": -3.0},  # INCORRECT
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": 0.2},   # flat → excluded
        {"predicted_direction": "neutral", "confidence": 0.50, "actual_price_change_pct": 3.0},   # neutral → excluded
    ]


def test_survivorship_excludes_neutral_and_flat():
    tr = compute_track_record(_rows())
    assert tr["n_resolved_directional"] == 4
    assert tr["n_excluded_neutral"] == 2  # the flat move + the neutral prediction


def test_hit_rate_and_counts():
    tr = compute_track_record(_rows())
    assert tr["n_correct"] == 3
    assert tr["n_incorrect"] == 1
    assert tr["hit_rate"] == 0.75


def test_baseline_and_beats_baseline():
    tr = compute_track_record(_rows())
    # 2 actual-up, 2 actual-down among directional → best naive constant = 0.5
    assert tr["baseline_naive"] == 0.5
    assert tr["beats_baseline"] is True  # 0.75 > 0.5


def test_calibration_curve_buckets():
    tr = compute_track_record(_rows())
    by_bucket = {c["confidence_bucket"]: c for c in tr["calibration_curve"]}
    assert by_bucket["70-80%"]["n"] == 3
    assert by_bucket["70-80%"]["actual_hit_rate"] == pytest.approx(0.6667, abs=1e-3)
    assert by_bucket["60-70%"]["n"] == 1


def test_small_sample_flagged_and_wilson_present():
    tr = compute_track_record(_rows())
    assert tr["sample_warning"] is not None        # N=4 < 30, loudly flagged
    assert tr["wilson_ci_95"] is not None
    lo, hi = tr["wilson_ci_95"]
    assert lo < tr["hit_rate"] < hi                 # interval brackets the point estimate


def test_empty_set_is_honest_not_flattering():
    tr = compute_track_record([])
    assert tr["hit_rate"] is None
    assert tr["beats_baseline"] is None
    assert tr["sample_warning"] is not None


def test_all_flat_moves_zero_directional():
    flat = [{"predicted_direction": "bullish", "confidence": 0.7, "actual_price_change_pct": 0.1}
            for _ in range(5)]
    tr = compute_track_record(flat)
    assert tr["n_resolved_directional"] == 0
    assert tr["n_excluded_neutral"] == 5
