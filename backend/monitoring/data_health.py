"""Data feed health checks for Market Oracle AI.

check_feeds() performs lightweight live checks against each data source and
returns per-feed status plus a top-level recommendation on whether signals
should be blocked.

Blocking logic (conservative):
  - yfinance (ASX prices) DOWN → block signals (primary data source for simulations)
  - All other feeds degraded → degrade with warning, don't block
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Staleness thresholds (seconds) — feeds older than this are flagged
_STALE_THRESHOLDS = {
    "asx_prices":   15 * 60,   # 15 minutes — live prices must be fresh
    "macro_data":   60 * 60,   # 1 hour — FRED/macro updates hourly at most
    "news_feed":    30 * 60,   # 30 minutes — news cache
}

# In-memory tracking of last known-good fetch per feed
_last_success: dict[str, float] = {}


def record_feed_success(feed_name: str) -> None:
    """Call after a successful fetch from any data source."""
    _last_success[feed_name] = time.time()


def _age_seconds(feed_name: str) -> float | None:
    """Return seconds since last successful fetch, or None if never fetched."""
    ts = _last_success.get(feed_name)
    if ts is None:
        return None
    return time.time() - ts


async def _check_yfinance() -> dict[str, Any]:
    """Check ASX price feed via yfinance. Critical — blocks signals if down."""
    t0 = time.time()
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yf.Ticker("BHP.AX").fast_info)
        price = round(info.last_price, 2) if hasattr(info, "last_price") else None
        if price is None:
            return {
                "status": "degraded",
                "response_ms": round((time.time() - t0) * 1000),
                "error": "No price returned for BHP.AX",
                "critical": True,
            }
        record_feed_success("asx_prices")
        return {
            "status": "healthy",
            "response_ms": round((time.time() - t0) * 1000),
            "sample_price": price,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "down",
            "response_ms": round((time.time() - t0) * 1000),
            "error": str(e),
            "critical": True,
        }


async def _check_fred() -> dict[str, Any]:
    """Check macro data feed (FRED). Non-critical."""
    t0 = time.time()
    try:
        import os
        if not os.environ.get("FRED_API_KEY"):
            return {"status": "unconfigured", "note": "FRED_API_KEY not set", "critical": False}
        from services.fred_service import get_all_australian_macro
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_all_australian_macro)
        if result.get("status") == "success" and result.get("data"):
            record_feed_success("macro_data")
            return {
                "status": "healthy",
                "response_ms": round((time.time() - t0) * 1000),
                "fields": len(result["data"]),
                "last_update": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "status": "degraded",
            "response_ms": round((time.time() - t0) * 1000),
            "note": result.get("message", "No data returned"),
            "critical": False,
        }
    except Exception as e:
        return {
            "status": "down",
            "response_ms": round((time.time() - t0) * 1000),
            "error": str(e),
            "critical": False,
        }


async def _check_news() -> dict[str, Any]:
    """Check news feed. Non-critical."""
    t0 = time.time()
    try:
        from services.news_service import get_asx_news_sentiment
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: get_asx_news_sentiment(["BHP.AX"], hours=24)
        )
        if result.get("status") == "success":
            record_feed_success("news_feed")
            return {
                "status": "healthy",
                "response_ms": round((time.time() - t0) * 1000),
                "articles": result.get("articles", 0),
                "last_update": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "status": "degraded",
            "response_ms": round((time.time() - t0) * 1000),
            "note": result.get("message", "No articles"),
            "critical": False,
        }
    except Exception as e:
        return {
            "status": "down",
            "response_ms": round((time.time() - t0) * 1000),
            "error": str(e),
            "critical": False,
        }


async def check_feeds(timeout: float = 10.0) -> dict[str, Any]:
    """
    Run all feed health checks concurrently and return a consolidated report.

    Returns:
        {
            "overall": "healthy" | "degraded" | "critical",
            "feeds": { feed_name: { status, response_ms, ... } },
            "signals_blocked": bool,
            "block_reason": str | None,
            "checked_at": ISO timestamp,
        }
    """
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _check_yfinance(),
                _check_fred(),
                _check_news(),
                return_exceptions=True,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Data feed health check timed out after %.0fs", timeout)
        results = [
            {"status": "timeout", "critical": True},
            {"status": "timeout", "critical": False},
            {"status": "timeout", "critical": False},
        ]

    feed_names = ["asx_prices", "macro_data", "news_feed"]
    feeds: dict[str, Any] = {}
    for name, result in zip(feed_names, results):
        if isinstance(result, Exception):
            feeds[name] = {"status": "error", "error": str(result), "critical": name == "asx_prices"}
        else:
            feeds[name] = result

    # Determine if signals should be blocked
    critical_feeds = [name for name, info in feeds.items() if info.get("critical") and info.get("status") not in ("healthy", "unconfigured")]
    signals_blocked = len(critical_feeds) > 0
    block_reason: str | None = None
    if signals_blocked:
        block_reason = f"{', '.join(critical_feeds)} feed(s) unavailable — signals blocked until data is restored"

    # Overall status
    statuses = [info["status"] for info in feeds.values()]
    if signals_blocked:
        overall = "critical"
    elif any(s in ("down", "degraded", "timeout") for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "feeds": feeds,
        "signals_blocked": signals_blocked,
        "block_reason": block_reason,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def should_block_signals() -> tuple[bool, str | None]:
    """
    Lightweight check: should the current simulation be blocked due to bad data?

    Returns (blocked: bool, reason: str | None).
    Only checks the critical feed (ASX prices) to keep simulation startup fast.
    """
    result = await _check_yfinance()
    if result["status"] not in ("healthy",):
        reason = result.get("error") or f"ASX price feed status: {result['status']}"
        return True, f"ASX price feed unavailable — {reason}"
    return False, None
