"""Catalyst validator for Market Oracle AI.

A valid catalyst is a specific, recently-identifiable event that could
move a stock. Generic phrases like "None", "no direct impact", or
"general market conditions" are NOT valid catalysts.

Directional trading signals (BUY/SELL) should only be generated when
a concrete catalyst backs the thesis.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


# ── Patterns that indicate NO real catalyst ────────────────────────────────────
_NO_CATALYST_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*none\s*$", re.I),
    re.compile(r"^\s*n/?a\s*$", re.I),
    re.compile(r"^no\s+catalyst", re.I),
    re.compile(r"^no\s+specific", re.I),
    re.compile(r"^no\s+direct", re.I),
    re.compile(r"^general\s+market", re.I),
    re.compile(r"^market\s+condition", re.I),
    re.compile(r"^(broad\s+)?(technical|momentum|trend)\b", re.I),
    re.compile(r"^no\s+\w+\s+identified", re.I),
    re.compile(r"given\s+the\s+\w+\s+has\s+no\s+direct\s+impact", re.I),
    re.compile(r"no\s+identifiable\s+catalyst", re.I),
    re.compile(r"insufficient\s+data", re.I),
    re.compile(r"^unclear\s*$", re.I),
    re.compile(r"^unknown\s*$", re.I),
]

# ── Keywords that suggest a REAL catalyst ─────────────────────────────────────
_VALID_CATALYST_KEYWORDS: list[str] = [
    # Corporate events
    "announce", "report", "earnings", "guidance", "forecast",
    "merger", "acquisition", "deal", "contract", "bid", "tender",
    "ceo", "board", "management", "resign", "appoint",
    "dividend", "buyback", "capital raising",
    # Macro / policy
    "rba", "fed", "rate", "policy", "inflation", "gdp",
    "tariff", "sanction", "restriction", "ban", "quota",
    "stimulus", "infrastructure", "budget",
    # Commodity / sector
    "iron ore", "oil", "lng", "gas", "coal", "copper", "lithium",
    "freight", "shipping", "port", "pilbara", "china",
    # Market events
    "crash", "rally", "selloff", "surge", "plunge",
    "downgrade", "upgrade", "rating", "analyst",
    # Geopolitical
    "war", "conflict", "sanction", "blockade", "disaster", "earthquake",
]

# ── Specificity patterns — at least one needed ────────────────────────────────
_SPECIFICITY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\d"),           # Contains any digit
    re.compile(r"\$\d"),         # Dollar amount
    re.compile(r"\d{4}"),        # Year
    re.compile(r"[A-Z]{2,}"),    # Acronyms (e.g. RBA, ASX, BHP)
    re.compile(r"\b\w+\.\w+"),   # Dot-notation (e.g. BHP.AX)
    re.compile(r"%"),            # Percentage
]


def validate_catalyst(trigger_event: str) -> Tuple[bool, str]:
    """Determine whether a trigger event represents a real, actionable catalyst.

    Args:
        trigger_event: The trigger_event string from the Judge agent.

    Returns:
        (is_valid, reason) tuple.
        is_valid=True when the trigger is specific and recognisable.
    """
    if not trigger_event or not trigger_event.strip():
        return False, "No trigger event provided"

    text = trigger_event.strip()

    # Check against explicit no-catalyst patterns first
    for pattern in _NO_CATALYST_PATTERNS:
        if pattern.search(text):
            return False, f"Trigger indicates no catalyst: '{text[:60]}'"

    text_lower = text.lower()

    # Must contain at least one recognised catalyst keyword
    has_keyword = any(kw in text_lower for kw in _VALID_CATALYST_KEYWORDS)
    if not has_keyword:
        return False, f"No recognised catalyst keyword in: '{text[:60]}'"

    # Must have some specificity (number, acronym, percentage, etc.)
    has_specifics = any(p.search(text) for p in _SPECIFICITY_PATTERNS)
    if not has_specifics:
        return False, f"Trigger lacks specifics (dates/amounts/tickers): '{text[:60]}'"

    logger.debug("Valid catalyst: '%s'", text[:80])
    return True, "Valid catalyst identified"


def catalyst_strength(trigger_event: str) -> str:
    """Estimate catalyst impact strength: HIGH / MEDIUM / LOW."""
    if not trigger_event:
        return "NONE"

    text_lower = trigger_event.lower()

    _HIGH = ["war", "sanction", "ban", "crash", "collapse", "emergency",
             "crisis", "catastrophe", "shutdown", "blockade"]
    if any(kw in text_lower for kw in _HIGH):
        return "HIGH"

    _MEDIUM = ["tariff", "rate", "earnings", "guidance", "merger",
               "acquisition", "downgrade", "upgrade", "deficit", "surplus"]
    if any(kw in text_lower for kw in _MEDIUM):
        return "MEDIUM"

    return "LOW"
