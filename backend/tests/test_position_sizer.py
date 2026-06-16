"""
Tests for fractional-Kelly position sizing.

Covers the pure sizing math (edge detection, shrinkage, clamping) and the
opt-in integration into TradeExecutor — verifying that supplying a historical
win-rate changes sizing while omitting it preserves the legacy linear behaviour.
"""

import dataclasses

import pytest
from services.position_sizer import (
    DEFAULT_KELLY_FRACTION,
    KellyPositionResult,
    compute_kelly_position,
)

pytestmark = pytest.mark.unit


# ── Pure Kelly math ──────────────────────────────────────────────────────────


def test_proven_strong_edge_sizes_to_cap():
    """A high win-rate over a large sample should saturate the position cap."""
    result = compute_kelly_position(
        win_rate_pct=70.0,
        sample_size=100,
        payoff_ratio=2.0,
        stop_risk_percent=4.0,
        max_position_pct=2.0,
    )
    assert result.has_edge is True
    assert result.position_size_percent == 2.0  # clamped to cap
    assert result.kelly_raw > 0


def test_losing_history_has_no_edge_and_floors():
    """A win-rate below break-even must yield no edge and the floor position."""
    result = compute_kelly_position(
        win_rate_pct=30.0,
        sample_size=100,
        payoff_ratio=2.0,
        stop_risk_percent=4.0,
        max_position_pct=2.0,
    )
    assert result.has_edge is False
    assert result.position_size_percent == 0.5
    assert result.kelly_raw <= 0


def test_no_history_defaults_to_no_edge():
    """With zero samples the estimate is the break-even prior → no edge earned."""
    result = compute_kelly_position(
        win_rate_pct=0.0,
        sample_size=0,
        payoff_ratio=2.0,
        stop_risk_percent=4.0,
        max_position_pct=2.0,
    )
    assert result.has_edge is False
    assert result.position_size_percent == 0.5


def test_small_sample_is_shrunk_toward_breakeven():
    """100% over 3 trades must produce a far smaller Kelly than 100% over 100."""
    tiny = compute_kelly_position(
        win_rate_pct=100.0, sample_size=3, payoff_ratio=2.0,
        stop_risk_percent=4.0, max_position_pct=2.0,
    )
    large = compute_kelly_position(
        win_rate_pct=100.0, sample_size=100, payoff_ratio=2.0,
        stop_risk_percent=4.0, max_position_pct=2.0,
    )
    assert tiny.kelly_raw < large.kelly_raw
    assert tiny.win_rate_shrunk < large.win_rate_shrunk


def test_invalid_payoff_returns_floor_no_edge():
    result = compute_kelly_position(
        win_rate_pct=80.0, sample_size=50, payoff_ratio=0.0,
        stop_risk_percent=4.0, max_position_pct=2.0,
    )
    assert result.has_edge is False
    assert result.position_size_percent == 0.5


def test_higher_win_rate_never_decreases_position():
    """Monotonicity: more wins should never shrink the recommended size."""
    sizes = [
        compute_kelly_position(
            win_rate_pct=w, sample_size=100, payoff_ratio=2.0,
            stop_risk_percent=4.0, max_position_pct=5.0,
        ).position_size_percent
        for w in (40.0, 50.0, 60.0, 70.0)
    ]
    assert sizes == sorted(sizes)


def test_result_is_immutable():
    result = compute_kelly_position(
        win_rate_pct=70.0, sample_size=100, payoff_ratio=2.0,
        stop_risk_percent=4.0, max_position_pct=2.0,
    )
    assert isinstance(result, KellyPositionResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.position_size_percent = 99.0  # type: ignore[misc]


def test_default_fraction_is_quarter_kelly():
    assert DEFAULT_KELLY_FRACTION == 0.25


# ── Integration with TradeExecutor (opt-in) ──────────────────────────────────


def _bullish_request(**overrides):
    """A BULLISH request that produces a valid execution plan."""
    from models.trade_execution import TradeExecutionRequest

    params = {
        "prediction_id": "kelly-test-001",
        "stock_ticker": "BHP.AX",
        "current_price": 45.0,
        "direction": "BULLISH",
        "recommendation": "BUY",
        "confidence_score": 70,
        "risk_tolerance": "moderate",
        "atr_14": 0.9,  # 2% ATR → 1.8 stop distance (moderate 2.0x) → ~4% risk
        "resistance_levels": [49.0, 51.0, 53.0],
    }
    params.update(overrides)
    return TradeExecutionRequest(**params)


def test_executor_uses_kelly_when_winrate_supplied():
    """Proven edge should size up versus the legacy linear haircut."""
    from agents.trade_executor import TradeExecutor

    executor = TradeExecutor()
    linear = executor.generate_execution_plan(_bullish_request())
    kelly = executor.generate_execution_plan(
        _bullish_request(historical_win_rate=70.0, historical_sample_size=100)
    )

    assert linear is not None and kelly is not None
    # Linear applies a confidence × risk haircut; Kelly on a proven edge sizes to cap.
    assert kelly.position_size_percent > linear.position_size_percent


def test_executor_downsizes_on_losing_history():
    """A losing track record should size down to the floor."""
    from agents.trade_executor import TradeExecutor

    executor = TradeExecutor()
    kelly = executor.generate_execution_plan(
        _bullish_request(historical_win_rate=30.0, historical_sample_size=100)
    )
    assert kelly is not None
    assert kelly.position_size_percent == 0.5


def test_executor_unchanged_without_winrate():
    """Omitting history must preserve the existing linear sizing exactly."""
    from agents.trade_executor import TradeExecutor

    executor = TradeExecutor()
    req = _bullish_request()
    plan = executor.generate_execution_plan(req)
    assert plan is not None
    # Legacy formula: base(2.0) × conf(0.70) × risk_mult(0.5 when risk%>3) = 0.70
    assert plan.position_size_percent == pytest.approx(0.70, abs=0.01)
