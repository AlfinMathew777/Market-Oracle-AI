"""Outcome-fed reputation update rule (Piece 2 policy).

Turns one resolved prediction into bounded reputation nudges for the sources and
archetypes that drove it. The atomic EMA mechanics + supersede live in
ReputationStore.apply_step; this module decides target, step weight, regime, and
which cells to touch.

Design choices (all locked with the user):
  - EMA toward 1.0 on CORRECT, 0.0 on INCORRECT; clamp keeps it in [floor, ceiling].
  - step damped by margin past the noise band — a move that barely cleared ±0.5%
    is one-day noise and must not hit a thin regime cell at full strength.
  - regime collapsed to 3 buckets (down/neutral/up) to keep Option-B cells from
    starving; sources stay regime-agnostic (regime="").
  - archetype updates BOTH the (archetype, regime) cell and the (archetype, "")
    pooled record — the A-backstop that serves reads until the regime cell seasons.
  - chain_override → skip archetype updates: the causal chain, not the agents,
    made that call, so the archetypes neither earn nor lose for it. sources still
    update (they fed the prediction regardless).
  - survivorship: only CORRECT/INCORRECT update; NEUTRAL/UNVALIDATABLE/SKIPPED
    never touch reputation.
  - dissent learns (new-shape payloads carrying `archetype_votes`): every
    archetype is scored against the ACTUAL move on its OWN side — a dissenter
    that was right earns credit, one that was wrong takes the penalty. NEUTRAL
    votes never update. Legacy winner-only payloads replay EXACTLY as before,
    so old hash-chained ledger entries stay reproducible.
"""

from __future__ import annotations

import logging
from datetime import UTC

from validation.constants import MIN_MOVE_PCT

from trust.reputation import (
    ARCHETYPE,
    REPUTATION_CEILING,
    REPUTATION_FLOOR,
    SOURCE,
    ReputationStore,
)

logger = logging.getLogger(__name__)

# base EMA step — small and slow; reputation must not swing on one outcome.
BASE_ALPHA = 0.08
# move size (percent) at/above which the step is full strength.
_DECISIVE_PCT = 2.5
# floor on the damping factor so a marginal-but-real move still learns a little.
_MIN_MARGIN_FACTOR = 0.1

# EMA targets — clamp in the store keeps these inside [floor, ceiling].
_TARGET_CORRECT = 1.0
_TARGET_INCORRECT = 0.0

_UPDATING_OUTCOMES = ("CORRECT", "INCORRECT")


def collapse_regime(trend_label: str) -> str:
    """Collapse the 6 trend buckets to 3 (down/neutral/up) for Option-B cells."""
    t = (trend_label or "").upper()
    if "DOWNTREND" in t:
        return "down"
    if "UPTREND" in t:
        return "up"
    return "neutral"


def step_weight(change_pct: float) -> float:
    """Damp the EMA step by how decisively the move cleared the noise band.

    Just above ±0.5% → near the floor factor; a decisive move → full BASE_ALPHA.
    """
    margin = abs(change_pct) - MIN_MOVE_PCT
    if margin <= 0:
        return 0.0  # inside the band — not a directional outcome.
    span = _DECISIVE_PCT - MIN_MOVE_PCT
    factor = max(_MIN_MARGIN_FACTOR, min(1.0, margin / span))
    return BASE_ALPHA * factor


def _clean_counts(side: object) -> dict[str, int]:
    """Coerce a persisted side-count mapping to non-negative ints, dropping junk."""
    if not isinstance(side, dict):
        return {}
    cleaned: dict[str, int] = {}
    for name, count in side.items():
        try:
            cleaned[str(name)] = max(0, int(count))
        except (TypeError, ValueError):
            continue
    return cleaned


def archetype_steps(
    archetype_votes: dict, actual_side: str, weight: float,
) -> dict[str, tuple[float, float, str]]:
    """Per-archetype (target, step_weight, outcome_label) from all-sides votes.

    Dissent learns: each side's votes are scored against the ACTUAL direction —
    votes on `actual_side` pull toward 1.0, opposite-side votes toward 0.0, and
    NEUTRAL votes never contribute (matches survivorship semantics). The step is
    weighted by the archetype's directional vote count relative to ALL directional
    votes, so it stays inside the margin-damped BASE_ALPHA budget.

    An archetype with votes on BOTH sides gets one blended step: target is its
    correct-vote fraction, weight is its total directional share. To first order
    this equals two independent per-side EMA steps while preserving the store's
    one-sample-per-prediction supersede invariant.
    """
    # payloads are persisted attribution data — coerce defensively so a
    # malformed count can never push one archetype past the step budget
    bullish = _clean_counts(archetype_votes.get("bullish"))
    bearish = _clean_counts(archetype_votes.get("bearish"))
    total = sum(bullish.values()) + sum(bearish.values())
    if total <= 0:
        return {}
    right_side, wrong_side = (bullish, bearish) if actual_side == "bullish" else (bearish, bullish)
    steps: dict[str, tuple[float, float, str]] = {}
    for name in sorted(set(bullish) | set(bearish)):
        right = right_side.get(name, 0)
        wrong = wrong_side.get(name, 0)
        votes = right + wrong
        if votes <= 0:
            continue
        label = "CORRECT" if wrong == 0 else ("INCORRECT" if right == 0 else "MIXED")
        steps[name] = (right / votes, weight * votes / total, label)
    return steps


