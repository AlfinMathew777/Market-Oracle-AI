"""Tests for orchestration.orchestrator — state machine transitions and timeout handling.

Uses a mock UnifiedInferenceClient so no real LLM calls are made.
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from infrastructure.health_monitor import HealthMonitor
from infrastructure.inference_client import CompletionResult, UnifiedInferenceClient
from orchestration.orchestrator import Orchestrator, OrchestratorState, PredictionResult
from orchestration.task_graph import TaskGraph


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _mock_client(content: str = '{"direction":"bullish","confidence":0.6,"causal_chain":["a","b"]}') -> UnifiedInferenceClient:
    client = MagicMock(spec=UnifiedInferenceClient)
    client.complete = AsyncMock(return_value=CompletionResult(success=True, content=content))
    return client


def _make_orchestrator(client=None, graph=None) -> Orchestrator:
    client = client or _mock_client()
    monitor = HealthMonitor()
    graph = graph or TaskGraph()
    return Orchestrator(client, graph, monitor)


# ── run() — happy path ────────────────────────────────────────────────────────

class TestRunHappyPath:
    def test_returns_prediction_result(self):
        orch = _make_orchestrator()
        result = asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert isinstance(result, PredictionResult)
        assert result.ticker == "BHP"

    def test_direction_extracted_from_llm(self):
        orch = _make_orchestrator()
        result = asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert result.direction in ("bullish", "bearish", "neutral")

    def test_confidence_capped_at_85_pct(self):
        client = _mock_client('{"direction":"bullish","confidence":0.99}')
        orch = _make_orchestrator(client=client)
        result = asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert result.confidence <= 0.85

    def test_state_ends_complete(self):
        orch = _make_orchestrator()
        asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert orch.current_state == OrchestratorState.COMPLETE

    def test_state_trace_recorded(self):
        orch = _make_orchestrator()
        result = asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert len(result.state_trace) > 0

    def test_execution_time_non_negative(self):
        orch = _make_orchestrator()
        result = asyncio.get_event_loop().run_until_complete(orch.run("BHP"))
        assert result.execution_time_s >= 0


# ── run() — failure path ──────────────────────────────────────────────────────

class TestRunFailurePath:
    def test_partial_result_on_llm_failure(self):
        client = MagicMock(spec=UnifiedInferenceClient)
        client.complete = AsyncMock(return_value=CompletionResult(success=False, content="", error="no providers"))
        orch = _make_orchestrator(client=client)
        result = asyncio.get_event_loop().run_until_complete(orch.run("RIO"))
        assert isinstance(result, PredictionResult)
        # May be partial with errors
        assert result.ticker == "RIO"

    def test_partial_flag_set_on_failed_state(self):
        """Force FAILED state by injecting a graph with a cycle."""
        g = TaskGraph()
        g.add_task("X", "x", depends_on=["Y"])
        g.add_task("Y", "y", depends_on=["X"])
        orch = _make_orchestrator(graph=g)
        result = asyncio.get_event_loop().run_until_complete(orch.run("WDS"))
        assert result.partial is True or result.error is not None


# ── tick() ────────────────────────────────────────────────────────────────────

class TestTick:
    def test_classify_transitions_to_plan(self):
        async def _run():
            orch = _make_orchestrator()
            orch._state = OrchestratorState.CLASSIFY
            orch._context = {"ticker": "BHP", "agents_results": {}, "errors": [], "state_trace": []}
            new_state = await orch.tick()
            return new_state
        new_state = asyncio.get_event_loop().run_until_complete(_run())
        assert new_state == OrchestratorState.PLAN

    def test_plan_transitions_to_execute(self):
        async def _run():
            orch = _make_orchestrator()
            orch._state = OrchestratorState.PLAN
            orch._context = {"ticker": "BHP", "agents_results": {}, "errors": [], "state_trace": []}
            return await orch.tick()
        new_state = asyncio.get_event_loop().run_until_complete(_run())
        assert new_state == OrchestratorState.EXECUTE


# ── get_status() ──────────────────────────────────────────────────────────────

class TestGetStatus:
    def test_status_fields(self):
        orch = _make_orchestrator()
        orch._start_time = __import__("time").monotonic()
        orch._context = {"ticker": "CBA", "state_trace": []}
        status = orch.get_status()
        assert status["state"] == OrchestratorState.IDLE.value
        assert status["ticker"] == "CBA"
        assert "elapsed_s" in status
        assert "graph_summary" in status


# ── pipeline timeout ──────────────────────────────────────────────────────────

class TestPipelineTimeout:
    def test_timeout_returns_partial_result(self):
        """Patch _PIPELINE_TIMEOUT to 0 to force immediate timeout."""
        import orchestration.orchestrator as orch_module
        original = orch_module._PIPELINE_TIMEOUT
        orch_module._PIPELINE_TIMEOUT = 0.001
        try:
            orch = _make_orchestrator()
            result = asyncio.get_event_loop().run_until_complete(orch.run("FMG"))
            assert isinstance(result, PredictionResult)
            assert result.partial is True or result.error is not None
        finally:
            orch_module._PIPELINE_TIMEOUT = original
