"""Tests for attribution — driving archetypes, claims, sources, ledger join."""

import os
import tempfile

import pytest
from trust.attribution import append_attribution, build_attribution
from trust.ledger import TrustLedger

pytestmark = pytest.mark.unit

_TS = "2026-06-17T00:00:00Z"


def _votes():
    return [
        {"agent_id": 1, "persona": "macro_bull", "vote": "bullish", "reason": "x"},
        {"agent_id": 2, "persona": "macro_bull", "vote": "bullish", "reason": "x"},
        {"agent_id": 3, "persona": "geo_bear", "vote": "bearish", "reason": "x"},
        {"agent_id": 4, "persona": "quant", "vote": "bullish", "reason": "x"},
        {"agent_id": 5, "persona": "neutral_fund", "vote": "neutral", "reason": "x"},
    ]


def _judge():
    return {
        "trigger_event": "China cuts iron ore imports",
        "revenue_impact": "Iron ore at $90/t (-8%) compresses margin",
        "cost_impact": "No data — assumed neutral",
        "demand_impact": "China PMI 48 signals contraction",
        "sentiment_impact": "",
    }


def _build(sim_id="sim_X", direction="UP", chain_override=False):
    return build_attribution(
        simulation_id=sim_id,
        ticker="BHP.AX",
        direction=direction,
        confidence=0.62,
        all_votes=_votes(),
        judge_result=_judge(),
        news_items=[
            {"source": "reuters", "weight": 0.9, "title": "China cuts imports"},
            {"url": "https://afr.com/x", "weight": 0.5},
            {"source": "reuters", "weight": 0.7},
        ],
        alt_data={"per_source": {"reddit_sentiment": {}, "asx_announcements": {}}},
        chain_override=chain_override,
    )


# ── build ─────────────────────────────────────────────────────────────────────

def test_driving_archetypes_are_winning_side_only():
    attr = _build(direction="UP")  # bullish side
    assert attr["driving_archetypes"] == {"macro_bull": 2, "quant": 1}  # no geo_bear/neutral


def test_archetype_is_the_key_not_agent_id():
    attr = _build()
    keys = set(attr["driving_archetypes"].keys())
    assert keys <= {"macro_bull", "geo_bear", "quant", "neutral_fund"}
    # no per-run integer ids leak into the reputation-bearing structure.
    assert all(not str(k).isdigit() for k in keys)


def test_claims_skip_empty_and_no_data_slots():
    attr = _build()
    slots = {c["slot"] for c in attr["vote_moving_claims"]}
    assert slots == {"trigger", "revenue_impact", "demand_impact"}  # cost/sentiment dropped


def test_source_roster_dedupes_and_includes_alt_data():
    attr = _build()
    ids = {s["source_id"] for s in attr["sources"]}
    assert ids == {"reuters", "afr.com", "reddit_sentiment", "asx_announcements"}
    reuters = next(s for s in attr["sources"] if s["source_id"] == "reuters")
    assert reuters["weight"] == 0.9  # max weight across duplicates


def test_chain_override_flag_passes_through():
    assert _build(chain_override=True)["chain_override"] is True
    assert _build(chain_override=False)["chain_override"] is False


def test_neutral_direction_has_no_directional_drivers():
    attr = _build(direction="NEUTRAL")
    assert attr["driving_archetypes"] == {"neutral_fund": 1}


# ── ledger join ─────────────────────────────────────────────────────────────

@pytest.fixture
def ledger_path():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="attr_ledger_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


async def test_attribution_is_retrievable_by_simulation_id(ledger_path):
    ledger = TrustLedger(ledger_path)
    await ledger.init()
    payload = _build(sim_id="sim_join_001")

    await append_attribution(ledger, payload, issued_at=_TS)

    got = await ledger.find_attribution("sim_join_001")
    assert got is not None
    assert got["simulation_id"] == "sim_join_001"
    assert got["driving_archetypes"] == {"macro_bull": 2, "quant": 1}
    assert {s["source_id"] for s in got["sources"]} == {
        "reuters", "afr.com", "reddit_sentiment", "asx_announcements",
    }


async def test_unknown_simulation_id_returns_none(ledger_path):
    ledger = TrustLedger(ledger_path)
    await ledger.init()
    assert await ledger.find_attribution("does_not_exist") is None
