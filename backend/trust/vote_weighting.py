"""Reputation-weighted consensus voting.

Closes the reputation loop at the point where it matters: the vote tally.
Archetype reputation (earned by the outcome-fed loop in reputation_update.py)
scales each agent's vote weight, so archetypes with a real track record count
for more than chronically-wrong ones — without ever silencing anyone.

Design (mirrors the reputation store's own philosophy):
  - weights are the archetype's regime-conditioned effective reputation,
    normalised so the MEAN weight across voting archetypes is 1.0 — a weighted
    tally is directly comparable to a raw head-count.
  - clamped to [WEIGHT_FLOOR, WEIGHT_CEILING]; a bad archetype is damped,
    never muted (same reason the store has a reputation floor).
  - cold start is a guaranteed no-op: while every archetype sits on the prior
    tier, `applied` is False and callers keep the raw integer tally.
  - fail-soft everywhere: any store/read error returns the raw tally — vote
    weighting must never break a simulation.

Kill switch: set REPUTATION_WEIGHTED_VOTING=0 to disable without a deploy.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Relative influence bounds — one archetype can at most double / at least halve
# its head-count influence, no matter how extreme its reputation gets.
WEIGHT_FLOOR = 0.5
WEIGHT_CEILING = 2.0

_ENV_FLAG = "REPUTATION_WEIGHTED_VOTING"


@dataclass(frozen=True)
class WeightedTally:
    """Weighted vote totals plus the audit trail of how they were produced."""

    w_bull: float
    w_bear: float
    w_neut: float
    applied: bool
    weights: dict[str, float] = field(default_factory=dict)
    tiers: dict[str, str] = field(default_factory=dict)
    note: str = ""


def _clamp_weight(value: float) -> float:
    return max(WEIGHT_FLOOR, min(WEIGHT_CEILING, value))


def _raw_tally(all_votes: list[dict], note: str) -> WeightedTally:
    """Unweighted fallback — identical numbers to the plain head-count."""
    n_bull = sum(1 for v in all_votes if v.get("vote") == "bullish")
    n_bear = sum(1 for v in all_votes if v.get("vote") == "bearish")
    n_neut = sum(1 for v in all_votes if v.get("vote") == "neutral")
    return WeightedTally(
        w_bull=float(n_bull), w_bear=float(n_bear), w_neut=float(n_neut),
        applied=False, note=note,
    )


async def compute_weighted_tally(
    all_votes: list[dict], trend_label: str
) -> WeightedTally:
    """Weight each vote by its archetype's effective reputation.

    Args:
        all_votes:   vote dicts from the swarm — needs "vote" and "persona" keys
        trend_label: the run's trend bucket; collapsed to the reputation regime

    Returns:
        WeightedTally. `applied` is True only when at least one archetype has a
        seasoned (non-prior) reputation AND the weighting actually ran.
    """
    if os.environ.get(_ENV_FLAG, "1") != "1":
        return _raw_tally(all_votes, note="disabled via env flag")
    if not all_votes:
        return _raw_tally(all_votes, note="no votes")

    try:
        from trust import get_reputation_store
        from trust.reputation import ARCHETYPE, TIER_PRIOR
        from trust.reputation_update import collapse_regime

        store = await get_reputation_store()
        regime = collapse_regime(trend_label or "")

        personas = sorted({v.get("persona") for v in all_votes if v.get("persona")})
        if not personas:
            return _raw_tally(all_votes, note="no personas on votes")

        effective: dict[str, float] = {}
        tiers: dict[str, str] = {}
        for persona in personas:
            value, tier = await store.effective_with_tier(persona, ARCHETYPE, regime)
            effective[persona] = value
            tiers[persona] = tier

        # Cold start: every archetype still on the static prior → weighting
        # would be a mathematical no-op. Report it honestly as not applied.
        if all(tier == TIER_PRIOR for tier in tiers.values()):
            return _raw_tally(all_votes, note="cold-start: all archetypes on prior")

        mean_rep = sum(effective.values()) / len(effective)
        if mean_rep <= 0:
            return _raw_tally(all_votes, note="degenerate reputation mean")

        weights = {p: _clamp_weight(effective[p] / mean_rep) for p in personas}

        w_bull = sum(weights.get(v.get("persona"), 1.0) for v in all_votes if v.get("vote") == "bullish")
        w_bear = sum(weights.get(v.get("persona"), 1.0) for v in all_votes if v.get("vote") == "bearish")
        w_neut = sum(weights.get(v.get("persona"), 1.0) for v in all_votes if v.get("vote") == "neutral")

        return WeightedTally(
            w_bull=round(w_bull, 3), w_bear=round(w_bear, 3), w_neut=round(w_neut, 3),
            applied=True, weights={p: round(w, 3) for p, w in weights.items()},
            tiers=tiers, note=f"regime={regime or 'agnostic'}",
        )

    except Exception as e:  # noqa: BLE001 — weighting must never break a sim
        logger.warning("vote weighting failed (%s) — using raw tally", e)
        return _raw_tally(all_votes, note=f"fail-soft: {e}")
