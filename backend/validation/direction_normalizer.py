"""
Direction token normaliser for prediction_log entries.

Two code paths have historically written different direction vocabularies to the DB:
  - database.save_prediction_log()  → "bullish" / "bearish" / "neutral"
  - test_core._save_prediction()    → "up" / "down" / "neutral"  (legacy)

This module is the single source of truth for what each token means.
All validation and reporting code MUST use normalize_direction() instead of
hard-coding token comparisons.
"""

from __future__ import annotations

from typing import Literal, Optional

# Canonical output values
Direction = Literal["bullish", "bearish", "neutral", "unvalidatable"]

# Token sets — extend here when new aliases appear
BULLISH_TOKENS: frozenset[str] = frozenset({"bullish", "up", "buy", "long", "positive"})
BEARISH_TOKENS: frozenset[str] = frozenset({"bearish", "down", "sell", "short", "negative"})
NEUTRAL_TOKENS: frozenset[str] = frozenset({"neutral", "hold", "sideways", "flat", "unclear"})


def normalize_direction(raw: Optional[str]) -> Direction:
    """
    Map any direction token to its canonical form.

    Returns:
        "bullish"        — token is in BULLISH_TOKENS
        "bearish"        — token is in BEARISH_TOKENS
        "neutral"        — token is in NEUTRAL_TOKENS
        "unvalidatable"  — token is None, empty, or unrecognised
    """
    if not raw:
        return "unvalidatable"
    token = raw.strip().lower()
    if token in BULLISH_TOKENS:
        return "bullish"
    if token in BEARISH_TOKENS:
        return "bearish"
    if token in NEUTRAL_TOKENS:
        return "neutral"
    return "unvalidatable"


def is_actionable(direction: Direction) -> bool:
    """
    Return True only for directions that carry a testable market prediction.

    neutral and unvalidatable have no pass/fail outcome — they should be
    excluded from hit-rate calculations and never scored as INCORRECT.
    """
    return direction in ("bullish", "bearish")
