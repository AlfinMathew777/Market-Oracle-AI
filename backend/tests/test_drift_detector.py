"""Tests for monitoring/drift_detector.py — distribution-shift detection."""

import random

from monitoring.drift_detector import (
    DRIFT_MULTIPLIERS,
    assess_drift,
    check_drift,
    classify_drift,
    compute_categorical_psi,
    compute_psi,
    drift_confidence_multiplier,
)


def _rows(n, confidence=0.6, direction="bullish", correct=None):
    return [
        {"confidence": confidence, "predicted_direction": direction, "prediction_correct": correct}
        for _ in range(n)
    ]


# ── PSI math ──────────────────────────────────────────────────────────────────

def test_identical_distributions_psi_near_zero():
    rng = random.Random(1)  # noqa: S311 — test data
    base = [rng.gauss(0.6, 0.1) for _ in range(200)]
    assert compute_psi(base, list(base)) < 0.01


def test_shifted_distribution_high_psi():
    rng = random.Random(2)  # noqa: S311 — test data
    base = [rng.gauss(0.6, 0.05) for _ in range(200)]
    shifted = [rng.gauss(0.3, 0.05) for _ in range(200)]
    assert compute_psi(base, shifted) > 0.25


def test_empty_samples_psi_zero():
    assert compute_psi([], [0.5]) == 0.0
    assert compute_psi([0.5], []) == 0.0


def test_degenerate_baseline_psi_zero():
    # All-identical baseline has no distribution to shift against
    assert compute_psi([0.5] * 50, [0.9] * 50) == 0.0


def test_categorical_psi_detects_direction_flip():
    base = ["bullish"] * 70 + ["bearish"] * 20 + ["neutral"] * 10
    flipped = ["bullish"] * 10 + ["bearish"] * 80 + ["neutral"] * 10
    psi = compute_categorical_psi(base, flipped, ("bullish", "bearish", "neutral"))
    assert psi > 0.25


def test_categorical_psi_same_mix_near_zero():
    base = ["bullish"] * 50 + ["bearish"] * 30 + ["neutral"] * 20
    assert compute_categorical_psi(base, list(base), ("bullish", "bearish", "neutral")) < 0.01


# ── Classification & multipliers ──────────────────────────────────────────────

def test_classify_bands():
    assert classify_drift(0.05) == "NONE"
    assert classify_drift(0.15) == "MODERATE"
    assert classify_drift(0.30) == "SEVERE"


def test_multipliers_bounded():
    for level, mult in DRIFT_MULTIPLIERS.items():
        assert 0.5 <= mult <= 1.0, level
    assert drift_confidence_multiplier("UNKNOWN_LEVEL") == 1.0


# ── assess_drift ──────────────────────────────────────────────────────────────

def test_insufficient_data_reports_none():
    result = assess_drift(_rows(5), _rows(5))
    assert result["level"] == "NONE"
    assert result["multiplier"] == 1.0
    assert "insufficient" in result["note"]


def test_stable_windows_report_none():
    rng = random.Random(3)  # noqa: S311 — test data
    base = [
        {"confidence": rng.gauss(0.6, 0.08), "predicted_direction": rng.choice(["bullish", "bearish"]),
         "prediction_correct": rng.choice([0, 1])}
        for _ in range(100)
    ]
    recent = [
        {"confidence": rng.gauss(0.6, 0.08), "predicted_direction": rng.choice(["bullish", "bearish"]),
         "prediction_correct": rng.choice([0, 1])}
        for _ in range(50)
    ]
    result = assess_drift(base, recent)
    assert result["level"] == "NONE"
    assert result["multiplier"] == 1.0


def test_confidence_regime_shift_detected():
    base = _rows(100, confidence=0.65)
    # vary baseline so it isn't degenerate
    for i, r in enumerate(base):
        r["confidence"] = 0.55 + (i % 10) * 0.02
    recent = _rows(40, confidence=0.30)
    result = assess_drift(base, recent)
    assert result["level"] in ("MODERATE", "SEVERE")
    assert result["multiplier"] < 1.0


def test_accuracy_collapse_escalates():
    base = [dict(r, prediction_correct=1) for r in _rows(60)]
    for i, r in enumerate(base):
        r["confidence"] = 0.55 + (i % 10) * 0.02
    recent = [dict(r, prediction_correct=0) for r in _rows(30)]
    for i, r in enumerate(recent):
        r["confidence"] = 0.55 + (i % 10) * 0.02
    result = assess_drift(base, recent)
    # confidence/direction identical → PSI ~0, but accuracy fell 100% → 0%
    assert result["level"] != "NONE"


# ── DB-backed check ───────────────────────────────────────────────────────────

async def test_check_drift_fails_soft(monkeypatch):
    import database

    async def broken(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(database, "get_full_prediction_log", broken)
    result = await check_drift()
    assert result["level"] == "NONE"
    assert result["multiplier"] == 1.0
    assert "fail-soft" in result["note"]
