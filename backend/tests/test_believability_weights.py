"""
Unit tests for believability-weighted confidence (UPGRADE 1b in scripts/test_core.py).

Covers the pure weighting helper and the flag-gated async wrapper:
  (a) flag OFF  → reputation store never called, confidence equals raw path
  (b) flag ON + uniform scores → weights normalise away, confidence equals raw path
  (c) flag ON + skewed scores  → confidence moves in the correct direction,
      direction determination (raw counts) unchanged
  (d) store raises → FAIL OPEN to raw counts + audit fallback note
"""

import copy
import math
from unittest.mock import AsyncMock, patch

import pytest

import scripts.test_core as core

pytestmark = pytest.mark.unit


# ── Helpers ────────────────────────────────────────────────────────────────────

def _vote(persona: str, vote: str, idx: int = 0) -> dict:
    return {"agent_id": f"{persona}_{idx}", "persona": persona, "vote": vote, "reason": "test"}


def _make_votes(spec: list[tuple[str, str, int]]) -> list[dict]:
    """spec: list of (persona, vote, count)."""
    votes: list[dict] = []
    for persona, vote, count in spec:
        votes.extend(_vote(persona, vote, i) for i in range(count))
    return votes


UNIFORM_SCORES = {"macro_bull": 0.3, "geo_bear": 0.3, "quant": 0.3, "neutral_fund": 0.3}
SKEWED_SCORES = {"macro_bull": 0.9, "geo_bear": 0.1, "quant": 0.5, "neutral_fund": 0.5}

# 10 bullish (macro_bull) / 6 bearish (geo_bear) / 4 neutral (quant)
STANDARD_SPEC = [("macro_bull", "bullish", 10), ("geo_bear", "bearish", 6), ("quant", "neutral", 4)]


# ── (a) Flag OFF — store never touched, raw path exact ─────────────────────────

async def test_flag_off_store_never_called_confidence_equals_raw(monkeypatch):
    monkeypatch.setattr(core, "USE_BELIEVABILITY_WEIGHTS", False)
    fetch_mock = AsyncMock()
    monkeypatch.setattr(core, "fetch_archetype_believability", fetch_mock)

    votes = _make_votes(STANDARD_SPEC)
    (w_bull, w_bear, w_neut), scores, note = await core.compute_believability_tally(votes, 10, 6, 4)

    fetch_mock.assert_not_called()
    assert (w_bull, w_bear, w_neut) == (10.0, 6.0, 4.0)
    assert scores is None
    assert note is None
    assert core.calculate_confidence(w_bull, w_bear, w_neut) == core.calculate_confidence(10, 6, 4)


# ── (b) Flag ON + uniform scores — weights normalise away ──────────────────────

async def test_uniform_scores_normalise_to_raw_counts():
    votes = _make_votes(STANDARD_SPEC)
    w_bull, w_bear, w_neut = core.apply_believability_weights(votes, UNIFORM_SCORES)

    assert w_bull == pytest.approx(10.0)
    assert w_bear == pytest.approx(6.0)
    assert w_neut == pytest.approx(4.0)
    assert core.calculate_confidence(w_bull, w_bear, w_neut) == core.calculate_confidence(10, 6, 4)


async def test_flag_on_uniform_scores_via_wrapper(monkeypatch):
    monkeypatch.setattr(core, "USE_BELIEVABILITY_WEIGHTS", True)
    monkeypatch.setattr(core, "fetch_archetype_believability", AsyncMock(return_value=UNIFORM_SCORES))

    votes = _make_votes(STANDARD_SPEC)
    (w_bull, w_bear, w_neut), scores, note = await core.compute_believability_tally(votes, 10, 6, 4)

    assert scores == UNIFORM_SCORES
    assert note is None
    assert core.calculate_confidence(w_bull, w_bear, w_neut) == core.calculate_confidence(10, 6, 4)


# ── (c) Flag ON + skewed scores — confidence moves, direction untouched ────────

async def test_skewed_scores_move_confidence_in_correct_direction():
    """High-believability bulls vs low-believability bears → confidence rises."""
    votes = _make_votes(STANDARD_SPEC)
    original = copy.deepcopy(votes)

    w_bull, w_bear, w_neut = core.apply_believability_weights(votes, SKEWED_SCORES)

    # Normalisation preserves the total (participation semantics intact).
    assert w_bull + w_bear + w_neut == pytest.approx(20.0)
    # Bullish majority backed by the more-believable archetype → amplified.
    assert w_bull > 10.0
    assert w_bear < 6.0

    raw_conf = core.calculate_confidence(10, 6, 4)
    weighted_conf = core.calculate_confidence(w_bull, w_bear, w_neut)
    assert weighted_conf > raw_conf

    # Pure function: inputs never mutated (raw counts stay the source of truth).
    assert votes == original


