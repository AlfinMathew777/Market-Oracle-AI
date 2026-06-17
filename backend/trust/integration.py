"""Adapters that connect the trust gateway to the project's prediction shapes.

Keeps the route handlers thin: a route hands in its native object, gets back a
TrustCertificate. Mapping logic that knows about ReasoningOutput / test_core
dicts lives here, not in the gateway (which only speaks TrustContext).
"""

from __future__ import annotations

import logging
from typing import Any

from trust import build_context, get_gateway
from trust.contracts import TrustCertificate

logger = logging.getLogger(__name__)

# A FRAGILE consensus maps to a low Monte-Carlo-equivalent stability so the
# Validation layer's V3 stability check can fire on synthesizer output.
_STABILITY_MAP = {"STABLE": 0.80, "FRAGILE": 0.20}


def _provenance_ages(provenance: dict) -> dict:
    """Pull {feed: age_seconds} from a data_provenance dict if it carries ages."""
    ages: dict = {}
    for key, val in (provenance or {}).items():
        if isinstance(val, dict) and "age_seconds" in val:
            try:
                ages[key] = float(val["age_seconds"])
            except (TypeError, ValueError):
                continue
    return ages


def reasoning_to_prediction(result: Any, *, news_headline: str = "") -> dict:
    """Flatten a ReasoningOutput into the dict shape build_context understands."""
    fd = result.final_decision
    cc = result.causal_chain
    ca = result.consensus_analysis
    return {
        "ticker": result.stock_ticker,
        "direction": fd.direction.value,                 # Bullish/Bearish/Neutral
        "confidence": fd.confidence_score / 100.0,        # 0-100 → 0-1
        "signal_order": "primary",
        "catalyst": news_headline or cc.summary,
        "agent_votes": {
            "bull": ca.bullish, "bear": ca.bearish, "neut": ca.neutral,
        },
        "mc_stability": _STABILITY_MAP.get(ca.stability.value.upper(), 0.5),
        "judge_result": {
            "trigger_event": cc.summary,
            "cost_impact": cc.cost_impact,
            "revenue_impact": cc.revenue_impact,
            "demand_signal": cc.demand_impact,
            "sentiment_signal": cc.sentiment_impact,
        },
        "data_feeds": _provenance_ages(result.data_provenance),
        "market_context": result.market_context.commodity_signals
        if result.market_context else {},
        # one news trigger ⇒ sanitized + single-source (capped, labeled uncorroborated).
        "input_provenance": _input_provenance(
            [news_headline or cc.summary], [{"source_id": "news_trigger"}],
        ),
    }


def _input_provenance(text_blocks: list[str], sources: list[dict]) -> dict:
    """Build an input-trust record by sanitizing untrusted text + assessing sources.

    The gateway's InputLayer enforces this. A directional prediction with no record
    fails closed, so every certified path must produce one.
    """
    from trust.constitution import THRESHOLDS
    from trust.contracts import WRAP_FULL, WRAP_NONE
    from trust.input import assess_corroboration, sanitize_external_text

    flags: set = set()
    neutralized = 0
    blocks = [t for t in text_blocks if t]
    for t in blocks:
        s = sanitize_external_text(t)
        flags.update(s.normalization_flags)
        neutralized += s.instructions_neutralized
    corr = assess_corroboration(
        sources or [], min_reputation=THRESHOLDS.min_source_reputation,
        low_rep_cluster_min=THRESHOLDS.low_rep_cluster_min,
    )
    return {
        "sanitized": True,
        # reasoning wraps its single trigger block — full coverage for that path.
        "wrapped_status": WRAP_FULL if blocks else WRAP_NONE,
        "evasion_flags": sorted(flags),
        "instructions_neutralized": neutralized,
        "model_generated_cited": False,
        "independent_origins": corr.independent_origins,
        "single_source": corr.single_source,
        "low_rep_cluster": corr.low_rep_cluster,
    }


async def certify_reasoning(result: Any, *, news_headline: str = "") -> TrustCertificate:
    """Run a ReasoningOutput through the 5-layer trust gateway."""
    gateway = await get_gateway()
    prediction = reasoning_to_prediction(result, news_headline=news_headline)
    ctx = build_context(prediction)
    return await gateway.evaluate(ctx)


# swarm directions use UP/DOWN; the gateway speaks BULLISH/BEARISH.
_SWARM_DIRECTION = {"UP": "BULLISH", "DOWN": "BEARISH", "NEUTRAL": "NEUTRAL"}


def simulation_to_prediction(pred: dict) -> dict:
    """Flatten a swarm prediction dict into the shape build_context understands.

    Tolerant of both the full report and the partial-fallback shape — pulls fields
    by their swarm names and maps UP/DOWN to the gateway's direction vocabulary.
    """
    raw_dir = str(pred.get("direction") or "NEUTRAL").upper()
    consensus = pred.get("agent_consensus") or {}
    qa = pred.get("quality_assessment") or {}
    causal = pred.get("causal_chain")
    # swarm causal_chain is a list of steps; the gateway wants a dict it can scan.
    judge = causal if isinstance(causal, dict) else {"trigger_event": pred.get("trigger_event", "")}
    mc_pct = qa.get("mc_stability_pct")
    hist_pct = qa.get("historical_accuracy_pct")
    return {
        "ticker": pred.get("ticker") or "UNKNOWN",
        "direction": _SWARM_DIRECTION.get(raw_dir, raw_dir),
        "confidence": pred.get("confidence", 0.0),
        "signal_order": pred.get("signal_order") or "primary",
        "catalyst": pred.get("trigger_event") or "",
        "agent_votes": {
            "bull": consensus.get("up", 0),
            "bear": consensus.get("down", 0),
            "neut": consensus.get("neutral", 0),
        },
        "mc_stability": (mc_pct / 100.0) if mc_pct is not None else 1.0,
        "historical_accuracy": (hist_pct / 100.0) if hist_pct is not None else 1.0,
        "judge_result": judge,
        # recorded by the swarm at ingestion; None ⇒ fail closed at the gateway.
        "input_provenance": pred.get("input_provenance"),
    }


async def certify_simulation(pred: dict) -> TrustCertificate:
    """Run a swarm prediction dict through the same 5-layer trust gateway."""
    gateway = await get_gateway()
    ctx = build_context(simulation_to_prediction(pred))
    return await gateway.evaluate(ctx)
