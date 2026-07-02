"""Probabilistic scoring — Brier, log loss, BSS, reliability bins, ECE, Murphy."""

import copy
import math

import pytest

from trust.scoring import (
    actual_class,
    brier_score_3class,
    brier_skill_score,
    climatology_probs,
    expected_calibration_error,
    forecast_vector,
    log_loss,
    murphy_decomposition,
    reliability_bins,
    score_predictions,
)
from validation.constants import MIN_MOVE_PCT
from validation.outcome_checker import classify_outcome

pytestmark = pytest.mark.unit


# ── forecast_vector ────────────────────────────────────────────────────────────

def test_forecast_vector_bullish_puts_confidence_on_up():
    probs = forecast_vector("bullish", 0.7)
    assert probs["up"] == pytest.approx(0.7)
    assert probs["down"] == pytest.approx(0.15)
    assert probs["neutral"] == pytest.approx(0.15)


def test_forecast_vector_legacy_up_token_normalizes_to_up():
    assert forecast_vector("UP", 0.6)["up"] == pytest.approx(0.6)


def test_forecast_vector_sell_token_normalizes_to_down():
    assert forecast_vector("sell", 0.8)["down"] == pytest.approx(0.8)


def test_forecast_vector_hold_token_normalizes_to_neutral():
    assert forecast_vector("hold", 0.5)["neutral"] == pytest.approx(0.5)


def test_forecast_vector_unknown_token_returns_none():
    assert forecast_vector("banana", 0.7) is None
    assert forecast_vector("", 0.7) is None
    assert forecast_vector(None, 0.7) is None


def test_forecast_vector_probs_sum_to_one():
    probs = forecast_vector("bearish", 0.85)
    assert sum(probs.values()) == pytest.approx(1.0)


def test_forecast_vector_out_of_range_confidence_clamped():
    assert forecast_vector("bullish", 1.4)["up"] == pytest.approx(1.0)
    assert forecast_vector("bullish", -0.2)["up"] == pytest.approx(0.0)


# ── actual_class ───────────────────────────────────────────────────────────────

def test_actual_class_above_deadband_returns_up():
    assert actual_class(MIN_MOVE_PCT + 0.01) == "up"


def test_actual_class_below_negative_deadband_returns_down():
    assert actual_class(-MIN_MOVE_PCT - 0.01) == "down"


def test_actual_class_inside_deadband_returns_neutral():
    assert actual_class(0.0) == "neutral"
    assert actual_class(0.2) == "neutral"


def test_actual_class_exactly_plus_deadband_returns_neutral():
    # strict inequality — a move must CLEAR the band, matching classify_outcome.
    assert actual_class(MIN_MOVE_PCT) == "neutral"
    assert actual_class(-MIN_MOVE_PCT) == "neutral"


def test_actual_class_boundary_matches_classify_outcome_convention():
    # exactly at the band, classify_outcome abstains (NEUTRAL) — so must we.
    assert classify_outcome("bullish", MIN_MOVE_PCT) == "NEUTRAL"
    assert actual_class(MIN_MOVE_PCT) == "neutral"
    assert classify_outcome("bullish", MIN_MOVE_PCT + 0.01) == "CORRECT"
    assert actual_class(MIN_MOVE_PCT + 0.01) == "up"


# ── brier_score_3class ─────────────────────────────────────────────────────────

def test_brier_score_uniform_forecast_scores_two_thirds():
    uniform = {"up": 1 / 3, "down": 1 / 3, "neutral": 1 / 3}
    for outcome in ("up", "down", "neutral"):
        assert brier_score_3class(uniform, outcome) == pytest.approx(2 / 3)


def test_brier_score_perfect_confident_forecast_scores_zero():
    assert brier_score_3class(forecast_vector("bullish", 1.0), "up") == pytest.approx(0.0)


def test_brier_score_confidently_wrong_forecast_scores_two():
    assert brier_score_3class(forecast_vector("bullish", 1.0), "down") == pytest.approx(2.0)


# ── log_loss ───────────────────────────────────────────────────────────────────

def test_log_loss_known_probability_matches_negative_ln():
    probs = forecast_vector("bullish", 0.7)
    assert log_loss(probs, "up") == pytest.approx(-math.log(0.7))


