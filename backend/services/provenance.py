"""Prediction provenance — one auditable document per prediction.

CFA AI Transition Framework imperative #1 (traceability in hybrid decision
systems): "model-assisted conclusions can be explained, challenged, and
attributed." Every piece already exists — the prediction_log row, the trust
attribution in the hash-chained ledger, the full simulation JSON with votes
and confidence audit, and the chain-integrity proof. This module assembles
them into ONE document: the artifact you hand a diligence team or a regulator.

Read-only and fail-soft: each section is fetched independently; a missing
section is reported as absent, never fabricated, and never fails the others.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _swarm_section(full_json: dict | None, prediction: dict | None) -> dict[str, Any]:
    """Vote counts, weighting audit, and per-provider breakdown."""
    section: dict[str, Any] = {}
    if prediction:
        section["vote_counts"] = {
            "bullish": prediction.get("agent_bullish"),
            "bearish": prediction.get("agent_bearish"),
            "neutral": prediction.get("agent_neutral"),
        }
    if not full_json:
        return section

    audit = full_json.get("confidence_audit") or {}
    if audit.get("reputation_weighting"):
        section["reputation_weighting"] = audit["reputation_weighting"]
    if full_json.get("persona_distribution"):
        section["persona_distribution"] = full_json["persona_distribution"]
    if full_json.get("cognitive_diversity"):
        section["cognitive_diversity"] = full_json["cognitive_diversity"]

    # Per-provider vote breakdown (ensemble diversity evidence): prefer the
    # compact persisted tally; fall back to recomputing from raw votes when
    # an older record carries all_votes instead.
    providers: dict[str, dict[str, int]] = full_json.get("votes_by_provider") or {}
    if not providers:
        for vote in full_json.get("all_votes") or []:
            provider = vote.get("provider") or "unrecorded"
            tally = providers.setdefault(provider, {"bullish": 0, "bearish": 0, "neutral": 0})
            direction = str(vote.get("vote") or "").lower()
            if direction in tally:
                tally[direction] += 1
    if providers:
        section["votes_by_provider"] = providers
    return section


def _decision_section(prediction: dict | None, full_json: dict | None) -> dict[str, Any]:
    section: dict[str, Any] = {}
    if prediction:
        section.update({
            "direction": prediction.get("predicted_direction"),
            "confidence": prediction.get("confidence"),
            "predicted_at": prediction.get("predicted_at"),
            "primary_reason": prediction.get("primary_reason"),
            "trend_label": prediction.get("trend_label"),
            "excluded_from_stats": bool(prediction.get("excluded_from_stats")),
        })
    if full_json:
        section["confidence_audit"] = full_json.get("confidence_audit")
        section["signal_grade"] = full_json.get("signal_grade")
        section["is_actionable"] = full_json.get("is_actionable")
        section["chain_override"] = full_json.get("chain_override_flag")
        section["regime_drift"] = full_json.get("regime_drift")
        section["trust"] = full_json.get("trust")
    return section


def _outcome_section(prediction: dict | None) -> dict[str, Any]:
    if not prediction:
        return {}
    resolved = prediction.get("actual_direction") is not None
    return {
        "resolved": resolved,
        "actual_direction": prediction.get("actual_direction"),
        "actual_price_change_pct": prediction.get("actual_price_change_pct"),
        "prediction_correct": prediction.get("prediction_correct"),
        "resolved_at": prediction.get("resolved_at"),
        "lesson": prediction.get("lesson"),
        "resolution_notes": prediction.get("resolution_notes"),
    }


async def build_provenance(simulation_id: str) -> dict[str, Any] | None:
    """Assemble the full provenance document for one prediction.

    Returns None only when the prediction is entirely unknown (no
    prediction_log row AND no simulation record).
    """
    prediction: dict | None = None
    full_json: dict | None = None
    attribution: dict | None = None
    integrity: dict[str, Any] = {"verified": False, "note": "not checked"}

    try:
        from database import get_prediction_by_simulation_id
        prediction = await get_prediction_by_simulation_id(simulation_id)
    except Exception as e:  # noqa: BLE001 — each section independent
        logger.warning("provenance: prediction fetch failed for %s: %s", simulation_id, e)

    try:
        from database import get_simulation_full_json
        full_json = await get_simulation_full_json(simulation_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("provenance: simulation fetch failed for %s: %s", simulation_id, e)

    try:
        from trust import get_ledger
        ledger = await get_ledger()
        attribution = await ledger.find_attribution(simulation_id)
        intact, first_broken = await ledger.verify_chain()
        integrity = {
            "verified": True,
            "chain_intact": intact,
            "first_broken_seq": first_broken,
            "note": (
                "hash chain re-walked and verified"
                if intact
                else f"TAMPER EVIDENT: chain breaks at seq {first_broken}"
            ),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("provenance: ledger read failed for %s: %s", simulation_id, e)
        integrity = {"verified": False, "note": f"ledger unavailable: {e}"}

    if prediction is None and full_json is None:
        return None

    return {
        "simulation_id": simulation_id,
        "ticker": (prediction or {}).get("ticker") or (full_json or {}).get("ticker"),
        "decision": _decision_section(prediction, full_json),
        "swarm": _swarm_section(full_json, prediction),
        "evidence": {
            "attribution": attribution,
            "note": (
                "" if attribution
                else "no attribution entry recorded for this simulation_id"
            ),
        },
        "outcome": _outcome_section(prediction),
        "ledger_integrity": integrity,
        "sections_present": {
            "prediction_log": prediction is not None,
            "simulation_json": full_json is not None,
            "attribution": attribution is not None,
        },
    }
