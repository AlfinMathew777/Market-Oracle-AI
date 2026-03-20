"""Semantic ASX ticker mapper using Zep Cloud knowledge graph.

Replaces the 15-rule event_ticker_mapping.py with graph-based semantic search.
Falls back to rule-based mapper if Zep is unavailable or returns no results.

Graph ID: 'aussieintel_v1' (seeded by scripts/seed_asx_knowledge_graph.py)
"""

import os
import logging
import asyncio
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_ZEP_KEY  = os.environ.get("ZEP_API_KEY", "")
_GRAPH_ID = "aussieintel_v1"

# All valid ASX tickers tracked by the platform
VALID_TICKERS = {
    "BHP.AX", "RIO.AX", "FMG.AX",           # Iron ore / diversified
    "WDS.AX", "STO.AX",                       # LNG / Energy
    "MIN.AX", "PLS.AX",                       # Lithium
    "CBA.AX", "WBC.AX", "ANZ.AX", "NAB.AX",  # Banks
    "NST.AX", "EVN.AX",                       # Gold
    "WES.AX", "WOW.AX",                       # Retail
    "LYC.AX",                                  # Rare Earths
}


async def map_event_to_ticker(event: dict) -> Tuple[str, float, str]:
    """
    Map a conflict/geopolitical event to the most relevant ASX ticker.

    Args:
        event: dict with keys: country, event_type, notes/description,
               latitude, longitude, fatalities (optional)

    Returns:
        (ticker, confidence, reasoning) — e.g. ("WDS.AX", 0.85, "Iran/Hormuz → LNG price spike")
    """
    query = _build_query(event)

    # Try Zep semantic search first
    if _ZEP_KEY:
        try:
            result = await _zep_search(query, event)
            if result:
                return result
        except Exception as e:
            logger.warning("Zep search failed (%s) — falling back to rules", e)

    # Rule-based fallback
    from event_ticker_mapping import map_event_to_ticker as rule_mapper
    ticker = rule_mapper(event) or "BHP.AX"
    return ticker, 0.5, "rule-based fallback"


def _build_query(event: dict) -> str:
    """Construct a natural-language search query from event fields."""
    parts = []
    if event.get("country"):
        parts.append(event["country"])
    if event.get("event_type"):
        parts.append(event["event_type"])
    if event.get("notes"):
        parts.append(str(event["notes"])[:200])
    elif event.get("location"):
        parts.append(str(event["location"])[:100])
    return " ".join(parts)


async def _zep_search(query: str, event: dict) -> Optional[Tuple[str, float, str]]:
    """Query Zep graph and use LLM to select the best ASX ticker from results."""
    from zep_cloud.client import Zep

    loop = asyncio.get_event_loop()
    client = Zep(api_key=_ZEP_KEY)

    # Search the knowledge graph
    results = await loop.run_in_executor(
        None,
        lambda: client.graph.search(
            graph_id=_GRAPH_ID,
            query=query,
            limit=5,
        ),
    )

    if not results or not results.results:
        return None

    # Build context from top search results
    context_snippets = [r.fact for r in results.results[:5] if hasattr(r, "fact") and r.fact]
    if not context_snippets:
        # Try edges attribute
        for r in results.results[:5]:
            if hasattr(r, "content"):
                context_snippets.append(r.content)

    if not context_snippets:
        return None

    context = "\n".join(f"- {s}" for s in context_snippets)

    # Use LLM to select best ticker from graph results
    ticker, confidence, reasoning = await _llm_select_ticker(query, context, event)
    return ticker, confidence, reasoning


async def _llm_select_ticker(
    query: str, graph_context: str, event: dict
) -> Tuple[str, float, str]:
    """Ask LLM to pick the single best ASX ticker given graph evidence."""
    try:
        from llm_router import LLMRouter, parse_json_response

        router = LLMRouter()
        valid_list = ", ".join(sorted(VALID_TICKERS))

        system = (
            "You are an Australian equity analyst. Given a geopolitical event and "
            "relevant knowledge graph facts about ASX ticker exposures, select the "
            "single most affected ASX ticker. Respond with JSON only."
        )

        user = f"""Event: {query}

Country: {event.get('country', 'Unknown')}
Event type: {event.get('event_type', 'Unknown')}

Knowledge graph evidence:
{graph_context}

Valid ASX tickers: {valid_list}

Select the single most impacted ticker. JSON format:
{{
  "ticker": "XXXX.AX",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explanation"
}}"""

        response = await router.call_primary(system, user)
        parsed = parse_json_response(response)

        ticker = parsed.get("ticker", "BHP.AX")
        if ticker not in VALID_TICKERS:
            ticker = "BHP.AX"

        return (
            ticker,
            float(parsed.get("confidence", 0.7)),
            parsed.get("reasoning", "Semantic graph selection"),
        )

    except Exception as e:
        logger.warning("LLM ticker selection failed: %s", e)
        return "BHP.AX", 0.5, "LLM fallback to BHP default"
