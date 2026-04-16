"""Circuit breaker — protects LLM providers from cascade failures.

Three states:
  CLOSED    — normal operation, all requests pass through
  OPEN      — provider is failing; requests are rejected immediately
  HALF_OPEN — one test request is allowed through to probe recovery

Usage::

    cb = CircuitBreaker("groq-70b", failure_threshold=3, recovery_timeout=60)
    if cb.can_proceed():
        try:
            result = await call_provider()
            cb.record_success()
        except Exception as exc:
            cb.record_failure()
            raise
    else:
        raise ProviderUnavailableError("groq-70b circuit is OPEN")
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe async circuit breaker for a single LLM provider."""

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    async def can_proceed(self) -> bool:
        """Return True if a request should be allowed through."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition(CircuitState.HALF_OPEN)
                    return True
                return False
            # HALF_OPEN — one probe allowed; subsequent calls blocked until resolved
            return True

    async def record_success(self) -> None:
        """Call after a successful provider response."""
        async with self._lock:
            if self._state != CircuitState.CLOSED:
                self._transition(CircuitState.CLOSED)
            self._failure_count = 0

    async def record_failure(self) -> None:
        """Call after a provider failure (timeout, error, rate-limit)."""
        async with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — go back to OPEN and reset the clock
                self._opened_at = time.monotonic()
                self._transition(CircuitState.OPEN)
            elif self._failure_count >= self.failure_threshold:
                self._opened_at = time.monotonic()
                self._transition(CircuitState.OPEN)

    async def reset(self) -> None:
        """Manually reset the breaker to CLOSED (e.g., after provider restart)."""
        async with self._lock:
            self._failure_count = 0
            self._opened_at = None
            self._transition(CircuitState.CLOSED)

    def get_status(self) -> dict:
        return {
            "provider": self.provider_name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "seconds_until_retry": self._seconds_until_retry(),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _should_attempt_reset(self) -> bool:
        if self._opened_at is None:
            return True
        return (time.monotonic() - self._opened_at) >= self.recovery_timeout

    def _seconds_until_retry(self) -> Optional[float]:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return None
        elapsed = time.monotonic() - self._opened_at
        remaining = self.recovery_timeout - elapsed
        return max(0.0, round(remaining, 1))

    def _transition(self, new_state: CircuitState) -> None:
        if new_state == self._state:
            return
        logger.warning(
            "[CircuitBreaker] %s: %s → %s (failures=%d)",
            self.provider_name,
            self._state.value,
            new_state.value,
            self._failure_count,
        )
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._opened_at = None
