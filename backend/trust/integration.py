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
    }


async def certify_reasoning(result: Any, *, news_headline: str = "") -> TrustCertificate:
    """Run a ReasoningOutput through the 5-layer trust gateway."""
    gateway = await get_gateway()
    prediction = reasoning_to_prediction(result, news_headline=news_headline)
    ctx = build_context(prediction)
    return await gateway.evaluate(ctx)
