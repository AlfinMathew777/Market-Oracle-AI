"""Semantic prediction memory — Zep-backed episodic recall.

The exact-match SQL memory in agents/prediction_memory.py can only learn from
past predictions with the SAME ticker and direction. This module adds the
cross-ticker dimension: RESOLVED predictions (outcome known) are indexed as
text episodes in a Zep Cloud graph, and retrieval is by semantic similarity —
so an RBA-rate-shock → CBA.AX setup can learn from a semantically similar
rate-shock → NAB.AX outcome even though no SQL key matches.

Follows the same pattern as services/semantic_ticker_mapper.py:
  - Zep is optional — without ZEP_API_KEY every call is a cheap no-op.
  - fail-soft everywhere: memory must never break validation or a prediction.
  - only RESOLVED outcomes are indexed; an episode always carries its outcome,
    so retrieved memories are experiences, not guesses.
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_ZEP_KEY = os.environ.get("ZEP_API_KEY", "")
_GRAPH_ID = "prediction_memory_v1"

# Bounds — keep episodes compact and queries inside Zep's limits.
_MAX_EPISODE_CHARS = 1200
_MAX_QUERY_CHARS = 400
_DEFAULT_SEARCH_LIMIT = 5


def _client():
    from zep_cloud.client import Zep

    return Zep(api_key=_ZEP_KEY)


def build_episode(
    *,
    ticker: str,
    direction: str,
    confidence: float,
    outcome: str,
    change_pct: float,
    event_summary: str = "",
    trend_label: str = "",
    lesson: str = "",
) -> str:
    """Render one resolved prediction as a compact, searchable text episode."""
    parts = [
        f"PREDICTION OUTCOME: {ticker} predicted {direction} "
        f"at {confidence:.0%} confidence — outcome {outcome} "
        f"(actual move {change_pct:+.2f}%).",
    ]
    if trend_label:
        parts.append(f"Market trend at prediction time: {trend_label}.")
    if event_summary:
        parts.append(f"Situation: {event_summary}")
    if lesson:
        parts.append(f"Lesson: {lesson}")
    return " ".join(parts)[:_MAX_EPISODE_CHARS]


async def index_resolved_prediction(
    *,
    ticker: str,
    direction: str,
    confidence: float,
    outcome: str,
    change_pct: float,
    event_summary: str = "",
    trend_label: str = "",
    lesson: str = "",
) -> bool:
    """Add one resolved prediction to the semantic memory graph.

    Returns True when the episode was indexed, False on no-op or failure.
    Never raises — indexing is strictly best-effort.
    """
    if not _ZEP_KEY:
        return False
    if outcome not in ("CORRECT", "INCORRECT"):
        return False  # only real experiences become memories

    episode = build_episode(
        ticker=ticker, direction=direction, confidence=confidence,
        outcome=outcome, change_pct=change_pct, event_summary=event_summary,
        trend_label=trend_label, lesson=lesson,
    )

    loop = asyncio.get_event_loop()
    try:
        client = _client()
        await loop.run_in_executor(
            None,
            lambda: client.graph.add(graph_id=_GRAPH_ID, type="text", data=episode),
        )
        logger.info("Semantic memory indexed: %s %s → %s", ticker, direction, outcome)
        return True
    except Exception as first_err:  # noqa: BLE001 — try create-then-retry once
        try:
            client = _client()
            await loop.run_in_executor(
                None, lambda: client.graph.create(graph_id=_GRAPH_ID)
            )
            await loop.run_in_executor(
                None,
                lambda: client.graph.add(graph_id=_GRAPH_ID, type="text", data=episode),
            )
            logger.info("Semantic memory graph created + episode indexed: %s", ticker)
            return True
        except Exception as retry_err:  # noqa: BLE001 — memory never breaks a caller
            logger.warning(
                "Semantic memory indexing failed (%s; retry: %s)", first_err, retry_err
            )
            return False


async def search_similar_situations(
    query: str, limit: int = _DEFAULT_SEARCH_LIMIT
) -> list[str]:
    """Retrieve semantically similar past prediction outcomes.

    Args:
        query: natural-language description of the current setup
               (ticker, direction, domains, event summary)
        limit: max episodes to return

    Returns:
        List of episode/fact strings, best match first. Empty on no-op/failure.
    """
    if not _ZEP_KEY or not query.strip():
        return []

    loop = asyncio.get_event_loop()
    try:
        client = _client()
        results = await loop.run_in_executor(
            None,
            lambda: client.graph.search(
                graph_id=_GRAPH_ID, query=query[:_MAX_QUERY_CHARS], limit=limit
            ),
        )
        if not results or not getattr(results, "results", None):
            return []

        snippets: list[str] = []
        for r in results.results[:limit]:
            fact = getattr(r, "fact", None) or getattr(r, "content", None)
            if fact:
                snippets.append(str(fact))
        return snippets[:limit]
    except Exception as e:  # noqa: BLE001 — memory never breaks a caller
        logger.warning("Semantic memory search failed: %s", e)
        return []