async def test_low_believability_directional_voters_lower_confidence():
    """Directional archetypes less believable than neutrals → weighted
    participation shrinks → confidence drops vs the raw path."""
    scores = {"macro_bull": 0.1, "geo_bear": 0.1, "quant": 0.9, "neutral_fund": 0.9}
    votes = _make_votes(STANDARD_SPEC)

    w_bull, w_bear, w_neut = core.apply_believability_weights(votes, scores)

    raw_conf = core.calculate_confidence(10, 6, 4)
    weighted_conf = core.calculate_confidence(w_bull, w_bear, w_neut)
    assert weighted_conf < raw_conf
    # Total still preserved — only the side balance moved.
    assert w_bull + w_bear + w_neut == pytest.approx(20.0)


async def test_direction_determination_uses_raw_counts_and_is_unchanged(monkeypatch):
    monkeypatch.setattr(core, "USE_BELIEVABILITY_WEIGHTS", True)
    monkeypatch.setattr(core, "fetch_archetype_believability", AsyncMock(return_value=SKEWED_SCORES))

    votes = _make_votes(STANDARD_SPEC)
    direction_before = core.determine_direction(10, 6, 4, 1.0, "Geopolitical escalation event", 0.6)

    await core.compute_believability_tally(votes, 10, 6, 4)

    # Direction is computed from the raw integer counts, which the weighting
    # path never touches — same inputs, same result.
    direction_after = core.determine_direction(10, 6, 4, 1.0, "Geopolitical escalation event", 0.6)
    assert direction_after == direction_before


# ── (d) Store failure — FAIL OPEN with audit note ───────────────────────────────

async def test_store_failure_falls_back_to_raw_counts_with_audit_note(monkeypatch):
    monkeypatch.setattr(core, "USE_BELIEVABILITY_WEIGHTS", True)
    monkeypatch.setattr(
        core, "fetch_archetype_believability",
        AsyncMock(side_effect=RuntimeError("reputation db down")),
    )

    votes = _make_votes(STANDARD_SPEC)
    (w_bull, w_bear, w_neut), scores, note = await core.compute_believability_tally(votes, 10, 6, 4)

    assert (w_bull, w_bear, w_neut) == (10.0, 6.0, 4.0)  # raw counts, uniform behaviour
    assert scores is None
    assert note is not None
    assert "raw counts used" in note
    assert "reputation db down" in note


# ── Fetch wrapper — pooled (regime-agnostic) reads via mocked store ─────────────

async def test_fetch_archetype_believability_reads_pooled_scores():
    store = AsyncMock()
    store.effective_archetype = AsyncMock(return_value=0.42)

    with patch("trust.get_reputation_store", AsyncMock(return_value=store)):
        scores = await core.fetch_archetype_believability()

    assert set(scores) == {"macro_bull", "geo_bear", "quant", "neutral_fund"}
    assert all(v == 0.42 for v in scores.values())
    # Pooled deliberately — regime always "" (regime bias already applied by
    # get_persona_distribution's persona mix).
    for call in store.effective_archetype.call_args_list:
        assert call.args[1] == ""


# ── Edge cases for the pure helper ──────────────────────────────────────────────

async def test_empty_votes_return_zeros():
    assert core.apply_believability_weights([], SKEWED_SCORES) == (0.0, 0.0, 0.0)


async def test_unknown_persona_uses_prior():
    votes = [_vote("mystery_persona", "bullish", 0), _vote("macro_bull", "bearish", 1)]
    w_bull, w_bear, w_neut = core.apply_believability_weights(votes, {"macro_bull": 0.3})
    # Unknown persona falls back to the 0.3 prior — equal weights → raw counts.
    assert w_bull == pytest.approx(1.0)
    assert w_bear == pytest.approx(1.0)
    assert w_neut == pytest.approx(0.0)


async def test_malformed_votes_excluded():
    votes = _make_votes([("macro_bull", "bullish", 4), ("geo_bear", "bearish", 2)])
    votes.append({"agent_id": "broken", "persona": "quant", "vote": "sideways", "reason": "?"})
    w_bull, w_bear, w_neut = core.apply_believability_weights(votes, UNIFORM_SCORES)
    assert w_bull + w_bear + w_neut == pytest.approx(6.0)


async def test_sanity_anchor_unaffected():
    """main()'s calc-check input must be unaffected by this change.

    Note: main() prints "expect ~0.230" — a stale label from the pre-sqrt
    formula. The current weighted_variance_v2 formula gives 0.693 for
    (0 bull, 24 bear, 26 neutral); this pins that unchanged behaviour.
    """
    assert math.isclose(core.calculate_confidence(0, 24, 26), 0.693, abs_tol=0.001)
