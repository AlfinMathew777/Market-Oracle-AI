"""
E2E — Queue system contract tests.

Tests the SimulationQueue API surface in isolation.
Redis connectivity is optional — tests skip cleanly if Redis is unavailable.

Verifies:
  - get_stats() always returns a dict with 'queued' and 'processing' int fields
  - enqueue() returns the simulation_id it was given (not a new one)
  - get_result() returns None for unknown IDs
  - fail() stores an error record retrievable via get_result()
  - complete() stores a result retrievable via get_result()
  - Queue gracefully degrades when Redis is unreachable (no crash)
"""

import asyncio

import pytest

from job_queue.simulation_queue import SimulationQueue


def _skip_if_no_redis(exc: Exception) -> None:
    """Convert a Redis connection error into a pytest.skip."""
    msg = str(exc).lower()
    if any(k in msg for k in ("connection", "refused", "redis", "timeout", "unavailable")):
        pytest.skip(f"Redis not available: {exc}")
    raise exc


class _FakeRedisClient:
    """Minimal in-memory async stand-in for the Redis commands SimulationQueue uses.

    Lets result-contract tests exercise the real fail()/complete()/get_result()
    serialization and key-prefix logic without a live Redis server.
    """

    def __init__(self) -> None:
        self._store: dict = {}

    async def set(self, key: str, value: str, ex: int = None) -> None:
        self._store[key] = value

    async def get(self, key: str):
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


def _queue_with_fake_redis() -> SimulationQueue:
    """SimulationQueue wired to an in-memory fake client (connect() sees it as open)."""
    q = SimulationQueue()
    q._client = _FakeRedisClient()
    return q


@pytest.mark.e2e
class TestQueueStatsContract:
    """get_stats() must always return a consistent shape."""

    def test_stats_without_redis_returns_disabled(self):
        """When Redis is unreachable, get_stats() returns enabled=False (no crash)."""

        async def _run():
            q = SimulationQueue(redis_url="redis://localhost:19999")  # unreachable port
            return await q.get_stats()

        stats = asyncio.get_event_loop().run_until_complete(_run())
        assert isinstance(stats, dict)
        assert "enabled" in stats or "queued" in stats

    def test_stats_shape_when_connected(self):
        """When Redis is reachable, stats has queued + processing as ints."""

        async def _run():
            q = SimulationQueue()
            try:
                return await q.get_stats()
            except Exception as exc:
                _skip_if_no_redis(exc)

        stats = asyncio.get_event_loop().run_until_complete(_run())
        assert "queued" in stats
        assert "processing" in stats
        assert isinstance(stats["queued"], int)
        assert isinstance(stats["processing"], int)


@pytest.mark.e2e
class TestQueueEnqueueContract:
    """enqueue() must return the provided simulation_id."""

    def test_enqueue_returns_provided_id(self):
        """The returned ID matches what was passed in."""

        async def _run():
            q = SimulationQueue()
            try:
                sim_id = "sim_contract_test_abc123"
                returned = await q.enqueue(
                    simulation_id=sim_id,
                    ticker="BHP.AX",
                    event_data={"event_type": "Economic", "country": "China"},
                    affected_tickers=["BHP.AX"],
                    priority=5,
                )
                return returned
            except Exception as exc:
                _skip_if_no_redis(exc)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result == "sim_contract_test_abc123"

    def test_enqueue_raises_when_redis_down(self):
        """RuntimeError raised (not silent fail) when Redis is unreachable."""

        async def _run():
            q = SimulationQueue(redis_url="redis://localhost:19999")
            return await q.enqueue(
                simulation_id="sim_test_fail",
                ticker="BHP.AX",
                event_data={},
            )

        with pytest.raises(RuntimeError, match="Redis not available"):
            asyncio.get_event_loop().run_until_complete(_run())


@pytest.mark.e2e
class TestQueueResultContract:
    """get_result() / complete() / fail() must store and retrieve correctly."""

    def test_get_result_unknown_id_returns_none(self):
        """Unknown simulation_id returns None without crashing."""

        async def _run():
            q = SimulationQueue()
            try:
                return await q.get_result("sim_definitely_does_not_exist_xyzabc")
            except Exception as exc:
                _skip_if_no_redis(exc)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is None

    def test_fail_then_get_result_returns_failed(self):
        """After fail(), get_result() returns status=failed with error field."""

        async def _run():
            q = _queue_with_fake_redis()
            sim_id = "sim_contract_fail_test_001"
            await q.fail(sim_id, "integration test error")
            return await q.get_result(sim_id)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is not None
        assert result.get("status") == "failed"
        assert "error" in result

    def test_complete_then_get_result_returns_completed(self):
        """After complete(), get_result() returns status=completed with result field."""

        async def _run():
            q = _queue_with_fake_redis()
            sim_id = "sim_contract_complete_test_001"
            payload = {
                "status": "completed",
                "simulation_id": sim_id,
                "prediction": {"direction": "UP", "confidence": 0.70},
                "execution_time": 12.5,
            }
            await q.complete(sim_id, payload)
            return await q.get_result(sim_id)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is not None
        assert result.get("status") == "completed"
        assert "result" in result or "prediction" in str(result)
