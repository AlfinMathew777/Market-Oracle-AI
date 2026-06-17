"""InputLayer enforcement — I1-I4 over the recorded provenance, fail-closed."""

import os
import sys
import tempfile
import types

import pytest
from trust import Decision, build_context, get_gateway, reset_gateway
from trust.constitution import THRESHOLDS

pytestmark = pytest.mark.unit


@pytest.fixture
def ledger_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="inlayer_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
async def gateway(ledger_path, monkeypatch):
    fake_state = types.ModuleType("system_state")
    fake_state.is_signals_enabled = lambda: True
    monkeypatch.setitem(sys.modules, "system_state", fake_state)
    reset_gateway()
    await get_gateway(db_path=ledger_path)
    yield
    reset_gateway()


def _clean_provenance(**over):
    p = {
        "sanitized": True, "wrapped": True, "evasion_flags": [],
        "instructions_neutralized": 0, "model_generated_cited": False,
        "independent_origins": 2, "single_source": False, "low_rep_cluster": False,
    }
    p.update(over)
    return p


def _prediction(provenance):
    p = {
        "ticker": "BHP.AX",
        "direction": "BULLISH",
        "confidence": 0.70,
        "signal_order": "primary",
        "trigger_event": "BHP reports record Q3 iron ore shipments, beats guidance 8%",
        "agent_votes": {"bull": 38, "bear": 5, "neut": 2},
        "mc_stability": 0.82,
        "historical_accuracy": 0.61,
        "judge_result": {"trigger_event": "Record Q3 shipments", "revenue_impact": "volumes up"},
    }
    if provenance is not None:
        p["input_provenance"] = provenance
    return p


async def _cert(provenance):
    gw = await get_gateway()
    return await gw.evaluate(build_context(_prediction(provenance)))


# ── fail-closed BLOCK cases ───────────────────────────────────────────────────

async def test_missing_provenance_fails_closed(gateway):
    cert = await _cert(None)
    assert cert.decision == Decision.BLOCK
    assert any(f.article == "I1" for f in cert.findings)


async def test_unsanitized_blocks(gateway):
    cert = await _cert(_clean_provenance(sanitized=False))
    assert cert.decision == Decision.BLOCK
    assert any(f.code == "INPUT.RAW_UNSANITIZED" for f in cert.findings)


async def test_unwrapped_blocks(gateway):
    cert = await _cert(_clean_provenance(wrapped=False))
    assert cert.decision == Decision.BLOCK
    assert any(f.article == "I3" for f in cert.findings)


async def test_model_self_trust_blocks(gateway):
    cert = await _cert(_clean_provenance(model_generated_cited=True))
    assert cert.decision == Decision.BLOCK
    assert any(f.article == "I2" for f in cert.findings)


async def test_low_rep_cluster_blocks(gateway):
    cert = await _cert(_clean_provenance(single_source=True, low_rep_cluster=True))
    assert cert.decision == Decision.BLOCK
    assert any(f.code == "INPUT.LOW_REP_CLUSTER" for f in cert.findings)


# ── I4 cap (publishes, not blocked) ───────────────────────────────────────────

async def test_single_source_caps_not_blocks(gateway):
    cert = await _cert(_clean_provenance(independent_origins=1, single_source=True))
    assert cert.is_actionable                          # published, NOT blocked
    assert cert.confidence_out <= THRESHOLDS.cap_uncorroborated + 1e-9
    assert any(f.code == "INPUT.UNCORROBORATED" for f in cert.findings)


# ── clean passes ──────────────────────────────────────────────────────────────

async def test_clean_corroborated_has_no_input_block(gateway):
    cert = await _cert(_clean_provenance())
    assert cert.is_actionable
    assert not any(f.layer == "input" and f.is_veto for f in cert.findings)
