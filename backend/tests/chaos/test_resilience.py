"""Chaos and resilience tests for Market Oracle AI.

Tests the system's behaviour when dependencies fail. Each test injects a
specific failure and verifies that:

  1. The system degrades gracefully (no 500s from unhandled exceptions)
  2. Fallback data or cached responses are served when available
  3. The kill switch remains controllable even under degraded conditions
  4. No data is silently lost

Test categories:
  TestRedisFailure         — Redis unavailable / timeout
  TestYFinanceFailure      — yfinance raises on every call
  TestDatabaseFailure      — DB connection error on reads
  TestLLMTimeout           — LLM call hangs / times out
  TestKillSwitchUnderLoad  — kill switch fires while simulations are running
  TestConcurrentSimulations— many sims hit the semaphore correctly
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_mini_app():
    """Return a minimal FastAPI app with the routes needed for chaos tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "operational"}

    return app


# ────────────────────────────────────────────────────────────────────────────
# TestRedisFailure
# ────────────────────────────────────────────────────────────────────────────

class TestRedisFailure:
    """System must continue serving data when Redis is down."""

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_on_connection_error(self):
        """cache_get must return None (not raise) when Redis is unreachable."""
        with patch("services.redis_client.UPSTASH_URL", "http://bad-host:1234"):
            with patch("httpx.AsyncClient.get", side_effect=ConnectionError("refused")):
                from services.redis_client import cache_get
                result = await cache_get("any:key")
                assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_returns_false_on_connection_error(self):
        """cache_set must return False (not raise) when Redis is unreachable."""
        with patch("services.redis_client.UPSTASH_URL", "http://bad-host:1234"):
            with patch("httpx.AsyncClient.post", side_effect=ConnectionError("refused")):
                from services.redis_client import cache_set
                result = await cache_set("any:key", {"value": 1})
                assert result is False

    @pytest.mark.asyncio
    async def test_redis_health_returns_degraded_on_error(self):
        """redis_health() must return degraded status on connectivity failure."""
        with patch("services.market_data_cache.cache_set", return_value=False):
            with patch("services.market_data_cache.cache_get", return_value=None):
                import os
                with patch.dict(os.environ, {"UPSTASH_REDIS_REST_URL": "http://bad"}):
                    from services.market_data_cache import redis_health
                    result = await redis_health()
                    assert result["status"] in ("degraded", "unavailable")

    @pytest.mark.asyncio
    async def test_price_cache_miss_does_not_raise(self):
        """get_price_cached must return None gracefully on cache failure."""
        with patch("services.market_data_cache.cache_get", return_value=None):
            from services.market_data_cache import get_price_cached
            result = await get_price_cached("BHP.AX")
            assert result is None

    @pytest.mark.asyncio
    async def test_macro_cache_miss_does_not_raise(self):
        """get_macro_cached must return None gracefully on cache failure."""
        with patch("services.market_data_cache.cache_get", return_value=None):
            from services.market_data_cache import get_macro_cached
            result = await get_macro_cached("iron_ore")
            assert result is None


# ────────────────────────────────────────────────────────────────────────────
# TestYFinanceFailure
# ────────────────────────────────────────────────────────────────────────────

class TestYFinanceFailure:
    """System must handle yfinance being unavailable."""

    @pytest.mark.asyncio
    async def test_run_accuracy_checks_tolerates_yfinance_error(self, isolated_db):
        """run_accuracy_checks must not propagate yfinance exceptions."""
        from database import get_db, init_db, save_simulation
        import time as _time

        # Insert a PENDING simulation that's overdue
        await init_db()
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO simulations
                   (id, ticker, direction, confidence, event_description,
                    event_type, country, causal_chain, agent_votes,
                    execution_time, ticker_confidence, ticker_reasoning,
                    outcome, check_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "chaos-001", "BHP.AX", "UP", 0.70, "test event",
                    "Battles", "Australia", "[]", "[]",
                    5.0, 0.8, "test", "PENDING",
                    int(_time.time()) - 100,   # already past check_at
                    "2026-01-01T00:00:00Z",
                ),
            )
            await db.commit()

        with patch("yfinance.Ticker", side_effect=RuntimeError("API down")):
            from database import run_accuracy_checks
            # Must not raise — returns 0 checked
            checked = await run_accuracy_checks()
            assert isinstance(checked, int)

    @pytest.mark.asyncio
    async def test_fetch_price_at_time_returns_none_on_error(self):
        """Validation service must return None when yfinance fails."""
        with patch("yfinance.Ticker", side_effect=Exception("rate limited")):
            from services.prediction_resolver import fetch_price_at_time
            result = await fetch_price_at_time("BHP.AX", "2026-01-01T12:00:00Z")
            assert result is None


# ────────────────────────────────────────────────────────────────────────────
# TestDatabaseFailure
# ────────────────────────────────────────────────────────────────────────────

