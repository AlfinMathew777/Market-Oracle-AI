"""Tests for the 5-layer Trust Stack.

Covers: each layer's veto behaviour, gateway aggregation/decision, confidence
capping, fail-closed semantics, and the tamper-evident ledger.

The tests bind the gateway to an isolated ledger file via reset_gateway() so the
project DB is never touched (testing rule: production DB is sacred).
"""

import os
import tempfile

import pytest
from trust import Decision, build_context, get_gateway, reset_gateway
from trust.ledger import TrustLedger, compute_hash


@pytest.fixture
def ledger_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="trust_test_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
async def gateway(ledger_path, monkeypatch):
    # Force kill switch OFF so RiskLayer doesn't block by default.
    import sys
    import types

    fake_state = types.ModuleType("system_state")
    fake_state.is_signals_enabled = lambda: True
    monkeypatch.setitem(sys.modules, "system_state", fake_state)

    reset_gateway()
    gw = await get_gateway(db_path=ledger_path)
    yield gw
    reset_gateway()


def _good_prediction():
    """A clean, high-quality BULLISH signal that should APPROVE."""
    return {
        "ticker": "BHP.AX",
        "direction": "BULLISH",
        "confidence": 0.70,
        "signal_order": "primary",
        "trigger_event": "BHP reports record Q3 iron ore shipments, beats guidance by 8%",
        "agent_votes": {"bull": 38, "bear": 5, "neut": 2},
        "mc_stability": 0.82,
        "historical_accuracy": 0.61,
        "judge_result": {
            "trigger_event": "Record Q3 iron ore shipments reported",
            "cost_impact": "Stable unit costs in Pilbara",
            "revenue_impact": "Higher volumes lift revenue",
            "demand_signal": "China restocking supports demand",
            "sentiment_signal": "Analyst upgrades following result",
        },
        "data_feeds": {"yfinance": 60, "news": 120},
        "paper_mode": True,
    }


# ── Gateway decisions ───────────────────────────────────────────────────────
async def test_clean_signal_approves(gateway):
    cert = await gateway.evaluate(build_context(_good_prediction()))
    assert cert.decision in (Decision.APPROVE, Decision.APPROVE_DEGRADED)
    assert cert.is_actionable
    assert cert.trust_score >= 60
    assert cert.ledger_seq == 1
    assert cert.ledger_hash


async def test_confidence_capped_to_primary_order(gateway):
    pred = _good_prediction()
    pred["confidence"] = 0.99  # Above the 0.75 primary cap and 0.85 absolute.
    cert = await gateway.evaluate(build_context(pred))
    assert cert.confidence_out <= 0.75
    assert cert.decision == Decision.APPROVE_DEGRADED  # capping forces degraded


async def test_missing_catalyst_blocks(gateway):
    pred = _good_prediction()
    pred["trigger_event"] = ""
    pred["judge_result"]["trigger_event"] = ""
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.BLOCK
    assert cert.direction_out == "NEUTRAL"
    assert any(f.code == "EVID.CATALYST_MISSING" for f in cert.findings)


async def test_low_confidence_blocks(gateway):
    pred = _good_prediction()
    pred["confidence"] = 0.20
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.BLOCK
    assert any(f.article == "V1" for f in cert.findings)


async def test_geographic_error_blocks(gateway):
    pred = _good_prediction()
    pred["judge_result"]["demand_signal"] = "Iron ore shipments via Malacca Strait disrupted"
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.BLOCK
    assert any(f.code == "EVID.GEO_ERROR" for f in cert.findings)


async def test_stale_feed_blocks(gateway):
    pred = _good_prediction()
    pred["data_feeds"] = {"yfinance": 99999}  # way past 30-min ceiling
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.BLOCK
    assert any(f.code == "EVID.FEED_STALE" for f in cert.findings)


async def test_neutral_never_actionable(gateway):
    pred = _good_prediction()
    pred["direction"] = "NEUTRAL"
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.BLOCK
    assert not cert.is_actionable


async def test_weak_consensus_degrades(gateway):
    pred = _good_prediction()
    pred["agent_votes"] = {"bull": 16, "bear": 15, "neut": 14}  # near tie
    cert = await gateway.evaluate(build_context(pred))
    assert cert.decision == Decision.APPROVE_DEGRADED
    assert any(f.code == "VALID.WEAK_CONSENSUS" for f in cert.findings)


async def test_kill_switch_blocks(gateway, monkeypatch):
    import sys
    sys.modules["system_state"].is_signals_enabled = lambda: False
    cert = await gateway.evaluate(build_context(_good_prediction()))
    assert cert.decision == Decision.BLOCK
    assert any(f.code == "RISK.KILL_SWITCH_ACTIVE" for f in cert.findings)


# ── Ledger: tamper-evidence ─────────────────────────────────────────────────
async def test_ledger_chain_intact_after_appends(gateway):
    for _ in range(3):
        await gateway.evaluate(build_context(_good_prediction()))
    ledger = gateway._ledger  # noqa: SLF001 — white-box check
    intact, broken = await ledger.verify_chain()
    assert intact
    assert broken is None


async def test_ledger_detects_tampering(ledger_path):
    import sqlite3

    ledger = TrustLedger(ledger_path)
    await ledger.init()
    await ledger.append({"x": 1}, ticker="A", decision="APPROVE", trust_score=90, issued_at="t1")
    await ledger.append({"x": 2}, ticker="B", decision="BLOCK", trust_score=10, issued_at="t2")

    intact, _ = await ledger.verify_chain()
    assert intact

    # Tamper with the first row's payload directly in SQLite.
    conn = sqlite3.connect(ledger_path)
    conn.execute("UPDATE trust_ledger SET payload = ? WHERE seq = 1", ('{"x":999}',))
    conn.commit()
    conn.close()

    intact, broken = await ledger.verify_chain()
    assert not intact
    assert broken == 1


async def test_hash_is_deterministic():
    h1 = compute_hash(5, "abc", {"b": 2, "a": 1})
    h2 = compute_hash(5, "abc", {"a": 1, "b": 2})  # key order must not matter
    assert h1 == h2
    assert compute_hash(6, "abc", {"a": 1}) != h1


# ── Fail-closed ─────────────────────────────────────────────────────────────
async def test_layer_crash_fails_closed(gateway, monkeypatch):
    # Make the evidence layer raise; the gateway must BLOCK, not approve.
    from trust.layers.evidence import EvidenceLayer

    def boom(self, ctx):
        raise RuntimeError("simulated layer failure")

    monkeypatch.setattr(EvidenceLayer, "_check", boom)
    cert = await gateway.evaluate(build_context(_good_prediction()))
    assert cert.decision == Decision.BLOCK
    assert any("LAYER_ERROR" in f.code for f in cert.findings)
