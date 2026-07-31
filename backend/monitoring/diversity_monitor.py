"""Cognitive diversity monitor — anti-monoculture instrumentation.

The CFA AI Transition Framework's central systemic worry is "cognitive
convergence": shared model architectures producing correlated signals that
fail together. The swarm rotates agents across model families (ensemble
diversity), but rotation only helps if the families actually think
differently. This module MEASURES that.

Design notes:
  - Providers are collapsed to model FAMILIES: groq-70b and groq-8b are both
    Llama models — routing between them is load-balancing, not diversity.
  - Agreement is computed only over FREE personas (quant, neutral_fund).
    macro_bull / geo_bear are forced-vote adversarial roles — their direction
    is persona-determined, so counting them would measure the persona mix,
    not model thinking.
  - convergence = (how often family majorities agree) x (how internally
    unanimous families are). diversity_score = 1 - convergence.
    A high score means families genuinely disagree (healthy adversarial
    ensemble); a score near 0 means a monoculture wearing several hats.
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any

logger = logging.getLogger(__name__)

# Personas whose direction is NOT forced by their role.
FREE_PERSONAS = ("quant", "neutral_fund")

# Convergence thresholds (only meaningful with >= 2 families voting).
CONVERGENCE_HIGH = 0.85
CONVERGENCE_MODERATE = 0.70

_MIN_VOTES_PER_FAMILY = 2


def provider_family(provider: str | None) -> str | None:
    """Collapse a provider name to its model family."""
    if not provider:
        return None
    name = provider.lower()
    if name.startswith("groq"):
        return "llama"  # both Groq tiers serve Llama-family models
    if "gemini" in name:
        return "gemini"
    if "openrouter" in name:
        return "openrouter"
    return name


def diversity_report(all_votes: list[dict]) -> dict[str, Any]:
    """Measure cross-family cognitive diversity for one simulation's votes.

    Args:
        all_votes: vote dicts with "vote", "persona", and "provider" keys
                   (provider is None for legacy/mocked routers).

    Returns:
        Dict with per-family tallies, convergence, diversity_score, and a
        monoculture_risk label:
          - "UNMEASURED": no provider data (legacy path) or < 2 families
          - "LOW" / "MODERATE" / "HIGH": measured convergence bands
    """
    families: dict[str, dict[str, int]] = {}
    for vote in all_votes or []:
        family = provider_family(vote.get("provider"))
        if family is None or vote.get("persona") not in FREE_PERSONAS:
            continue
        tally = families.setdefault(family, {"bullish": 0, "bearish": 0, "neutral": 0})
        direction = str(vote.get("vote") or "").lower()
        if direction in tally:
            tally[direction] += 1

    # Only families with enough free votes to have a meaningful majority.
    measurable = {
        fam: tally for fam, tally in families.items()
        if sum(tally.values()) >= _MIN_VOTES_PER_FAMILY
    }

    if len(measurable) < 2:
        return {
            "monoculture_risk": "UNMEASURED",
            "diversity_score": None,
            "convergence": None,
            "n_families": len(measurable),
            "families": families,
            "note": (
                "need >= 2 model families with >= "
                f"{_MIN_VOTES_PER_FAMILY} free-persona votes each"
            ),
        }

    majorities: dict[str, str] = {}
    internal_consensus: dict[str, float] = {}
    for fam, tally in measurable.items():
        total = sum(tally.values())
        majority_dir = max(tally, key=lambda d: tally[d])
        majorities[fam] = majority_dir
        internal_consensus[fam] = tally[majority_dir] / total

    pairs = list(combinations(sorted(measurable), 2))
    agreeing = sum(1 for a, b in pairs if majorities[a] == majorities[b])
    agreement_ratio = agreeing / len(pairs)
    mean_consensus = sum(internal_consensus.values()) / len(internal_consensus)

    convergence = round(agreement_ratio * mean_consensus, 3)
    diversity_score = round(1.0 - convergence, 3)

    if convergence >= CONVERGENCE_HIGH:
        risk = "HIGH"
    elif convergence >= CONVERGENCE_MODERATE:
        risk = "MODERATE"
    else:
        risk = "LOW"

    return {
        "monoculture_risk": risk,
        "diversity_score": diversity_score,
        "convergence": convergence,
        "agreement_ratio": round(agreement_ratio, 3),
        "mean_internal_consensus": round(mean_consensus, 3),
        "n_families": len(measurable),
        "family_majorities": majorities,
        "families": families,
        "note": "",
    }


async def maybe_alert_monoculture(report: dict[str, Any], ticker: str) -> None:
    """Fire a COGNITIVE_MONOCULTURE alert when convergence is HIGH.

    Best-effort: alerting failures are logged and swallowed — a monitoring
    signal must never break the simulation that produced it.
    """
    if report.get("monoculture_risk") != "HIGH":
        return
    try:
        from monitoring.alerts import COGNITIVE_MONOCULTURE, _fire_alert

        await _fire_alert(
            COGNITIVE_MONOCULTURE,
            "warning",
            (
                f"Model families converged on {ticker}: convergence="
                f"{report.get('convergence')} across {report.get('n_families')} "
                "families — ensemble diversity is not providing independent views"
            ),
            context={
                "ticker": ticker,
                "convergence": report.get("convergence"),
                "family_majorities": report.get("family_majorities"),
            },
            dedup_key=ticker,
        )
    except Exception as e:  # noqa: BLE001 — alerting never breaks a simulation
        logger.warning("monoculture alert failed (non-fatal): %s", e)
