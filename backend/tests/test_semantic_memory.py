"""Tests for services/semantic_memory.py — Zep-backed episodic recall."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import services.semantic_memory as sm

# ── No-key fail-soft behaviour ────────────────────────────────────────────────

async def test_index_without_key_is_noop(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "")
    ok = await sm.index_resolved_prediction(
        ticker="BHP.AX", direction="bearish", confidence=0.62,
        outcome="CORRECT", change_pct=-2.1,
    )
    assert ok is False


async def test_search_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "")
    assert await sm.search_similar_situations("BHP.AX bearish iron ore") == []


async def test_search_blank_query_returns_empty(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    assert await sm.search_similar_situations("   ") == []


async def test_unresolved_outcomes_never_indexed(monkeypatch):
    """Only CORRECT/INCORRECT become memories — no guesses in the graph."""
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    for outcome in ("NEUTRAL", "PENDING", "UNVALIDATABLE", "SKIPPED"):
        ok = await sm.index_resolved_prediction(
            ticker="BHP.AX", direction="bullish", confidence=0.6,
            outcome=outcome, change_pct=0.1,
        )
        assert ok is False


# ── Episode rendering ─────────────────────────────────────────────────────────

def test_build_episode_contains_all_signal_fields():
    episode = sm.build_episode(
        ticker="CBA.AX", direction="bearish", confidence=0.62,
        outcome="CORRECT", change_pct=-2.15,
        event_summary="RBA emergency rate hike 50bp",
        trend_label="STRONG_DOWNTREND",
        lesson="Rate shocks hit bank margins within 24h.",
    )
    assert "CBA.AX" in episode
    assert "bearish" in episode
    assert "62%" in episode
    assert "CORRECT" in episode
    assert "-2.15%" in episode
    assert "RBA emergency rate hike" in episode
    assert "STRONG_DOWNTREND" in episode
    assert "Lesson:" in episode


def test_build_episode_caps_length():
    episode = sm.build_episode(
        ticker="BHP.AX", direction="bullish", confidence=0.7,
        outcome="INCORRECT", change_pct=1.0,
        event_summary="x" * 5000,
    )
    assert len(episode) <= sm._MAX_EPISODE_CHARS


# ── Mocked Zep round-trips ────────────────────────────────────────────────────

def _fake_client_with_results(facts):
    client = MagicMock()
    client.graph.search.return_value = SimpleNamespace(
        results=[SimpleNamespace(fact=f, content=None) for f in facts]
    )
    return client


async def test_search_returns_facts(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    client = _fake_client_with_results(["past outcome A", "past outcome B"])
    monkeypatch.setattr(sm, "_client", lambda: client)

    results = await sm.search_similar_situations("CBA.AX bearish rate hike", limit=2)
    assert results == ["past outcome A", "past outcome B"]
    # Query must be truncated to Zep's comfortable bounds
    _, kwargs = client.graph.search.call_args
    assert len(kwargs["query"]) <= sm._MAX_QUERY_CHARS


async def test_search_zep_error_fails_soft(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    client = MagicMock()
    client.graph.search.side_effect = RuntimeError("zep down")
    monkeypatch.setattr(sm, "_client", lambda: client)

    assert await sm.search_similar_situations("anything") == []


async def test_index_success(monkeypatch):
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    client = MagicMock()
    monkeypatch.setattr(sm, "_client", lambda: client)

    ok = await sm.index_resolved_prediction(
        ticker="FMG.AX", direction="bullish", confidence=0.58,
        outcome="INCORRECT", change_pct=-1.4,
        event_summary="Lombok strait disruption",
    )
    assert ok is True
    client.graph.add.assert_called_once()
    _, kwargs = client.graph.add.call_args
    assert kwargs["graph_id"] == sm._GRAPH_ID
    assert "FMG.AX" in kwargs["data"]


async def test_index_creates_graph_on_first_failure(monkeypatch):
    """Missing graph → create it and retry the add once."""
    monkeypatch.setattr(sm, "_ZEP_KEY", "fake-key")
    client = MagicMock()
    client.graph.add.side_effect = [RuntimeError("graph not found"), None]
    monkeypatch.setattr(sm, "_client", lambda: client)

    ok = await sm.index_resolved_prediction(
        ticker="RIO.AX", direction="bearish", confidence=0.66,
        outcome="CORRECT", change_pct=-3.0,
    )
    assert ok is True
    client.graph.create.assert_called_once_with(graph_id=sm._GRAPH_ID)
    assert client.graph.add.call_count == 2
