"""Health monitor — tracks agent heartbeats and detects stuck / error-loop agents.

Agents call heartbeat() at the start of execution and record_success/record_error
on completion.  The orchestrator checks get_unhealthy_agents() before dispatching
to skip agents that are cycling in error loops or have gone silent.

Usage::

    monitor = HealthMonitor()
    monitor.heartbeat("macro_bull")
    try:
        result = await run_macro_bull(...)
        monitor.record_success("macro_bull")
    except Exception as exc:
        monitor.record_error("macro_bull", exc)
        raise
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

AgentStatus = Literal["healthy", "stuck", "error_loop", "unknown"]
Recommendation = Literal["continue", "restart", "skip"]


@dataclass
class AgentHealth:
    agent_id: str
    last_heartbeat: float
    error_count: int
    status: AgentStatus
    recommendation: Recommendation
    last_error: Optional[str] = None


@dataclass
class _AgentRecord:
    """Internal mutable state per agent — not exposed publicly."""
    last_heartbeat: float = field(default_factory=time.monotonic)
    consecutive_errors: int = 0
    last_error: Optional[str] = None


class HealthMonitor:
    """Tracks liveness and error counts for every named agent."""

    def __init__(
        self,
        stuck_threshold: float = 60.0,
        error_loop_threshold: int = 3,
    ) -> None:
        self.stuck_threshold = stuck_threshold
        self.error_loop_threshold = error_loop_threshold
        self._records: Dict[str, _AgentRecord] = {}

    # ── Agent-facing API ──────────────────────────────────────────────────────

    def heartbeat(self, agent_id: str) -> None:
        """Called by an agent at the start of its execution to signal liveness."""
        record = self._get_or_create(agent_id)
        record.last_heartbeat = time.monotonic()

    def record_success(self, agent_id: str) -> None:
        """Call after a successful agent completion."""
        record = self._get_or_create(agent_id)
        record.consecutive_errors = 0
        record.last_error = None

    def record_error(self, agent_id: str, error: Exception) -> None:
        """Call after an agent failure."""
        record = self._get_or_create(agent_id)
        record.consecutive_errors += 1
        record.last_error = str(error)
        if record.consecutive_errors >= self.error_loop_threshold:
            logger.warning(
                "[HealthMonitor] %s entered error loop (%d consecutive failures): %s",
                agent_id,
                record.consecutive_errors,
                record.last_error,
            )

    def reset_agent(self, agent_id: str) -> None:
        """Clear error counts and reset heartbeat (e.g., after manual restart)."""
        self._records[agent_id] = _AgentRecord()

    # ── Query API ─────────────────────────────────────────────────────────────

    def is_stuck(self, agent_id: str) -> bool:
        record = self._records.get(agent_id)
        if record is None:
            return False
        elapsed = time.monotonic() - record.last_heartbeat
        return elapsed >= self.stuck_threshold

    def is_error_loop(self, agent_id: str) -> bool:
        record = self._records.get(agent_id)
        if record is None:
            return False
        return record.consecutive_errors >= self.error_loop_threshold

    def get_health_report(self) -> Dict[str, AgentHealth]:
        return {agent_id: self._assess(agent_id) for agent_id in self._records}

    def get_unhealthy_agents(self) -> List[str]:
        return [
            agent_id
            for agent_id, health in self.get_health_report().items()
            if health.recommendation != "continue"
        ]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_or_create(self, agent_id: str) -> _AgentRecord:
        if agent_id not in self._records:
            self._records[agent_id] = _AgentRecord()
        return self._records[agent_id]

    def _assess(self, agent_id: str) -> AgentHealth:
        record = self._records[agent_id]
        elapsed = time.monotonic() - record.last_heartbeat

        if record.consecutive_errors >= self.error_loop_threshold:
            status: AgentStatus = "error_loop"
            recommendation: Recommendation = "skip"
        elif elapsed >= self.stuck_threshold:
            status = "stuck"
            recommendation = "restart"
        elif record.consecutive_errors > 0:
            status = "healthy"  # errors but below threshold — still healthy
            recommendation = "continue"
        else:
            status = "healthy"
            recommendation = "continue"

        return AgentHealth(
            agent_id=agent_id,
            last_heartbeat=record.last_heartbeat,
            error_count=record.consecutive_errors,
            status=status,
            recommendation=recommendation,
            last_error=record.last_error,
        )
