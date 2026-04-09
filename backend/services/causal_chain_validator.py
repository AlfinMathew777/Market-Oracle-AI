"""
Causal Chain Validator
----------------------
Validates that Judge-generated causal chain slots have sufficient data.
Applies a confidence cap when too many slots contain fallback text
("No data — assumed neutral impact"), which indicates a Judge/Reconciler
timeout rather than genuine analysis.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Substrings that indicate an empty / fallback causal slot
EMPTY_CAUSAL_MARKERS = [
    "no data",
    "assumed neutral",
    "assumed neutral impact",
    "synthesis timed out",
    "timed out",
    "timeout",
    "unavailable",
    "not available",
]


def validate_causal_chain(judge_result: dict) -> dict:
    """
    Inspect the 5 causal chain slots from the judge result dict.

    Returns a validation dict with:
      - empty_slots: list of slot names that are empty or fallback
      - empty_count: int
      - total_slots: int
      - confidence_cap: float (0-1) — max confidence allowed given chain quality
      - chain_quality: "ADEQUATE" | "SPARSE" | "EMPTY"
      - reason: human-readable explanation

    Slot definitions:
      trigger_event   — the causal trigger (step 1)
      cost_impact     — direct cost impact (step 2)
      revenue_impact  — direct revenue impact (step 3)
      demand_signal   — demand outlook (step 4)
      sentiment_signal — market sentiment (step 5)
    """
    slots = {
        "trigger_event":    judge_result.get("trigger_event", ""),
        "cost_impact":      judge_result.get("cost_impact", ""),
        "revenue_impact":   judge_result.get("revenue_impact", ""),
        "demand_signal":    judge_result.get("demand_signal", ""),
        "sentiment_signal": judge_result.get("sentiment_signal", ""),
    }

    empty_slots: list[str] = []
    for slot_name, slot_text in slots.items():
        if not slot_text or not isinstance(slot_text, str) or len(slot_text.strip()) < 10:
            empty_slots.append(slot_name)
            continue
        text_lower = slot_text.lower()
        for marker in EMPTY_CAUSAL_MARKERS:
            if marker in text_lower:
                empty_slots.append(slot_name)
                break

    n_empty = len(empty_slots)
    n_slots = len(slots)

    if n_empty >= 4:
        confidence_cap = 0.25
        chain_quality = "EMPTY"
        reason = (
            f"Causal chain critically empty ({n_empty}/{n_slots} slots have no data) — "
            "likely a Judge/Reconciler timeout. Confidence capped at 25%."
        )
    elif n_empty >= 2:
        confidence_cap = 0.45
        chain_quality = "SPARSE"
        reason = (
            f"Causal chain sparse ({n_empty}/{n_slots} slots have no data). "
            "Confidence capped at 45%."
        )
    else:
        confidence_cap = 1.0
        chain_quality = "ADEQUATE"
        reason = f"Causal chain adequate ({n_slots - n_empty}/{n_slots} slots populated)."

    return {
        "empty_slots":     empty_slots,
        "empty_count":     n_empty,
        "total_slots":     n_slots,
        "confidence_cap":  confidence_cap,
        "chain_quality":   chain_quality,
        "reason":          reason,
    }


def apply_causal_chain_penalty(
    confidence: float,
    chain_validation: dict,
) -> tuple[float, Optional[str]]:
    """
    Apply the confidence cap derived from causal chain validation.

    Args:
        confidence:        Current confidence value (0–1 scale).
        chain_validation:  Output from validate_causal_chain().

    Returns:
        (capped_confidence, penalty_note)
        penalty_note is None when no cap was applied.
    """
    cap = chain_validation["confidence_cap"]
    if confidence > cap:
        capped = round(cap, 5)
        note = chain_validation["reason"]
        logger.info(
            "Causal chain penalty: %.1f%% → %.1f%% (quality=%s, empty=%d/%d)",
            confidence * 100,
            capped * 100,
            chain_validation["chain_quality"],
            chain_validation["empty_count"],
            chain_validation["total_slots"],
        )
        return capped, note
    return confidence, None
