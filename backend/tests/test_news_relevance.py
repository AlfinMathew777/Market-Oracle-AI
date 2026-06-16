"""Unit tests for services.news_relevance — flagged, fail-open source filter."""

from unittest.mock import AsyncMock

import pytest

from services import news_relevance
from services.news_relevance import (
    _parse_keep_indices,
    filter_relevant_news,
    is_enabled,
)


def _items(n: int) -> list[dict]:
    return [{"title": f"Headline number {i}"} for i in range(1, n + 1)]


def _router(response: str) -> AsyncMock:
    """A fake LLMRouter whose call_fast returns a fixed response."""
    router = AsyncMock()
    router.call_fast = AsyncMock(return_value=response)
    return router


# ── is_enabled ───────────────────────────────────────────────────────────────────

def test_is_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("ENABLE_NEWS_RELEVANCE_FILTER", raising=False)
    assert is_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " True "])
def test_is_enabled_truthy_values(monkeypatch, val):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", val)
    assert is_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_is_enabled_falsy_values(monkeypatch, val):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", val)
    assert is_enabled() is False


# ── _parse_keep_indices ──────────────────────────────────────────────────────────

def test_parse_basic_csv():
    assert _parse_keep_indices("1, 3, 4", 5) == [0, 2, 3]


def test_parse_handles_whitespace_and_noise():
    assert _parse_keep_indices("  keep: 2 and 5 ", 5) == [1, 4]


def test_parse_dedupes_and_orders():
    assert _parse_keep_indices("3,3,1", 5) == [2, 0]


def test_parse_drops_out_of_range():
    assert _parse_keep_indices("1, 99, 4", 5) == [0, 3]


def test_parse_none_verdict_returns_none():
    assert _parse_keep_indices("NONE", 5) is None


def test_parse_empty_returns_none():
    assert _parse_keep_indices("", 5) is None
    assert _parse_keep_indices("   ", 5) is None


def test_parse_no_digits_returns_none():
    assert _parse_keep_indices("all of them are great", 5) is None


# ── filter_relevant_news ─────────────────────────────────────────────────────────

async def test_filter_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("ENABLE_NEWS_RELEVANCE_FILTER", raising=False)
    router = _router("1")
    items = _items(6)
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out is items  # untouched
    router.call_fast.assert_not_awaited()


async def test_filter_too_few_items_is_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("1")
    items = _items(2)  # below the 4-item threshold
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out is items
    router.call_fast.assert_not_awaited()


async def test_filter_keeps_selected_indices(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("1, 3, 5")
    items = _items(6)
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out == [items[0], items[2], items[4]]
    router.call_fast.assert_awaited_once()


async def test_filter_none_verdict_fails_open(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("NONE")
    items = _items(6)
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out is items  # never strips all news


async def test_filter_llm_error_fails_open(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = AsyncMock()
    router.call_fast = AsyncMock(side_effect=RuntimeError("provider down"))
    items = _items(6)
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out is items


async def test_filter_garbage_response_fails_open(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("I think they all matter honestly")
    items = _items(6)
    out = await filter_relevant_news("BHP.AX", items, router)
    assert out is items


async def test_filter_empty_items_returns_empty(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("1")
    out = await filter_relevant_news("BHP.AX", [], router)
    assert out == []
    router.call_fast.assert_not_awaited()


async def test_filter_does_not_mutate_input(monkeypatch):
    monkeypatch.setenv("ENABLE_NEWS_RELEVANCE_FILTER", "true")
    router = _router("2")
    items = _items(5)
    original = list(items)
    await filter_relevant_news("BHP.AX", items, router)
    assert items == original  # input list unchanged
