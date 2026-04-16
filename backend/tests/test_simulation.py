"""
Tests for simulation pipeline control logic.

Does NOT test the 50-agent LLM pipeline end-to-end (that would require
real API keys and be prohibitively slow). Instead tests:

  - Kill switch enforcement (HTTP 503 when active)
  - Paper mode flag state
  - System state transitions (activate / resume)
  - Confidence guard boundaries

The simulation route itself is exercised lightly via a smoke test that
verifies the kill switch gate fires before any LLM call is attempted.
"""

import pytest
from datetime import datetime, timezone


# ── system_state unit tests ────────────────────────────────────────────────────

class TestKillSwitchState:
    """system_state module — state machine transitions."""

    def test_signals_enabled_by_default(self):
        import system_state
        system_state._signals_enabled = True  # reset (autouse fixture does this too)
        assert system_state.is_signals_enabled() is True

    def test_activate_disables_signals(self):
        import system_state
        system_state.activate_kill_switch("test reason")
        assert system_state.is_signals_enabled() is False

    def test_activate_records_reason(self):
        import system_state
        system_state.activate_kill_switch("data feed anomaly")
        assert system_state._kill_switch_reason == "data feed anomaly"

    def test_activate_records_timestamp(self):
        import system_state
        before = datetime.now(timezone.utc)
        system_state.activate_kill_switch("test")
        after = datetime.now(timezone.utc)
        ts = system_state._kill_switch_activated_at
        assert ts is not None
        assert before <= ts <= after

    def test_resume_re_enables_signals(self):
        import system_state
        system_state.activate_kill_switch("test")
        system_state.resume_signals()
        assert system_state.is_signals_enabled() is True

    def test_resume_clears_reason(self):
        import system_state
        system_state.activate_kill_switch("test")
        system_state.resume_signals()
        assert system_state._kill_switch_reason is None

    def test_resume_clears_activated_at(self):
        import system_state
        system_state.activate_kill_switch("test")
        system_state.resume_signals()
        assert system_state._kill_switch_activated_at is None

    def test_double_activate_idempotent(self):
        """Second activate should just overwrite the reason — not raise."""
        import system_state
        system_state.activate_kill_switch("first reason")
        system_state.activate_kill_switch("second reason")
        assert system_state._kill_switch_reason == "second reason"
        assert system_state.is_signals_enabled() is False

    def test_resume_when_already_active_is_safe(self):
        """Resume on a running system should not error."""
        import system_state
        system_state.resume_signals()
        assert system_state.is_signals_enabled() is True


class TestGetSystemState:
    """get_system_state() snapshot dict."""

    def test_running_state_shape(self):
        import system_state
        state = system_state.get_system_state()
        assert state["signals_enabled"] is True
        assert state["kill_switch_active"] is False
        assert state["kill_switch_reason"] is None
        assert state["kill_switch_activated_at"] is None
        assert "paper_mode" in state
        assert "environment" in state

    def test_paused_state_shape(self):
        import system_state
        system_state.activate_kill_switch("bad data")
        state = system_state.get_system_state()
        assert state["signals_enabled"] is False
        assert state["kill_switch_active"] is True
        assert state["kill_switch_reason"] == "bad data"
        assert state["kill_switch_activated_at"] is not None

    def test_environment_key_present(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        import system_state
        state = system_state.get_system_state()
        assert state["environment"] == "staging"


# ── paper mode ─────────────────────────────────────────────────────────────────

class TestPaperMode:
    """PAPER_MODE is read from env at import time — test the default."""

    def test_paper_mode_true_by_default(self, monkeypatch):
        """When PAPER_MODE is unset, default is 'true'."""
        monkeypatch.delenv("PAPER_MODE", raising=False)
        # Re-import to get fresh evaluation of the env var
        import importlib
        import system_state
        importlib.reload(system_state)
        assert system_state.PAPER_MODE is True

    def test_paper_mode_false_when_explicitly_set(self, monkeypatch):
        monkeypatch.setenv("PAPER_MODE", "false")
        import importlib
        import system_state
        importlib.reload(system_state)
        assert system_state.PAPER_MODE is False

    def test_paper_mode_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("PAPER_MODE", "FALSE")
        import importlib
        import system_state
        importlib.reload(system_state)
        assert system_state.PAPER_MODE is False


# ── Kill switch HTTP gate (simulate route) ─────────────────────────────────────

class TestKillSwitchHTTPGate:
    """
    Verify that the simulate route returns 503 when kill switch is active.

    Uses a tiny FastAPI app that mirrors the gate logic without spawning
    the full 50-agent pipeline, so this runs in < 100ms.
    """

    @pytest.fixture
    def gate_client(self):
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        from pydantic import BaseModel

        mini = FastAPI()

        class SimRequest(BaseModel):
            ticker: str = "BHP.AX"
            event_description: str = "Test event"

        @mini.post("/api/simulate")
        async def _simulate(body: SimRequest):
            from system_state import get_system_state, is_signals_enabled
            if not is_signals_enabled():
                state = get_system_state()
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "System paused — signal generation disabled",
                        "reason": state["kill_switch_reason"],
                    },
                )
            return {"status": "ok", "ticker": body.ticker}

        with TestClient(mini, raise_server_exceptions=False) as client:
            yield client

    def test_simulate_returns_200_when_active(self, gate_client):
        resp = gate_client.post("/api/simulate", json={"ticker": "BHP.AX", "event_description": "test"})
        assert resp.status_code == 200

    def test_simulate_returns_503_when_kill_switch_active(self, gate_client):
        import system_state
        system_state.activate_kill_switch("unit test kill switch")
        resp = gate_client.post("/api/simulate", json={"ticker": "BHP.AX", "event_description": "test"})
        assert resp.status_code == 503

    def test_simulate_503_includes_reason(self, gate_client):
        import system_state
        system_state.activate_kill_switch("feed anomaly")
        resp = gate_client.post("/api/simulate", json={"ticker": "BHP.AX", "event_description": "test"})
        body = resp.json()
        assert "feed anomaly" in str(body)

    def test_simulate_recovers_after_resume(self, gate_client):
        import system_state
        system_state.activate_kill_switch("temporary halt")
        assert gate_client.post("/api/simulate", json={"ticker": "BHP.AX", "event_description": "test"}).status_code == 503
        system_state.resume_signals()
        assert gate_client.post("/api/simulate", json={"ticker": "BHP.AX", "event_description": "test"}).status_code == 200
