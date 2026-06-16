"""
Source-relevance filter for news items (context engineering: retrieval + reduction).

The market-context builder feeds every fetched headline to all ~30 voting agents.
Off-topic headlines (a mining stock's prompt carrying unrelated political violence,
say) are pure noise that dilutes the consensus. This module runs a single cheap
8b-tier pass that keeps only the headlines that could plausibly move the given ticker,
*before* they reach the agent prompts.

Safety contract — this filter can never make a prediction worse than the status quo:

* Disabled by default. Only active when ``ENABLE_NEWS_RELEVANCE_FILTER`` is truthy,
  so production behaviour is unchanged until explicitly opted in.
* Fails open. Any LLM error, timeout, empty/garbled response, or a "drop everything"
  verdict returns the original list untouched — agents are never starved of news.
* One extra LLM call total (all headlines classified in a single batched prompt),
  routed through ``LLMRouter.call_fast`` (Groq-8b), not one call per item.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FLAG = "ENABLE_NEWS_RELEVANCE_FILTER"

# Below this many items, filtering isn't worth an LLM round-trip — a handful of
# headlines is cheap to carry and the consensus tolerates it.
_MIN_ITEMS_TO_FILTER = 4

_SYSTEM_PROMPT = (
    "You are a financial news relevance filter for ASX-listed equities. "
    "Given a stock and a numbered list of headlines, decide which headlines could "
    "plausibly affect that stock's price — directly, or through its sector, commodity "
    "inputs, supply chain, currency, or macro exposure. Be inclusive when a headline "
    "is borderline; only exclude clearly unrelated noise.\n\n"
    "Respond with ONLY the numbers of the relevant headlines, comma-separated "
    "(e.g. '1, 3, 4'). If none are relevant, respond with the single word NONE. "
    "Do not explain."
)


def is_enabled() -> bool:
    """True when the relevance filter is switched on via env var."""
    return os.environ.get(_FLAG, "false").strip().lower() in ("1", "true", "yes", "on")


def _parse_keep_indices(response: str, n_items: int) -> Optional[list[int]]:
    """
    Parse a model response into a list of 0-based indices to keep.

    Returns None when the response is unusable (so the caller fails open). An explicit
    "NONE" verdict also returns None — we never let the model strip *all* news, since a
    false "nothing is relevant" is worse than carrying a little noise.
    """
    if not response:
        return None

    text = response.strip().upper()
    if "NONE" in text and not any(ch.isdigit() for ch in text):
        return None

    nums = re.findall(r"\d+", text)
    if not nums:
        return None

    # Convert to 0-based, dedupe, keep only in-range, preserve original order.
    keep: list[int] = []
    seen: set[int] = set()
    for raw in nums:
        idx = int(raw) - 1
        if 0 <= idx < n_items and idx not in seen:
            seen.add(idx)
            keep.append(idx)

    return keep or None


async def filter_relevant_news(
    ticker: str,
    items: list[dict[str, Any]],
    llm_router: Any | None = None,
    *,
    min_items_to_filter: int = _MIN_ITEMS_TO_FILTER,
) -> list[dict[str, Any]]:
    """
    Return only the news items relevant to ``ticker``.

    Args:
        ticker:               ASX ticker (e.g. "BHP.AX").
        items:                News dicts, each expected to carry a ``title`` key.
        llm_router:           An ``LLMRouter``-like object exposing ``call_fast``.
                              When None, one is lazily constructed.
        min_items_to_filter:  Skip the LLM call when fewer than this many items.

    Returns:
        A filtered list (a new list; the input is never mutated). Falls open to the
        original ``items`` on disablement, too-few items, or any failure.
    """
    if not is_enabled() or not items or len(items) < min_items_to_filter:
        return items

    try:
        router = llm_router or _get_router()
        if router is None:
            return items

        numbered = "\n".join(
            f"{i + 1}. {(it.get('title') or '').strip()}" for i, it in enumerate(items)
        )
        user_prompt = f"Stock: {ticker}\n\nHeadlines:\n{numbered}"

        response = await router.call_fast(
            system_message=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            session_id="news_relevance",
        )

        keep = _parse_keep_indices(response, len(items))
        if not keep:
            # Unparseable, empty, or "NONE" — fail open rather than drop all news.
            return items

        filtered = [items[i] for i in keep]
        logger.info(
            "news relevance filter: kept %d/%d headlines for %s",
            len(filtered),
            len(items),
            ticker,
        )
        return filtered

    except Exception as e:  # noqa: BLE001 — must fail open on ANY error
        logger.warning(
            "news relevance filter failed for %s (%s) — passing all items through",
            ticker,
            e,
        )
        return items


def _get_router() -> Any | None:
    """Lazily build an LLMRouter, returning None if construction fails (no keys, etc.)."""
    try:
        from llm_router import LLMRouter

        return LLMRouter()
    except Exception as e:  # noqa: BLE001
        logger.warning("news relevance filter: could not init LLMRouter (%s)", e)
        return None
