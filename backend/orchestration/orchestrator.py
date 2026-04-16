"""State-machine orchestrator for the Market Oracle prediction pipeline.

States::

    IDLE → CLASSIFY → PLAN → EXECUTE → AGGREGATE → RECONCILE → COMPLETE
                                 ↓                                  ↑
                              FAILED ────────────────────────────────

The orchestrator drives the task graph forward in a tick loop.  Each tick
transitions to the next state based on the result of the current handler.

Usage::

    client   = UnifiedInferenceClient()
    monitor  = HealthMonitor()
    memory   = ErrorMemory()

    async def predict(ticker: str) -> PredictionResult:
        graph = TaskGraph()
        orch  = Orchestrator(client, graph, monitor, memory)
        return await orch.run(ticker)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from infrastructure.health_monitor import HealthMonitor
from infrastructure.inference_client import UnifiedInferenceClient
from orchestration.task_graph import TaskGraph, TaskStatus

logger = logging.getLogger(__name__)

_PIPELINE_TIMEOUT = 120.0   # seconds — whole pipeline budget
_AGENT_TIMEOUT    = 30.0    # seconds — per-agent budget


class OrchestratorState(str, Enum):
    IDLE       = "IDLE"
    CLASSIFY   = "CLASSIFY"
    PLAN       = "PLAN"
    REVIEW     = "REVIEW"
    EXECUTE    = "EXECUTE"
    AGGREGATE  = "AGGREGATE"
    RECONCILE  = "RECONCILE"
    COMPLETE   = "COMPLETE"
    FAILED     = "FAILED"


@dataclass
class PredictionResult:
    ticker: str
    direction: str = "neutral"
    confidence: float = 0.0
    signals: List[Dict[str, Any]] = field(default_factory=list)
    causal_chain: List[str] = field(default_factory=list)
    execution_time_s: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    partial: bool = False
    error: Optional[str] = None
    state_trace: List[str] = field(default_factory=list)


class Orchestrator:
    """Drives the prediction pipeline through its state machine."""

    def __init__(
        self,
        inference_client: UnifiedInferenceClient,
        task_graph: TaskGraph,
        health_monitor: HealthMonitor,
        error_memory: Optional[Any] = None,   # ErrorMemory — optional
    ) -> None:
        self._client  = inference_client
        self._graph   = task_graph
        self._monitor = health_monitor
        self._memory  = error_memory

        self._state: OrchestratorState = OrchestratorState.IDLE
        self._context: Dict[str, Any]  = {}
        self._start_time: float        = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def current_state(self) -> OrchestratorState:
        return self._state

    async def run(self, ticker: str) -> PredictionResult:
        """Execute the full pipeline and return a PredictionResult."""
        self._start_time = time.monotonic()
        self._context = {
            "ticker": ticker,
            "agents_results": {},
            "errors": [],
            "state_trace": [],
        }

        try:
            await asyncio.wait_for(self._run_loop(), timeout=_PIPELINE_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error("[Orchestrator] Pipeline timeout for %s after %.0fs", ticker, _PIPELINE_TIMEOUT)
            self._state = OrchestratorState.FAILED
            self._context["errors"].append(f"Pipeline timeout after {_PIPELINE_TIMEOUT}s")

        return self._build_result(ticker)

    async def tick(self) -> OrchestratorState:
        """Execute one state transition and return the new state."""
        next_state = await self._dispatch()
        self._context["state_trace"].append(next_state.value)
        self._state = next_state
        return self._state

    def get_status(self) -> Dict[str, Any]:
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0
        return {
            "state": self._state.value,
            "ticker": self._context.get("ticker"),
            "elapsed_s": round(elapsed, 1),
            "graph_summary": self._graph.get_summary(),
            "state_trace": self._context.get("state_trace", []),
        }

    # ── State machine loop ────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        self._state = OrchestratorState.CLASSIFY
        terminal = {OrchestratorState.COMPLETE, OrchestratorState.FAILED}
        while self._state not in terminal:
            await self.tick()

    async def _dispatch(self) -> OrchestratorState:
        handlers = {
            OrchestratorState.CLASSIFY:  self._handle_classify,
            OrchestratorState.PLAN:      self._handle_plan,
            OrchestratorState.REVIEW:    self._handle_review,
            OrchestratorState.EXECUTE:   self._handle_execute,
            OrchestratorState.AGGREGATE: self._handle_aggregate,
            OrchestratorState.RECONCILE: self._handle_reconcile,
        }
        handler = handlers.get(self._state)
        if handler is None:
            return OrchestratorState.FAILED
        try:
            return await handler()
        except Exception as exc:
            logger.error("[Orchestrator] Error in state %s: %s", self._state, exc, exc_info=True)
            self._context["errors"].append(str(exc))
            return OrchestratorState.FAILED

    # ── State handlers ────────────────────────────────────────────────────────

    async def _handle_classify(self) -> OrchestratorState:
        ticker = self._context["ticker"]
        logger.info("[Orchestrator] CLASSIFY — ticker=%s", ticker)
        # Determine sector / agent roster. For now all tickers use the default graph.
        self._context["sector"] = "general"
        return OrchestratorState.PLAN

    async def _handle_plan(self) -> OrchestratorState:
        logger.info("[Orchestrator] PLAN — building task graph")
        if not self._graph._nodes:
            self._graph.build_default_graph()
        if self._graph.has_cycle():
            self._context["errors"].append("Task graph contains a cycle")
            return OrchestratorState.FAILED
        return OrchestratorState.EXECUTE

    async def _handle_review(self) -> OrchestratorState:
        # Optional validation step — skip for now
        return OrchestratorState.EXECUTE

    async def _handle_execute(self) -> OrchestratorState:
        logger.info("[Orchestrator] EXECUTE — running ready tasks")
        ready = [
            t for t in self._graph.get_ready_tasks()
            if t.id not in self._monitor.get_unhealthy_agents()
        ]

        if not ready:
            if not self._graph.can_continue():
                return OrchestratorState.AGGREGATE
            return OrchestratorState.EXECUTE   # wait for running tasks

        # Run ready tasks in parallel with per-agent timeout
        await asyncio.gather(*[self._run_agent_task(t) for t in ready])

        if self._graph.can_continue():
            return OrchestratorState.EXECUTE
        return OrchestratorState.AGGREGATE

    async def _handle_aggregate(self) -> OrchestratorState:
        results = self._graph.get_results()
        logger.info("[Orchestrator] AGGREGATE — %d agent results collected", len(results))

        # Collect votes from specialist agents (all tasks except blind_judge/reconciler/final)
        specialist_keys = [k for k in results if k not in ("blind_judge", "reconciler", "final_prediction")]
        votes = [results[k] for k in specialist_keys if isinstance(results[k], dict)]
        self._context["specialist_votes"] = votes

        # Run blind judge to aggregate signals
        judge_result = await self._run_judge(votes)
        self._context["judge_output"] = judge_result
        self._graph.mark_complete("blind_judge", judge_result)
        return OrchestratorState.RECONCILE

    async def _handle_reconcile(self) -> OrchestratorState:
        judge_output = self._context.get("judge_output", {})
        logger.info("[Orchestrator] RECONCILE")

        reconciled = await self._run_reconciler(judge_output)
        self._context["reconciled"] = reconciled
        self._graph.mark_complete("reconciler", reconciled)
        self._graph.mark_complete("final_prediction", reconciled)
        return OrchestratorState.COMPLETE

    # ── Agent runners ─────────────────────────────────────────────────────────

    async def _run_agent_task(self, task: Any) -> None:
        self._graph.mark_running(task.id)
        self._monitor.heartbeat(task.id)

        try:
            system_msg = f"You are the {task.agent_type} for Market Oracle AI. Respond with a JSON vote object."
            user_msg   = (
                f"Ticker: {self._context['ticker']}\n"
                f"Anti-patterns: {self._get_anti_patterns()}\n"
                "Respond with: {{\"verdict\": \"bullish|bearish|neutral\", \"confidence\": \"high|medium|low\", \"reasoning\": \"...\"}}"
            )
            result = await asyncio.wait_for(
                self._client.complete(
                    [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]
                ),
                timeout=_AGENT_TIMEOUT,
            )
            if result.success:
                self._graph.mark_complete(task.id, {"raw": result.content, "agent": task.agent_type})
                self._context["agents_results"][task.id] = result.content
                self._monitor.record_success(task.id)
            else:
                raise RuntimeError(result.error or "Inference failed")
        except Exception as exc:
            self._monitor.record_error(task.id, exc)
            self._graph.mark_failed(task.id, str(exc))

    async def _run_judge(self, votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        votes_summary = "\n".join(str(v.get("raw", v)) for v in votes[:20])
        system_msg = "You are the Blind Judge. Aggregate the specialist signals into a consensus verdict."
        user_msg   = f"Ticker: {self._context['ticker']}\n\nAgent votes:\n{votes_summary}\n\nRespond with JSON: {{\"direction\": \"bullish|bearish|neutral\", \"confidence\": 0.0-1.0, \"key_signals\": [...]}}"

        result = await asyncio.wait_for(
            self._client.complete([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]),
            timeout=_AGENT_TIMEOUT,
        )
        return {"raw": result.content} if result.success else {"direction": "neutral", "confidence": 0.0}

    async def _run_reconciler(self, judge_output: Dict[str, Any]) -> Dict[str, Any]:
        system_msg = "You are the Reconciler. Produce a final structured prediction."
        user_msg   = (
            f"Ticker: {self._context['ticker']}\n"
            f"Judge output: {judge_output.get('raw', '')}\n"
            "Respond with JSON: {\"direction\": \"bullish|bearish|neutral\", \"confidence\": 0.0-1.0, \"causal_chain\": [...]}"
        )
        result = await asyncio.wait_for(
            self._client.complete([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]),
            timeout=_AGENT_TIMEOUT,
        )
        return {"raw": result.content} if result.success else {"direction": "neutral", "confidence": 0.0}

    def _get_anti_patterns(self) -> str:
        if self._memory is None:
            return "none"
        ticker = self._context.get("ticker", "")
        patterns = self._memory.get_anti_patterns(ticker)
        return "; ".join(patterns[:3]) if patterns else "none"

    # ── Result assembly ───────────────────────────────────────────────────────

    def _build_result(self, ticker: str) -> PredictionResult:
        elapsed = round(time.monotonic() - self._start_time, 2)
        reconciled = self._context.get("reconciled", {})
        raw = reconciled.get("raw", "")

        # Attempt JSON parse for structured fields
        direction = "neutral"
        confidence = 0.0
        causal_chain: List[str] = []
        try:
            import json
            parsed = json.loads(raw) if raw.strip().startswith("{") else {}
            direction   = parsed.get("direction", "neutral")
            confidence  = float(parsed.get("confidence", 0.0))
            causal_chain = parsed.get("causal_chain", [])
        except Exception:
            pass

        return PredictionResult(
            ticker=ticker,
            direction=direction,
            confidence=min(confidence, 0.85),
            signals=[],
            causal_chain=causal_chain,
            execution_time_s=elapsed,
            agents_used=list(self._context.get("agents_results", {}).keys()),
            partial=self._state == OrchestratorState.FAILED,
            error="; ".join(self._context.get("errors", [])) or None,
            state_trace=self._context.get("state_trace", []),
        )
