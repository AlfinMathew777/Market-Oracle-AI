"""Tests for quant/significance.py — track-record permutation test."""

import random

from quant.significance import (
    _MIN_SAMPLE,
    permutation_test_accuracy,
    run_accuracy_significance,
)


def _pairs(correct: int, incorrect: int, pred: str = "bullish"):
    opposite = "bearish" if pred == "bullish" else "bullish"
    return [(pred, pred)] * correct + [(pred, opposite)] * incorrect


# ── Guard rails ───────────────────────────────────────────────────────────────

def test_insufficient_sample_refused():
    result = permutation_test_accuracy(_pairs(3, 2))
    assert "error" in result
    assert result["n_predictions"] == 5


def test_neutral_pairs_excluded():
    pairs = _pairs(6, 6) + [("neutral", "bullish")] * 20 + [("bullish", "neutral")] * 20
    result = permutation_test_accuracy(pairs)
    assert result["n_predictions"] == 12  # neutrals never count


# ── Statistical behaviour ─────────────────────────────────────────────────────

def test_perfect_predictor_is_significant():
    # 30 correct out of 30 with mixed directions — inarguably informative
    pairs = [("bullish", "bullish")] * 15 + [("bearish", "bearish")] * 15
    result = permutation_test_accuracy(pairs, n_permutations=2000)
    assert result["observed_accuracy_pct"] == 100.0
    assert result["p_value"] < 0.05
    assert result["is_significant"] is True


def test_coin_flip_predictor_not_significant():
    # Random labels on both sides — accuracy should sit inside the null
    rng = random.Random(7)  # noqa: S311 — test data generation, not crypto
    pairs = [
        (rng.choice(["bullish", "bearish"]), rng.choice(["bullish", "bearish"]))
        for _ in range(200)
    ]
    result = permutation_test_accuracy(pairs, n_permutations=2000)
    assert result["is_significant"] is False
    assert result["p_value"] >= 0.05


def test_one_sided_market_gives_free_accuracy_but_no_significance():
    """The killer case: always-bullish predictor in an always-up market.

    Accuracy is 100%, but shuffling identical labels changes nothing —
    the null distribution IS 100%, so the p-value must be ~1, not ~0.
    A naive coin-flip baseline would wrongly call this significant.
    """
    pairs = [("bullish", "bullish")] * 50
    result = permutation_test_accuracy(pairs, n_permutations=1000)
    assert result["observed_accuracy_pct"] == 100.0
    assert result["null_mean_accuracy_pct"] == 100.0
    assert result["p_value"] > 0.9
    assert result["is_significant"] is False


def test_deterministic_given_seed():
    pairs = _pairs(40, 20) + [("bearish", "bearish")] * 25 + [("bearish", "bullish")] * 15
    a = permutation_test_accuracy(pairs, n_permutations=500, seed=42)
    b = permutation_test_accuracy(pairs, n_permutations=500, seed=42)
    assert a == b


def test_pvalue_never_exactly_zero():
    # add-one correction: even a perfect result keeps p >= 1/(n+1)
    pairs = [("bullish", "bullish")] * 20 + [("bearish", "bearish")] * 20
    result = permutation_test_accuracy(pairs, n_permutations=100)
    # p is rounded to 5 dp in the payload — compare against the rounded floor
    assert result["p_value"] >= round(1 / 101, 5)
    assert result["p_value"] > 0.0


def test_result_shape():
    result = permutation_test_accuracy(_pairs(30, 20), n_permutations=200)
    for key in (
        "observed_accuracy_pct", "n_predictions", "n_correct", "p_value",
        "is_significant", "null_mean_accuracy_pct", "null_std_pct",
        "null_p95_accuracy_pct", "n_permutations", "seed", "interpretation",
    ):
        assert key in result
    assert result["n_correct"] == 30


# ── DB-backed runner ──────────────────────────────────────────────────────────

async def test_run_accuracy_significance_fails_soft(monkeypatch):
    """A DB error returns an error payload, never raises."""
    import quant.significance as sig

    async def broken(*args, **kwargs):
        raise RuntimeError("db gone")

    import database
    monkeypatch.setattr(database, "get_resolved_direction_pairs", broken)
    result = await sig.run_accuracy_significance(ticker="BHP.AX", days=90)
    assert "error" in result
    assert result["ticker"] == "BHP.AX"


async def test_run_accuracy_significance_happy_path(monkeypatch):
    import database

    async def fake_pairs(ticker=None, days=365, limit=5000):
        return (
            [{"predicted_direction": "bullish", "actual_direction": "bullish"}] * 20
            + [{"predicted_direction": "bearish", "actual_direction": "bearish"}] * 20
            + [{"predicted_direction": "bullish", "actual_direction": "bearish"}] * 5
        )

    monkeypatch.setattr(database, "get_resolved_direction_pairs", fake_pairs)
    result = await run_accuracy_significance(days=180, n_permutations=500)
    assert result["n_predictions"] == 45
    assert result["window_days"] == 180
    assert result["ticker"] == "ALL"
    assert result["is_significant"] is True


async def test_min_sample_constant_reasonable():
    assert _MIN_SAMPLE >= 10