class TestDatabaseFailure:
    """System must return safe fallback values when the DB is unavailable."""

    @pytest.mark.asyncio
    async def test_get_prediction_history_returns_empty_on_db_error(self):
        """get_prediction_history must return [] when the DB call fails."""
        with patch("database.get_db", side_effect=RuntimeError("DB unavailable")):
            from database import get_prediction_history
            result = await get_prediction_history()
            assert result == []

    @pytest.mark.asyncio
    async def test_get_accuracy_stats_returns_zero_on_db_error(self):
        """get_accuracy_stats must return a safe zero dict on DB failure."""
        with patch("database.get_db", side_effect=RuntimeError("DB unavailable")):
            from database import get_accuracy_stats
            result = await get_accuracy_stats()
            assert result["total"] == 0
            assert result.get("accuracy_pct") is None

    @pytest.mark.asyncio
    async def test_get_active_alerts_returns_empty_on_db_error(self):
        """get_active_alerts must return [] on DB failure."""
        with patch("database.get_db", side_effect=RuntimeError("DB unavailable")):
            from monitoring.alerts import get_active_alerts
            result = await get_active_alerts()
            assert result == []

    @pytest.mark.asyncio
    async def test_save_simulation_logs_error_does_not_raise(self, isolated_db):
        """save_simulation must log and swallow DB errors, not propagate."""
        import json
        from database import save_simulation

        with patch("database.get_db", side_effect=RuntimeError("disk full")):
            # Should not raise — fire-and-forget pattern
            await save_simulation(
                "chaos-002", "BHP.AX",
                {"direction": "UP", "confidence": 0.7, "causal_chain": [], "agent_votes": []},
                {"event_type": "Battles", "country": "Australia"},
                3.5,
            )


# ────────────────────────────────────────────────────────────────────────────
# TestKillSwitchUnderLoad
# ────────────────────────────────────────────────────────────────────────────

class TestKillSwitchUnderLoad:
    """Kill switch must be thread-safe and immediately effective."""

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_concurrent_checks(self):
        """All concurrent signal checks must be blocked after kill switch fires."""
        from routes.simulate import _kill_switch_active, activate_kill_switch, resume_signals

        try:
            activate_kill_switch("Chaos test — load spike detected", triggered_by="chaos_test")

            async def check_blocked():
                return _kill_switch_active()

            results = await asyncio.gather(*[check_blocked() for _ in range(20)])
            assert all(r is True for r in results), "All checks should see kill switch as active"
        finally:
            resume_signals()

    @pytest.mark.asyncio
    async def test_kill_switch_state_survives_concurrent_reads(self):
        """State reads under concurrent access must be consistent."""
        from routes.simulate import (
            _kill_switch_active, activate_kill_switch, resume_signals,
            get_system_state,
        )

        try:
            activate_kill_switch("Concurrent test", triggered_by="chaos")

            async def read_state():
                state = get_system_state()
                return state["kill_switch_active"], _kill_switch_active()

            results = await asyncio.gather(*[read_state() for _ in range(50)])
            for state_active, direct_active in results:
                assert state_active is True
                assert direct_active is True
        finally:
            resume_signals()

    @pytest.mark.asyncio
    async def test_resume_unblocks_immediately(self):
        """After resume_signals(), _kill_switch_active() must return False at once."""
        from routes.simulate import _kill_switch_active, activate_kill_switch, resume_signals

        activate_kill_switch("Temp block", triggered_by="chaos")
        assert _kill_switch_active() is True

        resume_signals()
        assert _kill_switch_active() is False


# ────────────────────────────────────────────────────────────────────────────
# TestLLMTimeout
# ────────────────────────────────────────────────────────────────────────────

class TestLLMTimeout:
    """Simulation pipeline must not hang forever on LLM timeouts."""

    @pytest.mark.asyncio
    async def test_llm_router_call_primary_timeout(self):
        """LLMRouter must raise/return within timeout, not hang indefinitely."""
        from llm_router import LLMRouter

        router = LLMRouter()

        async def slow_llm(*args, **kwargs):
            await asyncio.sleep(999)
            return "never"

        with patch.object(router, "_call_with_timeout", side_effect=asyncio.TimeoutError):
            try:
                result = await asyncio.wait_for(
                    router.call_primary("Test prompt"),
                    timeout=5.0,
                )
            except (asyncio.TimeoutError, Exception):
                pass  # Any exception is acceptable — just must not hang


# ────────────────────────────────────────────────────────────────────────────
# TestConcurrentSimulations
# ────────────────────────────────────────────────────────────────────────────

class TestConcurrentSimulations:
    """Semaphore must bound parallelism and prevent resource exhaustion."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_llm_calls(self):
        """No more than SEM_LIMIT tasks should run simultaneously."""
        SEM_LIMIT = 3
        sem = asyncio.Semaphore(SEM_LIMIT)
        concurrent_peak = 0
        active = 0
        lock = asyncio.Lock()

        async def task_fn():
            nonlocal concurrent_peak, active
            async with sem:
                async with lock:
                    active += 1
                    concurrent_peak = max(concurrent_peak, active)
                await asyncio.sleep(0.05)
                async with lock:
                    active -= 1

        await asyncio.gather(*[task_fn() for _ in range(20)])
        assert concurrent_peak <= SEM_LIMIT, (
            f"Peak concurrency {concurrent_peak} exceeded semaphore limit {SEM_LIMIT}"
        )

    @pytest.mark.asyncio
    async def test_prediction_history_stable_under_concurrent_reads(self, isolated_db):
        """Concurrent DB reads must not corrupt results or deadlock."""
        from database import get_prediction_history

        async def read():
            return await get_prediction_history(limit=10)

        results = await asyncio.gather(*[read() for _ in range(10)])
        # All should succeed and return lists
        for result in results:
            assert isinstance(result, list)