def test_log_loss_zero_probability_clipped_at_1e6():
    probs = forecast_vector("bullish", 1.0)  # down gets exactly 0
    assert log_loss(probs, "down") == pytest.approx(-math.log(1e-6))


# ── climatology_probs ──────────────────────────────────────────────────────────

def test_climatology_probs_returns_class_frequencies():
    clim = climatology_probs(["up", "up", "down", "neutral"])
    assert clim == {"up": 0.5, "down": 0.25, "neutral": 0.25}


def test_climatology_probs_empty_input_returns_uniform():
    clim = climatology_probs([])
    for k in ("up", "down", "neutral"):
        assert clim[k] == pytest.approx(1 / 3)


# ── brier_skill_score ──────────────────────────────────────────────────────────

def test_brier_skill_score_equal_to_reference_is_zero():
    assert brier_skill_score(0.5, 0.5) == pytest.approx(0.0)


def test_brier_skill_score_zero_reference_returns_none():
    assert brier_skill_score(0.3, 0.0) is None


def test_brier_skill_score_half_of_reference_is_half():
    assert brier_skill_score(0.3, 0.6) == pytest.approx(0.5)


# ── reliability_bins ───────────────────────────────────────────────────────────

def test_reliability_bins_seven_records_five_bins_equal_count():
    records = [(0.1, True), (0.2, False), (0.3, True), (0.4, True),
               (0.5, False), (0.6, True), (0.7, True)]
    bins = reliability_bins(records, n_bins=5)
    assert len(bins) == 5
    assert [b["n"] for b in bins] == [1, 1, 2, 1, 2]  # equal-count, never empty
    assert sum(b["n"] for b in bins) == 7
    # third bin holds (0.3, True) and (0.4, True)
    assert bins[2]["mean_confidence"] == pytest.approx(0.35)
    assert bins[2]["hit_rate"] == pytest.approx(1.0)
    assert bins[2]["gap"] == pytest.approx(0.65)


def test_reliability_bins_stats_computed_by_hand():
    records = [(0.6, True), (0.6, False), (0.8, True), (0.8, True)]
    bins = reliability_bins(records, n_bins=2)
    assert bins[0] == {"n": 2, "mean_confidence": 0.6, "hit_rate": 0.5, "gap": -0.1}
    assert bins[1] == {"n": 2, "mean_confidence": 0.8, "hit_rate": 1.0, "gap": 0.2}


def test_reliability_bins_fewer_records_than_bins_no_empty_bins():
    bins = reliability_bins([(0.5, True), (0.6, False), (0.7, True)], n_bins=5)
    assert len(bins) == 3
    assert all(b["n"] == 1 for b in bins)


def test_reliability_bins_empty_input_returns_empty_list():
    assert reliability_bins([], n_bins=5) == []


# ── expected_calibration_error ─────────────────────────────────────────────────

def test_expected_calibration_error_hand_computed():
    bins = reliability_bins([(0.6, True), (0.6, False), (0.8, True), (0.8, True)], n_bins=2)
    # (2/4)*|-0.1| + (2/4)*|0.2| = 0.05 + 0.10 = 0.15
    assert expected_calibration_error(bins) == pytest.approx(0.15)


def test_expected_calibration_error_empty_bins_returns_none():
    assert expected_calibration_error([]) is None


# ── murphy_decomposition ───────────────────────────────────────────────────────

def test_murphy_decomposition_identity_exact_for_bin_constant_forecasts():
    # forecasts constant within each equal-count bin → BS = REL - RES + UNC exactly.
    entries = [
        (0.6, forecast_vector("bearish", 0.6), "down"),
        (0.6, forecast_vector("bearish", 0.6), "up"),
        (0.8, forecast_vector("bullish", 0.8), "up"),
        (0.8, forecast_vector("bullish", 0.8), "up"),
    ]
    bs = sum(brier_score_3class(p, a) for _, p, a in entries) / len(entries)
    m = murphy_decomposition(entries, n_bins=2)
    assert bs == pytest.approx(m["rel"] - m["res"] + m["unc"], abs=1e-9)


def test_murphy_decomposition_unc_matches_outcome_variance():
    # o_bar = (0.5, 0.25, 0.25) → UNC = 0.25 + 0.1875 + 0.1875 = 0.625
    probs = forecast_vector("bullish", 0.7)
    entries = [(0.7, probs, a) for a in ("up", "up", "down", "neutral")]
    m = murphy_decomposition(entries, n_bins=2)
    assert m["unc"] == pytest.approx(0.625)
    assert m["rel"] >= 0.0
    assert m["res"] >= 0.0


