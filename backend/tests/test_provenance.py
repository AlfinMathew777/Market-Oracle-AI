"""Tests for services/provenance.py — auditable prediction provenance."""

import database
import trust as trust_pkg
from services.provenance import build_provenance

_SIM_ID = "sim_20260731_000000_abc123"

_PREDICTION = {
    "id": _SIM_ID,
    "ticker": "BHP.AX",
    "predicted_direction": "bearish",
    "confidence": 0.62,
    "predicted_at": "2026-07-30T01:00:00+00:00",
    "primary_reason": "Iron ore weakness",
    "trend_label": "DOWNTREND",
    "excluded_from_stats": 0,
    "agent_bullish": 6,
    "agent_bearish": 14,
    "agent_neutral": 5,
    "actual_direction": "bearish",
    "actual_price_change_pct": -1.8,
    "prediction_correct": 1,
    "resolved_at": "2026-07-31T01:00:00+00:00",
    "lesson": "BHP moved -1.80% over 24h (correct).",
    "resolution_notes": "entry 40.0 -> exit 39.28",
}

_FULL_JSON = {
    "ticker": "BHP.AX",
    "confidence_audit": {
        "final_confidence": 62.0,
        "reputation_weighting": {"applied": True, "weights": {"quant": 1.2}},
        "penalties_applied": [],
    },
    "persona_distribution": "Bear-weighted",
    "cognitive_diversity": {"monoculture_risk": "LOW", "diversity_score": 0.8},
    "regime_drift": {"level": "NONE", "multiplier": 1.0},
    "signal_grade": "B",
    "is_actionable": True,
    "chain_override_flag": False,
    "trust": {"decision": "APPROVE", "trust_score": 82},
    "all_votes": [
        {"vote": "bearish", "persona": "quant", "provider": "groq-70b"},
        {"vote": "bearish", "persona": "quant", "provider": "gemini"},
        {"vote": "bullish", "persona": "macro_bull", "provider": None},
    ],
}

_ATTRIBUTION = {
    "simulation_id": _SIM_ID,
    "driving_archetypes": {"geo_bear": 10},
    "sources": [{"source_id": "reuters", "weight": 0.9}],
}


class FakeLedger:
    def __init__(self, attribution=None, intact=True, broken_seq=None, fail=False):
        self._attribution = attribution
        self._intact = intact
        self._broken = broken_seq
        self._fail = fail

    async def find_attribution(self, simulation_id):
        if self._fail:
            raise RuntimeError("ledger locked")
        return self._attribution

    async def verify_chain(self):
        if self._fail:
            raise RuntimeError("ledger locked")
        return self._intact, self._broken


def _patch_all(monkeypatch, prediction=None, full_json=None, ledger=None):
    async def fake_pred(sim_id):
        return prediction

    async def fake_json(sim_id):
        return full_json

    async def fake_ledger(*args, **kwargs):
        return ledger or FakeLedger()

    monkeypatch.setattr(database, "get_prediction_by_simulation_id", fake_pred, raising=False)
    monkeypatch.setattr(database, "get_simulation_full_json", fake_json)
    monkeypatch.setattr(trust_pkg, "get_ledger", fake_ledger)


async def test_full_document_assembled(monkeypatch):
    _patch_all(
        monkeypatch, prediction=_PREDICTION, full_json=_FULL_JSON,
        ledger=FakeLedger(attribution=_ATTRIBUTION, intact=True),
    )
    doc = await build_provenance(_SIM_ID)

    assert doc is not None
    assert doc["ticker"] == "BHP.AX"
    assert doc["decision"]["direction"] == "bearish"
    assert doc["decision"]["trust"]["decision"] == "APPROVE"
    assert doc["decision"]["regime_drift"]["level"] == "NONE"
    assert doc["swarm"]["vote_counts"]["bearish"] == 14
    assert doc["swarm"]["reputation_weighting"]["applied"] is True
    assert doc["swarm"]["cognitive_diversity"]["monoculture_risk"] == "LOW"
    assert doc["swarm"]["votes_by_provider"]["groq-70b"]["bearish"] == 1
    assert doc["evidence"]["attribution"]["sources"][0]["source_id"] == "reuters"
    assert doc["outcome"]["resolved"] is True
    assert doc["outcome"]["prediction_correct"] == 1
    assert doc["ledger_integrity"]["chain_intact"] is True
    assert all(doc["sections_present"].values())


async def test_unknown_simulation_returns_none(monkeypatch):
    _patch_all(monkeypatch, prediction=None, full_json=None)
    assert await build_provenance("sim_does_not_exist") is None


async def test_partial_sections_still_assemble(monkeypatch):
    """Missing simulation JSON + missing attribution → document still built."""
    _patch_all(
        monkeypatch, prediction=_PREDICTION, full_json=None,
        ledger=FakeLedger(attribution=None),
    )
    doc = await build_provenance(_SIM_ID)
    assert doc is not None
    assert doc["sections_present"] == {
        "prediction_log": True, "simulation_json": False, "attribution": False,
    }
    assert "no attribution" in doc["evidence"]["note"]


async def test_tampered_ledger_is_reported_not_hidden(monkeypatch):
    _patch_all(
        monkeypatch, prediction=_PREDICTION, full_json=_FULL_JSON,
        ledger=FakeLedger(attribution=_ATTRIBUTION, intact=False, broken_seq=17),
    )
    doc = await build_provenance(_SIM_ID)
    assert doc["ledger_integrity"]["chain_intact"] is False
    assert doc["ledger_integrity"]["first_broken_seq"] == 17
    assert "TAMPER" in doc["ledger_integrity"]["note"]


async def test_ledger_failure_fails_soft(monkeypatch):
    _patch_all(
        monkeypatch, prediction=_PREDICTION, full_json=_FULL_JSON,
        ledger=FakeLedger(fail=True),
    )
    doc = await build_provenance(_SIM_ID)
    assert doc is not None  # other sections survive
    assert doc["ledger_integrity"]["verified"] is False
    assert "unavailable" in doc["ledger_integrity"]["note"]


async def test_unresolved_prediction_outcome(monkeypatch):
    pending = dict(_PREDICTION, actual_direction=None, prediction_correct=None, resolved_at=None)
    _patch_all(monkeypatch, prediction=pending, full_json=_FULL_JSON)
    doc = await build_provenance(_SIM_ID)
    assert doc["outcome"]["resolved"] is False
