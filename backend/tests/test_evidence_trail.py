"""Stage 5 — evidence trail: trace a prediction to its sources, flag unbacked claims."""

import os
import tempfile

import pytest
from trust.attribution import append_attribution, build_attribution
from trust.evidence_trail import build_evidence_trail
from trust.ledger import TrustLedger

pytestmark = pytest.mark.unit

_TS = "2026-06-17T00:00:00Z"


@pytest.fixture
def ledger_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="evtrail_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


async def _ledger(path):
    led = TrustLedger(path)
    await led.init()
    return led


def _attribution(sim_id, *, with_sources=True):
    return build_attribution(
        simulation_id=sim_id,
        ticker="BHP.AX",
        direction="UP",
        confidence=0.62,
        all_votes=[{"agent_id": 1, "persona": "macro_bull", "vote": "bullish"}],
        judge_result={"trigger_event": "China cuts iron ore imports",
                      "revenue_impact": "Iron ore at $90/t compresses margin"},
        news_items=([{"source": "reuters", "weight": 0.9}] if with_sources else []),
        alt_data=({"per_source": {"reddit_sentiment": {}}} if with_sources else {}),
    )


async def test_complete_trail_joinable_by_simulation_id(ledger_path):
    led = await _ledger(ledger_path)
    await append_attribution(led, _attribution("sim_ev_1"), issued_at=_TS)

    trail = await build_evidence_trail(led, None, "sim_ev_1")
    assert trail is not None
    assert trail["simulation_id"] == "sim_ev_1"
    assert trail["complete"] is True
    # every claim traces to backing sources with a provenance class + reputation slot.
    assert all(not c["unbacked"] for c in trail["claims"])
    assert {s["source_id"] for s in trail["sources"]} == {"reuters", "reddit_sentiment"}
    assert all(s["provenance_class"] == "untrusted_external" for s in trail["sources"])


async def test_unbacked_claim_is_flagged_not_silent(ledger_path):
    led = await _ledger(ledger_path)
    await append_attribution(led, _attribution("sim_ev_2", with_sources=False), issued_at=_TS)

    trail = await build_evidence_trail(led, None, "sim_ev_2")
    assert trail is not None
    assert trail["complete"] is False               # not silently published
    assert all(c["unbacked"] for c in trail["claims"])
    assert all(c["article"] == "E5" for c in trail["claims"])  # tied to no-invented-facts


async def test_reputation_snapshot_is_used_when_present(ledger_path):
    led = await _ledger(ledger_path)
    attr = _attribution("sim_ev_3")
    for s in attr["sources"]:
        s["reputation_at_decision"] = 0.42
        s["reputation_tier"] = "cell"
    await append_attribution(led, attr, issued_at=_TS)

    trail = await build_evidence_trail(led, None, "sim_ev_3")  # store=None → must use snapshot
    assert all(s["reputation_at_decision"] == 0.42 for s in trail["sources"])
    assert all(s["reputation_tier"] == "cell" for s in trail["sources"])


async def test_unknown_simulation_id_returns_none(ledger_path):
    led = await _ledger(ledger_path)
    assert await build_evidence_trail(led, None, "nope") is None