def test_murphy_decomposition_empty_input_returns_none():
    assert murphy_decomposition([], n_bins=5) is None


# ── score_predictions ──────────────────────────────────────────────────────────

def _rows() -> list[dict]:
    return [
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": 3.0},
        {"predicted_direction": "bearish", "confidence": 0.65, "actual_price_change_pct": -3.0},
        {"predicted_direction": "neutral", "confidence": 0.50, "actual_price_change_pct": 0.2},
        {"predicted_direction": "bullish", "confidence": 0.75, "actual_price_change_pct": -3.0},
    ]


def test_score_predictions_empty_input_returns_honest_none_metrics():
    out = score_predictions([])
    assert out["n_scored"] == 0
    assert out["brier"] is None
    assert out["log_loss"] is None
    assert out["brier_climatology"] is None
    assert out["bss_vs_climatology"] is None
    assert out["bss_vs_uniform"] is None
    assert out["reliability"] == []
    assert out["ece"] is None
    assert out["murphy"] is None


def test_score_predictions_skips_null_change_and_unvalidatable_direction():
    rows = [
        {"predicted_direction": "bullish", "confidence": 0.7, "actual_price_change_pct": 2.0},
        {"predicted_direction": "bullish", "confidence": 0.7, "actual_price_change_pct": None},
        {"predicted_direction": "banana", "confidence": 0.7, "actual_price_change_pct": 2.0},
        {"predicted_direction": "bullish", "actual_price_change_pct": 2.0},  # missing confidence
    ]
    out = score_predictions(rows)
    assert out["n_scored"] == 1


def test_score_predictions_neutral_prediction_is_scored():
    rows = [{"predicted_direction": "neutral", "confidence": 0.6, "actual_price_change_pct": 0.1}]
    out = score_predictions(rows)
    assert out["n_scored"] == 1
    # BS = (0.2-0)^2 + (0.2-0)^2 + (0.6-1)^2 = 0.04 + 0.04 + 0.16 = 0.24
    assert out["brier"] == pytest.approx(0.24)


def test_score_predictions_uniform_anchor_is_two_thirds():
    out = score_predictions(_rows())
    assert out["brier_uniform"] == pytest.approx(0.6667, abs=1e-4)


def test_score_predictions_perfect_forecasts_beat_both_baselines():
    rows = [
        {"predicted_direction": "bullish", "confidence": 1.0, "actual_price_change_pct": 3.0},
        {"predicted_direction": "bearish", "confidence": 1.0, "actual_price_change_pct": -3.0},
        {"predicted_direction": "neutral", "confidence": 1.0, "actual_price_change_pct": 0.1},
    ]
    out = score_predictions(rows)
    assert out["brier"] == pytest.approx(0.0)
    assert out["log_loss"] == pytest.approx(0.0)
    assert out["bss_vs_uniform"] == pytest.approx(1.0)
    assert out["bss_vs_climatology"] == pytest.approx(1.0)


def test_score_predictions_climatology_reference_equals_uncertainty():
    # mean Brier of the climatology forecast is exactly UNC — a good self-check.
    out = score_predictions(_rows())
    assert out["brier_climatology"] == pytest.approx(out["murphy"]["unc"], abs=1e-3)


def test_score_predictions_does_not_mutate_input_rows():
    rows = _rows()
    snapshot = copy.deepcopy(rows)
    score_predictions(rows)
    assert rows == snapshot


# ── track_record integration (additive "scoring" key) ─────────────────────────

def test_compute_track_record_includes_scoring_key_additively():
    from trust.track_record import compute_track_record

    tr = compute_track_record(_rows())
    assert tr["scoring"]["n_scored"] == 4  # neutral IS scored here, unlike hit rate
    # existing keys untouched
    assert "hit_rate" in tr
    assert "calibration_curve" in tr


def test_compute_track_record_empty_rows_scoring_is_honest():
    from trust.track_record import compute_track_record

    tr = compute_track_record([])
    assert tr["scoring"]["n_scored"] == 0
    assert tr["scoring"]["brier"] is None
