"""
Tests for validation/outcome_checker.py.

Split into:
  - Pure function tests (no DB, no network): _determine_outcome, _parse_timestamp,
    _next_market_open, _effective_target_time
  - DB-integrated tests (isolated_db fixture): get_pending_validations,
    run_validation_job
  - Network tests (mock_yfinance fixture): fetch_price_at_time, validate_prediction
"""

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tests.conftest import insert_prediction

_SYDNEY = ZoneInfo("Australia/Sydney")


# ── _determine_outcome (pure) ──────────────────────────────────────────────────

class TestDetermineOutcome:
    """Pure function — no fixtures needed."""

    def _call(self, direction, entry, exit_):
        from validation.outcome_checker import _determine_outcome
        return _determine_outcome(direction, entry, exit_)

    # Correct calls
    def test_bullish_correct_on_up_move(self):
        outcome, pct = self._call("bullish", 100.0, 102.0)
        assert outcome == "CORRECT"
        assert pytest.approx(pct, rel=1e-4) == 2.0

    def test_bearish_correct_on_down_move(self):
        outcome, pct = self._call("bearish", 100.0, 97.0)
        assert outcome == "CORRECT"
        assert pytest.approx(pct, rel=1e-4) == -3.0

    # Incorrect calls
    def test_bullish_incorrect_on_down_move(self):
        outcome, _ = self._call("bullish", 100.0, 97.0)
        assert outcome == "INCORRECT"

    def test_bearish_incorrect_on_up_move(self):
        outcome, _ = self._call("bearish", 100.0, 103.0)
        assert outcome == "INCORRECT"

    # Neutral threshold (±0.5%)
    def test_small_up_move_returns_neutral(self):
        """+0.3% is below the ±0.5% threshold — call it NEUTRAL."""
        outcome, _ = self._call("bullish", 100.0, 100.3)
        assert outcome == "NEUTRAL"

    def test_small_down_move_returns_neutral(self):
        outcome, _ = self._call("bearish", 100.0, 99.8)
        assert outcome == "NEUTRAL"

    def test_exactly_at_threshold_returns_neutral(self):
        """Exactly ±0.5% is not strictly greater/less — stays NEUTRAL."""
        outcome, _ = self._call("bullish", 100.0, 100.5)
        assert outcome == "NEUTRAL"

    def test_just_above_threshold_is_correct(self):
        outcome, _ = self._call("bullish", 100.0, 100.51)
        assert outcome == "CORRECT"

    # Neutral direction
    def test_neutral_direction_always_neutral(self):
        outcome, _ = self._call("neutral", 100.0, 110.0)
        assert outcome == "NEUTRAL"

    def test_neutral_direction_on_big_loss(self):
        outcome, _ = self._call("neutral", 100.0, 80.0)
        assert outcome == "NEUTRAL"

    # Aliases
    def test_buy_alias_works(self):
        outcome, _ = self._call("buy", 100.0, 103.0)
        assert outcome == "CORRECT"

    def test_sell_alias_works(self):
        outcome, _ = self._call("sell", 100.0, 96.0)
        assert outcome == "CORRECT"

    def test_up_alias_works(self):
        outcome, _ = self._call("up", 100.0, 101.0)
        assert outcome == "CORRECT"

    def test_down_alias_works(self):
        outcome, _ = self._call("down", 100.0, 98.0)
        assert outcome == "CORRECT"

    # Case insensitivity
    def test_direction_case_insensitive(self):
        outcome, _ = self._call("BULLISH", 100.0, 103.0)
        assert outcome == "CORRECT"

    # Change_pct sign
    def test_change_pct_negative_on_down_move(self):
        _, pct = self._call("bullish", 100.0, 95.0)
        assert pct < 0

    def test_change_pct_zero_on_flat(self):
        _, pct = self._call("bullish", 100.0, 100.0)
        assert pct == pytest.approx(0.0)


# ── _parse_timestamp (pure) ────────────────────────────────────────────────────

class TestParseTimestamp:
    def _parse(self, s):
        from validation.outcome_checker import _parse_timestamp
        return _parse_timestamp(s)

    def test_utc_iso_string(self):
        dt = self._parse("2026-04-15T10:30:00+00:00")
        assert dt.tzinfo is not None
        assert dt.hour == 10

    def test_z_suffix(self):
        dt = self._parse("2026-04-15T10:30:00Z")
        assert dt.tzinfo is not None

    def test_naive_string_gets_utc(self):
        dt = self._parse("2026-04-15T10:30:00")
        assert dt.tzinfo == timezone.utc

    def test_result_is_utc(self):
        dt = self._parse("2026-04-15T10:30:00+10:00")
        assert dt.utcoffset().total_seconds() == 0


