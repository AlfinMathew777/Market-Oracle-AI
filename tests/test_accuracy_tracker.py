"""
Tests for Accuracy Tracker Service
-----------------------------------
Covers: store_prediction, resolve_pending_predictions, _age_days, _evaluate_outcome
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_reasoning_output():
    """Return a minimal ReasoningOutput mock with the fields accuracy_tracker reads."""
    ro = MagicMock()
    ro.stock_ticker = "BHP.AX"
    ro.final_decision.direction.value = "BULLISH"
    ro.final_decision.recommendation.value = "BUY"
    ro.final_decision.confidence_score = 72
    ro.event_classification.model_dump.return_value = {"type": "DIRECT"}
    ro.causal_chain.model_dump.return_value = {"summary": "test"}
    ro.market_context.model_dump.return_value = {"alignment": "bullish"}
    ro.consensus_analysis.model_dump.return_value = {"bullish": 30, "bearish": 5}
    ro.model_dump.return_value = {}
    return ro


def _make_trade_execution(entry=51.50, stop=49.80, tp1=54.20, tp2=55.80, tp3=None):
    te = MagicMock()
    te.entry_price = entry
    te.stop_loss = stop
    te.take_profit_1 = tp1
    te.take_profit_2 = tp2
    te.take_profit_3 = tp3
    te.model_dump.return_value = {"entry_price": entry, "stop_loss": stop}
    return te


# ── store_prediction ───────────────────────────────────────────────────────────

class TestStorePrediction:

    @pytest.mark.asyncio
    async def test_returns_string_uuid(self):
        """store_prediction should return a UUID string on success."""
        import uuid

        ro = _make_reasoning_output()
        te = _make_trade_execution()

        with patch("services.accuracy_tracker.save_reasoning_prediction", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = None

            from services.accuracy_tracker import store_prediction
            result = await store_prediction(
                reasoning_output=ro,
                current_price=51.50,
                trade_execution=te,
            )

        assert isinstance(result, str)
        uuid.UUID(result)  # raises ValueError if not a valid UUID

    @pytest.mark.asyncio
    async def test_works_without_trade_execution(self):
        """store_prediction should succeed when trade_execution is None."""
        ro = _make_reasoning_output()

        with patch("services.accuracy_tracker.save_reasoning_prediction", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = None

            from services.accuracy_tracker import store_prediction
            result = await store_prediction(
                reasoning_output=ro,
                current_price=51.50,
                trade_execution=None,
            )

        assert result is not None
        # Verify None values passed for trade fields
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["entry_price"] is None
        assert call_kwargs["stop_loss"] is None

    @pytest.mark.asyncio
    async def test_passes_trade_levels_to_db(self):
        """store_prediction should forward trade execution levels."""
        ro = _make_reasoning_output()
        te = _make_trade_execution(entry=51.50, stop=49.80, tp1=54.20)

        with patch("services.accuracy_tracker.save_reasoning_prediction", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = None

            from services.accuracy_tracker import store_prediction
            await store_prediction(
                reasoning_output=ro,
                current_price=51.50,
                trade_execution=te,
            )

        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["entry_price"] == 51.50
        assert call_kwargs["stop_loss"] == 49.80
        assert call_kwargs["take_profit_1"] == 54.20


# ── resolve_pending_predictions ────────────────────────────────────────────────

class TestResolvePendingPredictions:

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_pending(self):
        """Should return 0 when there are no pending predictions."""
        with patch("services.accuracy_tracker.get_pending_reasoning_predictions", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []

            from services.accuracy_tracker import resolve_pending_predictions
            result = await resolve_pending_predictions()

        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_price_unavailable(self):
        """Should skip a prediction if the current price cannot be fetched."""
        pending = [
            {
                "id": "pred-1",
                "stock_ticker": "BHP.AX",
                "direction": "BULLISH",
                "price_at_prediction": 50.00,
                "stop_loss": 48.00,
                "take_profit_1": 53.00,
                "take_profit_2": None,
                "take_profit_3": None,
                "prediction_timestamp": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            }
        ]

        with patch("services.accuracy_tracker.get_pending_reasoning_predictions", new_callable=AsyncMock, return_value=pending), \
             patch("services.accuracy_tracker._fetch_price", return_value=None), \
             patch("services.accuracy_tracker.update_reasoning_outcome", new_callable=AsyncMock) as mock_update:

            from services.accuracy_tracker import resolve_pending_predictions
            result = await resolve_pending_predictions()

        assert result == 0
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolves_correct_bullish(self):
        """Price above TP1 for a BULLISH prediction should mark it CORRECT."""
        pending = [
            {
                "id": "pred-2",
                "stock_ticker": "BHP.AX",
                "direction": "BULLISH",
                "price_at_prediction": 50.00,
                "stop_loss": 48.00,
                "take_profit_1": 53.00,
                "take_profit_2": None,
                "take_profit_3": None,
                "prediction_timestamp": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            }
        ]

        with patch("services.accuracy_tracker.get_pending_reasoning_predictions", new_callable=AsyncMock, return_value=pending), \
             patch("services.accuracy_tracker._fetch_price", return_value=55.00), \
             patch("services.accuracy_tracker.update_reasoning_outcome", new_callable=AsyncMock) as mock_update:

            from services.accuracy_tracker import resolve_pending_predictions
            result = await resolve_pending_predictions()

        assert result == 1
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["outcome_status"] in ("CORRECT", "PARTIAL")

    @pytest.mark.asyncio
    async def test_resolves_stopped_out(self):
        """Price below stop-loss for BULLISH should mark it STOPPED_OUT or INCORRECT."""
        pending = [
            {
                "id": "pred-3",
                "stock_ticker": "BHP.AX",
                "direction": "BULLISH",
                "price_at_prediction": 50.00,
                "stop_loss": 48.00,
                "take_profit_1": 53.00,
                "take_profit_2": None,
                "take_profit_3": None,
                "prediction_timestamp": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            }
        ]

        with patch("services.accuracy_tracker.get_pending_reasoning_predictions", new_callable=AsyncMock, return_value=pending), \
             patch("services.accuracy_tracker._fetch_price", return_value=46.00), \
             patch("services.accuracy_tracker.update_reasoning_outcome", new_callable=AsyncMock) as mock_update:

            from services.accuracy_tracker import resolve_pending_predictions
            result = await resolve_pending_predictions()

        assert result == 1
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["outcome_status"] in ("INCORRECT", "STOPPED_OUT")
        assert call_kwargs["hit_stop_loss"] is True


# ── _age_days ──────────────────────────────────────────────────────────────────

class TestAgeDays:

    def test_age_days_two_days_ago(self):
        from services.accuracy_tracker import _age_days
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert _age_days(ts) == 2

    def test_age_days_invalid_returns_zero(self):
        from services.accuracy_tracker import _age_days
        assert _age_days("not-a-date") == 0

    def test_age_days_z_suffix(self):
        from services.accuracy_tracker import _age_days
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _age_days(ts) == 1


# ── _evaluate_outcome ──────────────────────────────────────────────────────────

class TestEvaluateOutcome:

    def _call(self, direction, entry, current, stop, tp1, tp2=None, tp3=None, age=3):
        from services.accuracy_tracker import _evaluate_outcome
        return _evaluate_outcome(
            direction=direction,
            entry_price=entry,
            current_price=current,
            stop_loss=stop,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            prediction_age_days=age,
        )

    def test_bullish_hit_tp1(self):
        result = self._call("BULLISH", 50.0, 54.0, 48.0, tp1=53.0)
        assert result["status"] in ("CORRECT", "PARTIAL")
        assert result["hit_tp1"] is True

    def test_bullish_stopped_out(self):
        result = self._call("BULLISH", 50.0, 47.0, 48.0, tp1=53.0)
        assert result["hit_stop"] is True
        assert result["status"] in ("INCORRECT", "STOPPED_OUT")

    def test_pending_when_too_early(self):
        """Prediction less than 1 day old should stay PENDING."""
        result = self._call("BULLISH", 50.0, 50.5, 48.0, tp1=53.0, age=0)
        assert result["status"] == "PENDING"

    def test_bearish_hit_tp1(self):
        result = self._call("BEARISH", 95.0, 91.0, 97.0, tp1=92.0)
        assert result["hit_tp1"] is True
        assert result["status"] in ("CORRECT", "PARTIAL")
