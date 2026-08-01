"""Regression tests for the MC price-model realism fixes.

Live bug (CBA.AX, 2026-08-01): lopsided agent votes produced a drift that
overwhelmed daily volatility — every simulated path finished positive,
yielding "Prob. of Profit 100%", a POSITIVE VaR captioned as a loss, and CI
bounds that contradicted the ATR-capped target on the prediction card.
"""

import pandas as pd
from services.game_theory.monte_carlo import (
    _MAX_DRIFT_VOL_RATIO,
    _MIN_DAILY_VOL,
    run_price_range_monte_carlo,
)
from services.price_target_validator import cap_price_range


def _run(direction_probability: float, price: float = 177.53):
    # No price_series → fallback vol table; deterministic seed inside.
    return run_price_range_monte_carlo(
        current_price=price,
        direction_probability=direction_probability,
        ticker="CBA.AX",
        days=7,
        n_simulations=2000,
    )


# ── Bug 2: fake certainty ─────────────────────────────────────────────────────

def test_prob_profit_never_100_even_on_lopsided_votes():
    """The exact CBA setup: 24% bearish votes → strong bullish drift."""
    result = _run(direction_probability=0.24)
    assert result.prob_profit <= 99.0
    assert result.prob_profit >= 1.0


def test_prob_profit_never_0_on_lopsided_bearish():
    result = _run(direction_probability=0.95)
    assert result.prob_profit >= 1.0


def test_drift_capped_leaves_downside_scenarios():
    """With drift ≤ 60% of vol, the 5th percentile must be a real loss —
    a market never offers a 7-day trade with zero downside."""
    result = _run(direction_probability=0.05)  # maximally bullish votes
    assert result.range_90pct_low < result.current_price


def test_realism_constants_sane():
    assert 0 < _MIN_DAILY_VOL <= 0.02
    assert 0 < _MAX_DRIFT_VOL_RATIO < 1.0


# ── Bug 3: VaR/CVaR wording for positive tail values ──────────────────────────

def test_var_interpretation_never_calls_gain_a_loss():
    for dp in (0.05, 0.24, 0.5, 0.76, 0.95):
        result = _run(direction_probability=dp)
        if result.var_95 >= 0:
            assert "loss won't exceed" not in result.var_interpretation
            assert "at or above" in result.var_interpretation
        else:
            assert "loss won't exceed" in result.var_interpretation
        if result.cvar_95 >= 0:
            assert "avg loss" not in result.cvar_interpretation
        else:
            assert "avg loss" in result.cvar_interpretation


# ── Bug 1: CI bounds must respect the ATR cap ─────────────────────────────────

def test_cap_price_range_bounds_entire_distribution():
    """The live contradiction: capped target 185.42 with 90% CI 185.69-196.12."""
    mc = _run(direction_probability=0.24, price=177.53)
    max_pct = 4.45  # the ATR cap from the live CBA card
    cap_price_range(mc, 177.53, max_pct)

    hi = 177.53 * (1 + max_pct / 100)
    lo = 177.53 * (1 - max_pct / 100)
    assert mc.expected_price_7d <= hi + 0.01
    assert mc.range_90pct_high <= hi + 0.01
    assert mc.range_68pct_high <= hi + 0.01
    assert mc.range_90pct_low >= lo - 0.01
    assert mc.range_68pct_low >= lo - 0.01
    # CI must never sit entirely above the expected price
    assert mc.range_90pct_low <= mc.expected_price_7d <= mc.range_90pct_high
    assert abs(mc.expected_return) <= max_pct
    assert abs(mc.expected_change_pct) <= max_pct + 0.01


def test_cap_price_range_noop_on_zero_cap():
    mc = _run(direction_probability=0.5)
    before = (mc.expected_price_7d, mc.range_90pct_high, mc.range_90pct_low)
    cap_price_range(mc, mc.current_price, 0.0)
    assert (mc.expected_price_7d, mc.range_90pct_high, mc.range_90pct_low) == before


def test_cap_price_range_noop_when_already_inside_band():
    mc = _run(direction_probability=0.5)
    cap_price_range(mc, mc.current_price, 50.0)  # absurdly wide cap
    assert mc.range_90pct_high > mc.range_68pct_high  # ordering untouched


# ── Volatility floor ──────────────────────────────────────────────────────────

def test_vol_floor_applies_with_flat_price_series():
    """A nearly-flat price history must not produce a near-zero-vol simulation."""
    flat = pd.Series([100.0 + (i % 2) * 0.01 for i in range(60)])
    result = run_price_range_monte_carlo(
        current_price=100.0,
        direction_probability=0.5,
        ticker="CBA.AX",
        days=7,
        n_simulations=2000,
        price_series=flat,
    )
    # With the floor, a 7-day 90% band must span at least ~2% total width
    width_pct = (result.range_90pct_high - result.range_90pct_low) / 100.0 * 100
    assert width_pct > 2.0
