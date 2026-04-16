"""Tests for infrastructure.circuit_breaker."""

import asyncio
import time

import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.circuit_breaker import CircuitBreaker, CircuitState


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── State transitions ─────────────────────────────────────────────────────────

class TestInitialState:
    def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_can_proceed_when_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert run(cb.can_proceed()) is True


class TestOpenTransition:
    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            run(cb.record_failure())
        assert cb.state == CircuitState.OPEN

    def test_blocked_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=9999)
        run(cb.record_failure())
        run(cb.record_failure())
        assert run(cb.can_proceed()) is False

    def test_does_not_open_before_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        run(cb.record_failure())
        run(cb.record_failure())
        assert cb.state == CircuitState.CLOSED


class TestHalfOpenTransition:
    def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        run(cb.record_failure())
        assert cb.state == CircuitState.OPEN
        time.sleep(0.1)
        allowed = run(cb.can_proceed())
        assert allowed is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success_from_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        run(cb.record_failure())
        time.sleep(0.1)
        run(cb.can_proceed())   # transitions to HALF_OPEN
        run(cb.record_success())
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_from_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        run(cb.record_failure())
        time.sleep(0.1)
        run(cb.can_proceed())   # transitions to HALF_OPEN
        run(cb.record_failure())
        assert cb.state == CircuitState.OPEN


class TestReset:
    def test_manual_reset_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        run(cb.record_failure())
        assert cb.state == CircuitState.OPEN
        run(cb.reset())
        assert cb.state == CircuitState.CLOSED
        assert run(cb.can_proceed()) is True

    def test_reset_clears_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        run(cb.record_failure())
        run(cb.record_failure())
        run(cb.reset())
        assert cb.get_status()["failure_count"] == 0


class TestSuccessResetsCount:
    def test_success_clears_failures(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        run(cb.record_failure())
        run(cb.record_failure())
        run(cb.record_success())
        assert cb.get_status()["failure_count"] == 0
        assert cb.state == CircuitState.CLOSED


class TestGetStatus:
    def test_status_fields(self):
        cb = CircuitBreaker("prov", failure_threshold=3)
        status = cb.get_status()
        assert status["provider"] == "prov"
        assert status["state"] == "CLOSED"
        assert status["failure_count"] == 0
        assert status["seconds_until_retry"] is None

    def test_seconds_until_retry_set_when_open(self):
        cb = CircuitBreaker("prov", failure_threshold=1, recovery_timeout=60.0)
        run(cb.record_failure())
        status = cb.get_status()
        assert status["seconds_until_retry"] is not None
        assert 0 < status["seconds_until_retry"] <= 60.0


class TestThreadSafety:
    """Concurrent record_failure calls should not corrupt state."""

    def test_concurrent_failures(self):
        async def _run():
            cb = CircuitBreaker("test", failure_threshold=5)
            await asyncio.gather(*[cb.record_failure() for _ in range(10)])
            assert cb._failure_count <= 10  # no race on the counter

        asyncio.get_event_loop().run_until_complete(_run())