async def _apply_archetype_updates(
    store: ReputationStore, *, prediction_id: str, attribution: dict, target: float,
    weight: float, outcome: str, change_pct: float, regime: str, stage: str,
    updated_at: str,
) -> int:
    """Update archetype cells; returns how many archetypes were stepped.

    New-shape payloads (with `archetype_votes`) score every side against the
    actual move; legacy winner-only payloads replay the original rule EXACTLY
    (full-weight step toward the final-direction target) so old hash-chained
    ledger entries remain reproducible.
    """
    votes = attribution.get("archetype_votes")
    if isinstance(votes, dict):
        actual_side = "bullish" if change_pct > 0 else "bearish"
        plan = [
            (name, tgt, w, label)
            for name, (tgt, w, label) in archetype_steps(votes, actual_side, weight).items()
        ]
    else:  # legacy shape — behavior unchanged.
        plan = [(a, target, weight, outcome) for a in (attribution.get("driving_archetypes") or {})]

    for name, tgt, w, label in plan:
        for cell_regime in (regime, ""):  # B cell + A-backstop pooled record
            await store.apply_step(
                prediction_id=prediction_id, identity=name, kind=ARCHETYPE,
                target=tgt, weight=w, outcome=label, stage=stage,
                regime=cell_regime, updated_at=updated_at,
            )
    return len(plan)


async def apply_outcome(
    store: ReputationStore,
    *,
    prediction_id: str,
    attribution: dict,
    outcome: str,
    change_pct: float,
    stage: str,
    updated_at: str,
) -> dict:
    """Apply one resolved outcome to the reputation of its drivers.

    Returns a small summary for the audit/before-after table. A no-op (survivorship
    or no drivers) returns counts of zero — never raises.
    """
    if outcome not in _UPDATING_OUTCOMES:
        return {"updated": False, "reason": f"non-directional outcome {outcome}"}

    target = _TARGET_CORRECT if outcome == "CORRECT" else _TARGET_INCORRECT
    weight = step_weight(change_pct)
    if weight <= 0.0:
        return {"updated": False, "reason": "move inside noise band"}

    regime = collapse_regime(attribution.get("trend_label", ""))
    sources_done = 0
    archetypes_done = 0

    for src in attribution.get("sources", []) or []:
        sid = src.get("source_id") if isinstance(src, dict) else None
        if not sid:
            continue
        await store.apply_step(
            prediction_id=prediction_id, identity=sid, kind=SOURCE,
            target=target, weight=weight, outcome=outcome, stage=stage,
            regime="", updated_at=updated_at,
        )
        sources_done += 1

    # chain override → the chain made the call, not the archetypes; skip them.
    if not attribution.get("chain_override"):
        archetypes_done = await _apply_archetype_updates(
            store, prediction_id=prediction_id, attribution=attribution,
            target=target, weight=weight, outcome=outcome, change_pct=change_pct,
            regime=regime, stage=stage, updated_at=updated_at,
        )

    return {
        "updated": True,
        "outcome": outcome,
        "regime": regime,
        "weight": round(weight, 4),
        "sources_updated": sources_done,
        "archetypes_updated": archetypes_done,
    }


async def resolve_and_update(
    store: ReputationStore,
    ledger,
    *,
    simulation_id: str,
    prediction_id: str,
    outcome: str,
    change_pct: float,
    stage: str,
    updated_at: str,
) -> dict:
    """Resolver-facing entry: join attribution by simulation_id, then update.

    Fail-closed: no attribution recorded → no update (the loop simply has nothing
    to attribute). Any error is logged and swallowed — reputation must never break
    or delay outcome resolution.
    """
    try:
        attribution = await ledger.find_attribution(simulation_id)
        if not attribution:
            return {"updated": False, "reason": "no attribution for simulation_id"}
        return await apply_outcome(
            store, prediction_id=prediction_id, attribution=attribution,
            outcome=outcome, change_pct=change_pct, stage=stage, updated_at=updated_at,
        )
    except Exception as e:  # noqa: BLE001 — never break resolution.
        logger.warning("reputation update failed for %s: %s", prediction_id, e)
        return {"updated": False, "reason": f"error: {e}"}


async def update_from_resolution(
    *, simulation_id: str, prediction_id: str, outcome: str,
    change_pct: float, stage: str, updated_at: str | None = None,
) -> dict:
    """One-liner for resolvers — fetches the shared store/ledger, then updates.

    Fail-closed everywhere: a missing simulation_id, an init failure, or any error
    returns a no-op dict and never raises into the resolution path.
    """
    if not simulation_id:
        return {"updated": False, "reason": "no simulation_id on row"}
    try:
        from datetime import datetime

        from trust import get_ledger, get_reputation_store

        store = await get_reputation_store()
        ledger = await get_ledger()
        ts = updated_at or datetime.now(UTC).isoformat()
    except Exception as e:  # noqa: BLE001 — never break resolution.
        logger.warning("reputation update could not initialise: %s", e)
        return {"updated": False, "reason": "init failed"}
    return await resolve_and_update(
        store, ledger, simulation_id=simulation_id, prediction_id=prediction_id,
        outcome=outcome, change_pct=change_pct, stage=stage, updated_at=ts,
    )


# protective bounds re-exported so callers can assert on them without reaching in.
__all__ = [
    "BASE_ALPHA", "REPUTATION_FLOOR", "REPUTATION_CEILING",
    "archetype_steps", "collapse_regime", "step_weight", "apply_outcome",
    "resolve_and_update", "update_from_resolution",
]
