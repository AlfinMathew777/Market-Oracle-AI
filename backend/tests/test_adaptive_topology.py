"""Tests for services/adaptive_topology.py — contested-signal reallocation."""

from services.adaptive_topology import (
    apply_contest_adjustment,
    compute_contest_score,
)

_PERSONAS = ("macro_bull", "geo_bear", "quant", "neutral_fund")


def _dist(bull=5, bear=5, quant=6, neutral=9):
    return {
        "macro_bull": bull, "geo_bear": bear,
        "quant": quant, "neutral_fund": neutral,
        "description": "test distribution",
    }


def _total(dist):
    return sum(dist[k] for k in _PERSONAS)


# ── compute_contest_score ─────────────────────────────────────────────────────

def test_no_signals_no_contest():
    score, reasons = compute_contest_score("NEUTRAL", None, None)
    assert score == 0.0
    assert reasons == []


def test_rsi_oversold_vs_downtrend_is_contested():
    score, reasons = compute_contest_score("STRONG_DOWNTREND", 20.0, None)
    assert score == 0.5
    assert "oversold" in reasons[0]


def test_rsi_overbought_vs_uptrend_is_contested():
    score, reasons = compute_contest_score("STRONG_UPTREND", 80.0, None)
    assert score == 0.5
    assert "overbought" in reasons[0]


def test_rsi_agreeing_with_trend_is_not_contested():
    # Oversold in an uptrend is a buy signal, not a conflict
    score, _ = compute_contest_score("STRONG_UPTREND", 20.0, None)
    assert score == 0.0


def test_alt_data_conflict_scores():
    score, reasons = compute_contest_score("DOWNTREND", None, 0.4)
    assert score == 0.5
    assert "alt-data bullish" in reasons[0]


def test_alt_data_deadband_ignored():
    score, _ = compute_contest_score("DOWNTREND", None, 0.02)
    assert score == 0.0


def test_both_conflicts_cap_at_one():
    score, reasons = compute_contest_score("STRONG_DOWNTREND", 20.0, 0.4)
    assert score == 1.0
    assert len(reasons) == 2


# ── apply_contest_adjustment ──────────────────────────────────────────────────

def test_zero_score_unchanged():
    original = _dist()
    adjusted, note = apply_contest_adjustment(original, 0.0)
    assert note == ""
    assert adjusted == original
    assert adjusted is not original  # immutability: always a new dict


def test_partial_contest_moves_one_per_side():
    adjusted, note = apply_contest_adjustment(_dist(), 0.5)
    assert note != ""
    assert adjusted["macro_bull"] == 6
    assert adjusted["geo_bear"] == 6
    assert adjusted["neutral_fund"] == 7
    assert _total(adjusted) == _total(_dist())


def test_full_contest_moves_two_per_side():
    adjusted, note = apply_contest_adjustment(_dist(), 1.0)
    assert note != ""
    assert adjusted["macro_bull"] == 7
    assert adjusted["geo_bear"] == 7
    assert _total(adjusted) == _total(_dist())


def test_symmetry_is_always_preserved():
    """Reallocation must never bias one direction over the other."""
    for score in (0.5, 0.75, 1.0):
        base = _dist()
        adjusted, _ = apply_contest_adjustment(base, score)
        gained_bull = adjusted["macro_bull"] - base["macro_bull"]
        gained_bear = adjusted["geo_bear"] - base["geo_bear"]
        assert gained_bull == gained_bear


def test_floors_respected_when_bench_is_thin():
    """A thin bench cannot be drained below its floor."""
    thin = _dist(bull=8, bear=8, quant=4, neutral=5)  # both benches at floor
    adjusted, note = apply_contest_adjustment(thin, 1.0)
    assert note == ""
    assert adjusted["neutral_fund"] == 5
    assert adjusted["quant"] == 4
    assert _total(adjusted) == _total(thin)


def test_head_count_always_preserved():
    for score in (0.0, 0.4, 0.5, 0.6, 0.75, 1.0):
        for neutral in (5, 6, 7, 9):
            base = _dist(neutral=neutral)
            adjusted, _ = apply_contest_adjustment(base, score)
            assert _total(adjusted) == _total(base)
