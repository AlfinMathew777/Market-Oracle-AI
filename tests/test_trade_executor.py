"""
Tests for Trade Executor Agent
--------------------------------
Covers: generate_execution_plan, stop-loss logic, take-profit targets,
        R:R ratio validation, position sizing, setup grading.
"""

import pytest
from agents.trade_executor import TradeExecutor
from models.trade_execution import TradeAction, TradeExecutionRequest


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def executor():
    return TradeExecutor()


def _bullish_request(**overrides) -> TradeExecutionRequest:
    defaults = dict(
        prediction_id="test-bull",
        stock_ticker="BHP.AX",
        current_price=51.50,
        direction="BULLISH",
        recommendation="BUY",
        confidence_score=72,
        risk_tolerance="moderate",
        atr_14=1.35,
        support_levels=[50.00, 48.50, 47.00],
        resistance_levels=[53.00, 54.50, 56.00],
        ma_20=50.80,
        ma_50=49.50,
        ma_200=48.00,
        rsi_14=56.0,
    )
    defaults.update(overrides)
    return TradeExecutionRequest(**defaults)


def _bearish_request(**overrides) -> TradeExecutionRequest:
    defaults = dict(
        prediction_id="test-bear",
        stock_ticker="CBA.AX",
        current_price=95.00,
        direction="BEARISH",
        recommendation="SELL",
        confidence_score=65,
        risk_tolerance="moderate",
        atr_14=2.10,
        support_levels=[92.00, 90.00, 88.00],
        resistance_levels=[97.00, 99.00, 100.00],
        ma_50=97.50,
        rsi_14=68.0,
    )
    defaults.update(overrides)
    return TradeExecutionRequest(**defaults)


# ── Action direction ───────────────────────────────────────────────────────────

class TestActionDirection:

    def test_bullish_generates_buy(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result is not None
        assert result.action == TradeAction.BUY

    def test_bearish_generates_sell(self, executor):
        result = executor.generate_execution_plan(_bearish_request())
        assert result is not None
        assert result.action == TradeAction.SELL

    def test_hold_returns_none(self, executor):
        req = _bullish_request(recommendation="HOLD")
        assert executor.generate_execution_plan(req) is None

    def test_wait_returns_none(self, executor):
        req = _bullish_request(recommendation="WAIT")
        assert executor.generate_execution_plan(req) is None

    def test_neutral_direction_returns_none(self, executor):
        req = _bullish_request(direction="NEUTRAL", recommendation="BUY")
        assert executor.generate_execution_plan(req) is None


# ── Stop-loss placement ────────────────────────────────────────────────────────

class TestStopLoss:

    def test_stop_below_entry_for_bullish(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result.stop_loss < result.entry_price

    def test_stop_above_entry_for_bearish(self, executor):
        result = executor.generate_execution_plan(_bearish_request())
        assert result.stop_loss > result.entry_price

    def test_atr_distance_moderate_bullish(self, executor):
        """Moderate risk = 2.0× ATR stop distance."""
        req = _bullish_request(current_price=50.00, atr_14=1.00,
                               resistance_levels=[55.00, 60.00])
        result = executor.generate_execution_plan(req)
        expected_stop = 50.00 - (1.00 * 2.0)
        assert abs(result.stop_loss - expected_stop) < 0.01

    def test_fallback_when_no_atr(self, executor):
        """Without ATR, should use a percentage fallback and still be below entry."""
        req = _bullish_request(atr_14=None, resistance_levels=[60.00, 65.00])
        result = executor.generate_execution_plan(req)
        if result:
            assert result.stop_loss < result.entry_price


# ── Take-profit targets ────────────────────────────────────────────────────────

class TestTakeProfitTargets:

    def test_tp1_above_entry_bullish(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result.take_profit_1 > result.entry_price

    def test_tp1_below_entry_bearish(self, executor):
        result = executor.generate_execution_plan(_bearish_request())
        assert result.take_profit_1 < result.entry_price

    def test_tp2_further_than_tp1_bullish(self, executor):
        req = _bullish_request(resistance_levels=[54.00, 57.00, 60.00])
        result = executor.generate_execution_plan(req)
        if result and result.take_profit_2:
            assert result.take_profit_2 > result.take_profit_1

    def test_tp2_further_than_tp1_bearish(self, executor):
        req = _bearish_request(support_levels=[90.00, 87.00, 84.00])
        result = executor.generate_execution_plan(req)
        if result and result.take_profit_2:
            assert result.take_profit_2 < result.take_profit_1


# ── Risk/Reward ratio ──────────────────────────────────────────────────────────

class TestRiskReward:

    def test_moderate_meets_2to1_minimum(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result.risk_reward.risk_reward_ratio >= 2.0

    def test_conservative_meets_3to1_minimum(self, executor):
        req = _bullish_request(risk_tolerance="conservative",
                               resistance_levels=[60.00, 65.00, 70.00])
        result = executor.generate_execution_plan(req)
        if result:
            assert result.risk_reward.risk_reward_ratio >= 3.0

    def test_rr_calculation_accuracy(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        risk = result.entry_price - result.stop_loss
        reward = result.take_profit_1 - result.entry_price
        expected = round(reward / risk, 2)
        assert abs(result.risk_reward.risk_reward_ratio - expected) < 0.02

    def test_always_generates_targets_via_fallback(self, executor):
        """Even with no resistance levels, executor generates targets from ATR multiples."""
        req = _bullish_request(
            current_price=50.00,
            atr_14=1.00,
            resistance_levels=[],  # no resistance
        )
        result = executor.generate_execution_plan(req)
        # Executor falls back to min_rr multiples — should always produce a result
        assert result is not None
        assert result.take_profit_1 > result.entry_price


# ── Position sizing ────────────────────────────────────────────────────────────

class TestPositionSizing:

    def test_size_within_bounds(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert 0.5 <= result.position_size_percent <= 5.0

    def test_high_confidence_larger_than_low(self, executor):
        high = executor.generate_execution_plan(
            _bullish_request(confidence_score=85, resistance_levels=[60.00, 65.00])
        )
        low = executor.generate_execution_plan(
            _bullish_request(confidence_score=45, resistance_levels=[60.00, 65.00])
        )
        if high and low:
            assert high.position_size_percent >= low.position_size_percent


# ── Setup grading ──────────────────────────────────────────────────────────────

class TestSetupGrading:

    def test_grade_is_valid_literal(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result.setup_quality in ("A+", "A", "B", "C")

    def test_high_conf_high_rr_gets_good_grade(self, executor):
        req = _bullish_request(
            confidence_score=85,
            resistance_levels=[60.00, 65.00, 70.00],
        )
        result = executor.generate_execution_plan(req)
        if result:
            assert result.setup_quality in ("A+", "A", "B")


# ── Output completeness ────────────────────────────────────────────────────────

class TestOutputCompleteness:

    def test_ticker_preserved(self, executor):
        result = executor.generate_execution_plan(_bullish_request(stock_ticker="RIO.AX"))
        assert result.stock_ticker == "RIO.AX"

    def test_entry_equals_current_price(self, executor):
        result = executor.generate_execution_plan(_bullish_request(current_price=50.00))
        assert result.entry_price == 50.00

    def test_timestamps_set(self, executor):
        result = executor.generate_execution_plan(_bullish_request())
        assert result.generated_at is not None
        assert result.valid_until > result.generated_at