# ── _next_market_open (pure) ───────────────────────────────────────────────────

class TestNextMarketOpen:
    def _call(self, dt):
        from validation.outcome_checker import _next_market_open
        return _next_market_open(dt)

    def test_weekend_advances_to_monday(self):
        """Saturday UTC → should land on Monday."""
        saturday = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)  # Saturday
        result = self._call(saturday)
        sydney_result = result.astimezone(_SYDNEY)
        assert sydney_result.weekday() < 5  # Mon–Fri

    def test_after_close_advances_to_next_day(self):
        """17:00 AEST (after 16:00 close) → next trading day at 10:00."""
        after_close = datetime(2026, 4, 14, 7, 0, tzinfo=timezone.utc)  # 17:00 AEST Tue
        result = self._call(after_close)
        sydney_result = result.astimezone(_SYDNEY)
        assert sydney_result.hour == 10

    def test_result_is_utc(self):
        dt = datetime(2026, 4, 14, 2, 0, tzinfo=timezone.utc)
        result = self._call(dt)
        assert result.utcoffset().total_seconds() == 0


# ── get_pending_validations (DB) ───────────────────────────────────────────────

class TestGetPendingValidations:
    """Requires isolated_db to patch database.DB_PATH."""

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from validation.outcome_checker import get_pending_validations
        result = await get_pending_validations()
        assert result == []

    @pytest.mark.asyncio
    async def test_old_prediction_is_returned(self, isolated_db, monkeypatch, sample_prediction):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        await insert_prediction(isolated_db, sample_prediction)

        from validation.outcome_checker import get_pending_validations
        result = await get_pending_validations()
        assert len(result) == 1
        assert result[0]["ticker"] == "BHP.AX"

    @pytest.mark.asyncio
    async def test_recent_prediction_excluded(self, isolated_db, monkeypatch):
        """A prediction from 1 hour ago is too new for 24h validation."""
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        recent = {
            "id": "recent-001",
            "ticker": "RIO.AX",
            "predicted_direction": "bearish",
            "confidence": 0.65,
            "predicted_at": datetime.now(timezone.utc).isoformat(),
            "bhp_price_at_prediction": 120.0,
        }
        await insert_prediction(isolated_db, recent)

        from validation.outcome_checker import get_pending_validations
        result = await get_pending_validations()
        assert result == []

    @pytest.mark.asyncio
    async def test_neutral_direction_excluded(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        neutral = {
            "id": "neutral-001",
            "ticker": "WDS.AX",
            "predicted_direction": "neutral",
            "confidence": 0.55,
            "predicted_at": "2026-04-15T02:00:00+00:00",
            "bhp_price_at_prediction": 30.0,
        }
        await insert_prediction(isolated_db, neutral)

        from validation.outcome_checker import get_pending_validations
        result = await get_pending_validations()
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_entry_price_excluded(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite
        async with aiosqlite.connect(isolated_db) as db:
            await db.execute(
                """INSERT INTO prediction_log
                   (id, ticker, predicted_direction, confidence, predicted_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("no-price-001", "FMG.AX", "bullish", 0.70,
                 "2026-04-15T02:00:00+00:00",
                 datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

        from validation.outcome_checker import get_pending_validations
        result = await get_pending_validations()
        assert result == []


# ── fetch_price_at_time (mocked network) ──────────────────────────────────────

class TestFetchPriceAtTime:

    @pytest.mark.asyncio
    async def test_returns_price_from_history(self, mock_yfinance):
        from validation.outcome_checker import fetch_price_at_time
        target = datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc)
        price = await fetch_price_at_time("BHP.AX", target)
        assert price == pytest.approx(46.10)

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_history(self):
        import pandas as pd
        from unittest.mock import MagicMock, patch

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from validation.outcome_checker import fetch_price_at_time
            target = datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc)
            price = await fetch_price_at_time("BHP.AX", target)
            assert price is None

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, mock_yfinance_rate_limited):
        """Should succeed on the second attempt after a rate-limit error."""
        from validation.outcome_checker import fetch_price_at_time
        target = datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc)
        price = await fetch_price_at_time("BHP.AX", target)
        # call_count["n"] should be 2 (failed once, succeeded once)
        assert mock_yfinance_rate_limited["n"] == 2
        assert price == pytest.approx(46.10)
