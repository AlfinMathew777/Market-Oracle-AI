"""Attribution — record what drove each prediction, for the reputation loop.

At the end of a swarm run, after the reconciler settles the final call, we append
one attribution entry to the existing hash-chained ledger (free-form JSON, no
migration). When the outcome later resolves, Piece 2 loads this entry by
simulation_id and nudges the reputation of the sources and archetypes that drove
the call.

Join key is simulation_id — the SAME key the prediction_log row carries and
outcome_checker resolves on. Without that join the loop cannot close.

What we record (only what moved the call, not 25 agents' chatter):
  - driving_archetypes : the 4-role counts on the side matching the final direction
  - chain_override     : true when the causal chain overrode the agent majority —
                         in that case the chain, not the archetypes, made the call
  - vote_moving_claims : the directional causal-chain slots + trigger
  - sources            : the stable source roster that fed the prediction (the
                         load-bearing half — source reputation updates from this)

agent_id is never recorded as an identity — it is a per-run enumeration index,
meaningless across runs. Archetype is the only stable agent key.

RESEARCH-TODO: per-claim source linkage is coarse. v1 attaches the run source
roster to each claim (KNOWN-WEAK); we know these sources fed the prediction, not
yet which claim each one backs. Source reputation only needs the roster, so this
does not block Piece 2.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ATTRIBUTION_DECISION = "ATTRIBUTION"

# the 4 stable voting roles. judge reconciles and does not vote.
_ARCHETYPES = ("macro_bull", "geo_bear", "quant", "neutral_fund")

# directional causal slots the reconciler reasons over.
_CLAIM_SLOTS = ("cost_impact", "revenue_impact", "demand_impact", "sentiment_impact")

_DIRECTION_TO_SIDE = {"UP": "bullish", "DOWN": "bearish", "NEUTRAL": "neutral"}


def _winning_archetypes(all_votes: list[dict], side: str) -> dict[str, int]:
    """Count the 4 roles among votes on the side matching the final direction."""
    counts: dict[str, int] = {}
    for v in all_votes or []:
        if v.get("vote") != side:
            continue
        persona = v.get("persona")
        if persona in _ARCHETYPES:
            counts[persona] = counts.get(persona, 0) + 1
    return counts


def _source_id(item: dict) -> str | None:
    """Stable origin id from a news item — explicit source, else url host."""
    src = (item.get("source") or "").strip().lower()
    if src:
        return src
    url = item.get("url") or item.get("link") or ""
    host = urlparse(url).netloc.lower()
    return host or None


def _source_roster(news_items: list[dict], alt_data: dict | None) -> list[dict]:
    """Distinct source ids that fed the run, with a coarse weight where present."""
    roster: dict[str, float] = {}
    for item in news_items or []:
        sid = _source_id(item)
        if not sid:
            continue
        weight = float(item.get("weight", 0.0) or 0.0)
        roster[sid] = max(roster.get(sid, 0.0), weight)
    # alt-data per_source keys are stable DataSource names (reddit_sentiment, ...).
    for sid in ((alt_data or {}).get("per_source") or {}):
        sid = str(sid).strip().lower()
        if sid:
            roster.setdefault(sid, 0.0)
    return [{"source_id": sid, "weight": round(w, 3)} for sid, w in sorted(roster.items())]


def _vote_moving_claims(judge_result: dict, source_ids: list[str]) -> list[dict]:
    """Directional causal slots + trigger, each tagged with the source roster."""
    claims: list[dict] = []
    trigger = (judge_result.get("trigger_event") or "").strip()
    if trigger:
        claims.append({"slot": "trigger", "claim": trigger[:300], "source_ids": source_ids})
    for slot in _CLAIM_SLOTS:
        text = (judge_result.get(slot) or "").strip()
        if text and "no data" not in text.lower():
            claims.append({"slot": slot, "claim": text[:300], "source_ids": source_ids})
    return claims


def build_attribution(
    *,
    simulation_id: str,
    ticker: str,
    direction: str,
    confidence: float,
    all_votes: list[dict],
    judge_result: dict,
    news_items: list[dict] | None = None,
    alt_data: dict | None = None,
    chain_override: bool = False,
    trend_label: str = "",
) -> dict[str, Any]:
    """Build the attribution payload. Pure; tolerant of missing pieces."""
    side = _DIRECTION_TO_SIDE.get((direction or "").upper(), "neutral")
    roster = _source_roster(news_items or [], alt_data)
    source_ids = [s["source_id"] for s in roster]
    return {
        "type": "attribution",
        "simulation_id": simulation_id,
        "ticker": ticker,
        "direction": (direction or "NEUTRAL").upper(),
        "confidence": round(float(confidence or 0.0), 4),
        "trend_label": trend_label,
        # true → the causal chain, not the archetypes, made the final call.
        "chain_override": bool(chain_override),
        "driving_archetypes": _winning_archetypes(all_votes, side),
        "vote_moving_claims": _vote_moving_claims(judge_result or {}, source_ids),
        "sources": roster,
    }


async def append_attribution(ledger, payload: dict, *, issued_at: str) -> None:
    """Append an attribution entry to the hash-chained ledger.

    Fail-closed: an append failure is logged and swallowed — attribution is never
    allowed to crash or delay a live prediction. A missing entry simply means the
    outcome later finds nothing to attribute and reputation is left unchanged.
    """
    try:
        await ledger.append(
            payload,
            ticker=payload.get("ticker", "UNKNOWN"),
            decision=ATTRIBUTION_DECISION,
            trust_score=0,
            issued_at=issued_at,
        )
    except Exception as e:  # noqa: BLE001 — attribution must never break a sim.
        logger.warning("attribution append failed for %s: %s", payload.get("simulation_id"), e)
