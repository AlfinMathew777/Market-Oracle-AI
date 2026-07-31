"""Tests for trust/vote_weighting.py — reputation-weighted consensus voting."""

import pytest
import trust
from trust.reputation import TIER_CELL, TIER_PRIOR
from trust.vote_weighting import (
    WEIGHT_CEILING,
    WEIGHT_FLOOR,
    compute_weighted_tally,
)


class FakeStore:
    """Reputation store stub — returns canned (value, tier) per archetype."""

    def __init__(self, table: dict[str, tuple[float, str]]):
        self._table = table

    async def effective_with_tier(self, identity, kind, regime=""):
        return self._table.get(identity, (0.3, TIER_PRIOR))


def _votes(bull=3, bear=3, neut=3):
    votes = []
    for _ in range(bull):
        votes.append({"persona": "macro_bull", "vote": "bullish"})
    for _ in range(bear):
        votes.append({"persona": "geo_bear", "vote": "bearish"})
    for _ in range(neut):
        votes.append({"persona": "neutral_fund", "vote": "neutral"})
    return votes


def _patch_store(monkeypatch, table):
    async def fake_get_store(db_path=None):
        return FakeStore(table)

    monkeypatch.setattr(trust, "get_reputation_store", fake_get_store)


async def test_cold_start_all_prior_not_applied(monkeypatch):
    """All archetypes on the prior tier → weighting is an honest no-op."""
    _patch_store(monkeypatch, {})
    result = await compute_weighted_tally(_votes(), "NEUTRAL")
    assert result.applied is False
    assert result.w_bull == 3.0
    assert result.w_bear == 3.0
    assert result.w_neut == 3.0
    assert "cold-start" in result.note


async def test_seasoned_reputation_shifts_tally(monkeypatch):
    """A seasoned high-rep bear archetype outweighs a low-rep bull one."""
    _patch_store(monkeypatch, {
        "macro_bull":   (0.2, TIER_CELL),
        "geo_bear":     (0.6, TIER_CELL),
        "neutral_fund": (0.4, TIER_CELL),
    })
    result = await compute_weighted_tally(_votes(bull=3, bear=3, neut=3), "DOWNTREND")
    assert result.applied is True
    # mean rep = 0.4 → weights: bull 0.5, bear 1.5, neutral 1.0
    assert result.w_bear > result.w_bull
    assert result.w_bull == pytest.approx(3 * 0.5)
    assert result.w_bear == pytest.approx(3 * 1.5)
    assert result.w_neut == pytest.approx(3 * 1.0)


async def test_weights_clamped_to_bounds(monkeypatch):
    """Extreme reputation gaps cannot exceed the influence bounds."""
    _patch_store(monkeypatch, {
        "macro_bull": (0.95, TIER_CELL),
        "geo_bear":   (0.05, TIER_CELL),
    })
    result = await compute_weighted_tally(_votes(bull=1, bear=1, neut=0), "NEUTRAL")
    assert result.applied is True
    for weight in result.weights.values():
        assert WEIGHT_FLOOR <= weight <= WEIGHT_CEILING


async def test_store_failure_fails_soft(monkeypatch):
    """A store read error returns the raw tally — never raises."""
    async def broken_get_store(db_path=None):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(trust, "get_reputation_store", broken_get_store)
    result = await compute_weighted_tally(_votes(), "NEUTRAL")
    assert result.applied is False
    assert result.w_bull == 3.0
    assert "fail-soft" in result.note


async def test_env_kill_switch(monkeypatch):
    """REPUTATION_WEIGHTED_VOTING=0 disables weighting without a deploy."""
    monkeypatch.setenv("REPUTATION_WEIGHTED_VOTING", "0")
    result = await compute_weighted_tally(_votes(), "NEUTRAL")
    assert result.applied is False
    assert "disabled" in result.note


async def test_empty_votes(monkeypatch):
    _patch_store(monkeypatch, {})
    result = await compute_weighted_tally([], "NEUTRAL")
    assert result.applied is False
    assert result.w_bull == result.w_bear == result.w_neut == 0.0
