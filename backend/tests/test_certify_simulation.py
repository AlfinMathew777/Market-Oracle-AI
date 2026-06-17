"""Stage 4 — the swarm path is certified by the same gateway, fail-closed."""

import os
import sys
import tempfile
import types

import pytest
from trust import Decision, get_gateway, reset_gateway
from trust.integration import certify_simulation, simulation_to_prediction

pytestmark = pytest.mark.unit


@pytest.fixture
def ledger_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="cert_sim_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
async def gateway(ledger_path, monkeypatch):
    # kill switch OFF so RiskLayer doesn't block by default.
    fake_state = types.ModuleType("system_state")
    fake_state.is_signals_enabled = lambda: True
    monkeypatch.setitem(sys.modules, "system_state", fake_state)
    reset_gateway()
    await get_gateway(db_path=ledger_path)  # bind the singleton to the temp ledger
    yield
    reset_gateway()


def _clean_swarm_prediction():
    return {
        "ticker": "BHP.AX",
        "direction": "UP",
        "confidence": 0.70,
        "trigger_event": "BHP reports record Q3 iron ore shipments, beats guidance 8%",
        "agent_consensus": {"up": 38, "down": 5, "neutral": 2},
        "quality_assessment": {"mc_stability_pct": 82.0, "historical_accuracy_pct": 61.0},
        "causal_chain": [{"consequence": "higher realised volume"}],
        "input_provenance": {
            "sanitized": True, "wrapped": True, "evasion_flags": [],
            "instructions_neutralized": 0, "model_generated_cited": False,
            "independent_origins": 2, "single_source": False, "low_rep_cluster": False,
        },
    }


# ── adapter ───────────────────────────────────────────────────────────────────

def test_adapter_maps_swarm_shape():
    p = simulation_to_prediction(_clean_swarm_prediction())
    assert p["direction"] == "BULLISH"           # UP → BULLISH
    assert p["agent_votes"] == {"bull": 38, "bear": 5, "neut": 2}
    assert p["mc_stability"] == pytest.approx(0.82)
    assert p["catalyst"].startswith("BHP reports")


def test_adapter_neutral_passthrough():
    p = simulation_to_prediction({"ticker": "X", "direction": "NEUTRAL"})
    assert p["direction"] == "NEUTRAL"


# ── certification (fail-closed) ───────────────────────────────────────────────

async def test_clean_swarm_prediction_is_actionable(gateway):
    cert = await certify_simulation(_clean_swarm_prediction())
    assert cert.is_actionable
    assert cert.decision in (Decision.APPROVE, Decision.APPROVE_DEGRADED)


async def test_forced_failing_layer_blocks_and_neutralises(gateway):
    # a directional signal with NO catalyst trips Evidence article E1 (BLOCK).
    bad = _clean_swarm_prediction()
    bad["trigger_event"] = ""
    bad["causal_chain"] = []
    cert = await certify_simulation(bad)
    assert cert.decision == Decision.BLOCK
    assert cert.is_actionable is False
    assert cert.direction_out == "NEUTRAL"        # forced neutral, not the UP it claimed
    assert any(f.article == "E1" for f in cert.findings)  # blocking article recorded


async def test_kill_switch_blocks_swarm(gateway, monkeypatch):
    # operator halt must veto a swarm signal too (Risk article R1).
    import system_state
    monkeypatch.setattr(system_state, "is_signals_enabled", lambda: False)
    cert = await certify_simulation(_clean_swarm_prediction())
    assert cert.decision == Decision.BLOCK
    assert cert.direction_out == "NEUTRAL"
