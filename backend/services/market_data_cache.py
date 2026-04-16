"""Market data caching layer for Market Oracle AI.

Extends the existing Upstash Redis client (services/redis_client.py) with
typed, TTL-aware helpers for the two hot data paths:

  - get_price_cached()   5-minute TTL  (intraday prices, volume, RSI)
  - get_macro_cached()   1-hour TTL    (iron ore, AUD/USD, Brent, FRED series)
  - set_price_cached()   write partner for prices
  - set_macro_cached()   write partner for macro

Each helper is a thin wrapper that:
  1. Checks Redis first (cache_get)
  2. On miss, returns None so the caller can fetch live data
  3. After a live fetch the caller should call set_*_cached() to populate the cache

All keys are namespaced: "price:{ticker}:v2" and "macro:{series}:v1".
Gracefully no-ops when Redis is not configured (UPSTASH_REDIS_REST_URL absent).

Usage:
    from services.market_data_cache import get_price_cached, set_price_cached

    data = await get_price_cached("BHP.AX")
    if data is None:
        data = fetch_live(...)          # your live-fetch call
        await set_price_cached("BHP.AX", data)
"""

import logging
import time
from typing import Any, Optional

from services.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

# ── TTLs ─────────────────────────────────────────────────────────────────────

_PRICE_TTL_SEC  = 5 * 60        # 5 minutes — intraday prices move frequently
_MACRO_TTL_SEC  = 60 * 60       # 1 hour    — macro series update less often
_NEWS_TTL_SEC   = 15 * 60       # 15 minutes — news/events
_SECTOR_TTL_SEC = 30 * 60       # 30 minutes — sector heatmap

# ── Key builders ─────────────────────────────────────────────────────────────

def _price_key(ticker: str) -> str:
    return f"price:{ticker.upper()}:v2"


def _macro_key(series: str) -> str:
    return f"macro:{series.lower()}:v1"


def _news_key(source: str) -> str:
    return f"news:{source.lower()}:v1"


def _sector_key(sector: str = "all") -> str:
    return f"sector:{sector.lower()}:v1"


# ── Price cache ───────────────────────────────────────────────────────────────

async def get_price_cached(ticker: str) -> Optional[dict]:
    """
    Return cached price data for a ticker, or None on cache miss.

    Expected dict shape (set by set_price_cached):
        {
            "ticker": "BHP.AX",
            "price": 45.20,
            "change_pct": 1.3,
            "volume": 3_800_000,
            "rsi_14": 58.2,
            "fetched_at": 1712345678,   # Unix timestamp
        }
    """
    key = _price_key(ticker)
    data = await cache_get(key)
    if data:
        age = int(time.time()) - data.get("fetched_at", 0)
        logger.debug("Cache HIT price:%s (age %ds)", ticker, age)
    else:
        logger.debug("Cache MISS price:%s", ticker)
    return data


async def set_price_cached(ticker: str, data: dict) -> bool:
    """
    Cache price data for a ticker with the standard 5-minute TTL.
    Automatically stamps data with fetched_at if not present.
    """
    payload = {**data, "fetched_at": data.get("fetched_at", int(time.time()))}
    ok = await cache_set(_price_key(ticker), payload, ttl=_PRICE_TTL_SEC)
    if ok:
        logger.debug("Cache SET price:%s (TTL %ds)", ticker, _PRICE_TTL_SEC)
    return ok


# ── Macro cache ───────────────────────────────────────────────────────────────

async def get_macro_cached(series: str) -> Optional[Any]:
    """
    Return cached macro data for a named series, or None on miss.

    Common series names:
        "iron_ore"   — spot price USD/t
        "audusd"     — AUD/USD exchange rate
        "brent"      — Brent crude USD/bbl
        "asx200"     — ASX 200 index level
        "fred_{id}"  — any FRED series (e.g. "fred_CPIAUCSL")
    """
    key = _macro_key(series)
    data = await cache_get(key)
    logger.debug("Cache %s macro:%s", "HIT" if data else "MISS", series)
    return data


async def set_macro_cached(series: str, value: Any) -> bool:
    """Cache macro data with the standard 1-hour TTL."""
    payload = {"value": value, "fetched_at": int(time.time())}
    ok = await cache_set(_macro_key(series), payload, ttl=_MACRO_TTL_SEC)
    if ok:
        logger.debug("Cache SET macro:%s (TTL %ds)", series, _MACRO_TTL_SEC)
    return ok


async def get_macro_value(series: str) -> Optional[float]:
    """Convenience: return just the numeric value from a cached macro entry."""
    data = await get_macro_cached(series)
    if data and isinstance(data, dict):
        return data.get("value")
    return None


# ── News / sector caches ─────────────────────────────────────────────────────

async def get_news_cached(source: str) -> Optional[list]:
    """Return cached news items for a source (e.g. 'acled', 'rss')."""
    return await cache_get(_news_key(source))


async def set_news_cached(source: str, items: list) -> bool:
    return await cache_set(_news_key(source), items, ttl=_NEWS_TTL_SEC)


async def get_sector_cached(sector: str = "all") -> Optional[dict]:
    """Return cached sector heatmap data."""
    return await cache_get(_sector_key(sector))


async def set_sector_cached(sector: str, data: dict) -> bool:
    return await cache_set(_sector_key(sector), data, ttl=_SECTOR_TTL_SEC)


# ── Health check ─────────────────────────────────────────────────────────────

async def redis_health() -> dict:
    """
    Probe Redis connectivity and return a health dict suitable for /api/health.

    Returns:
        {
            "status": "ok" | "degraded" | "unavailable",
            "latency_ms": 12,
            "configured": True,
        }
    """
    import os
    configured = bool(os.environ.get("UPSTASH_REDIS_REST_URL"))
    if not configured:
        return {"status": "unavailable", "latency_ms": None, "configured": False}

    start = time.monotonic()
    probe_key = "health:probe:v1"
    try:
        await cache_set(probe_key, {"ts": int(time.time())}, ttl=10)
        result = await cache_get(probe_key)
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        if result:
            return {"status": "ok", "latency_ms": latency_ms, "configured": True}
        return {"status": "degraded", "latency_ms": latency_ms, "configured": True}
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.warning("Redis health probe failed: %s", exc)
        return {"status": "degraded", "latency_ms": latency_ms, "configured": True}
