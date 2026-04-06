"""
Trend Context Service
---------------------
Multi-day price momentum analysis for trend-aware agent persona distribution.
Extracted from market_context.py to keep that module focused on data aggregation.

Public API:
    fetch_trend_context(ticker)       → Dict with trend_label, day changes, etc.
    get_trend_freshness_note(trend)   → str warning for stale data
    build_trend_block(trend)          → str prompt block for agents
    track_trend_health(ticker, ...)   → tracks consecutive failures
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

# /tmp persists within a Railway/Render deployment session; resets on redeploy.
TREND_CACHE_FILE = "/tmp/trend_context_cache.json"

# In-memory last-known-good — process lifetime, faster than disk
_last_known_trend: Dict[str, Dict[str, Any]] = {}

# Consecutive failure counter per ticker — triggers health alert at 3+
_trend_failure_count: Dict[str, int] = {}

# Hardcoded emergency fallbacks verified from market data 2026-03-22/23
_TREND_EMERGENCY_FALLBACKS: Dict[str, Dict[str, Any]] = {
    "BHP.AX": {
        "trend_label": "STRONG_DOWNTREND",
        "day_1_change": 1.59, "day_5_change": -4.68, "day_20_change": -8.09,
        "consecutive_down_days": 0, "dist_from_52w_high_pct": -18.36,
        "from_cache": False, "from_emergency_fallback": True,
    },
    "CBA.AX": {
        "trend_label": "DOWNTREND",
        "day_1_change": -1.81, "day_5_change": -2.0, "day_20_change": -1.16,
        "consecutive_down_days": 2, "dist_from_52w_high_pct": -21.6,
        "from_cache": False, "from_emergency_fallback": True,
    },
    "RIO.AX": {
        "trend_label": "STRONG_DOWNTREND",
        "day_1_change": -2.93, "day_5_change": -4.0, "day_20_change": -7.0,
        "consecutive_down_days": 3, "dist_from_52w_high_pct": -15.0,
        "from_cache": False, "from_emergency_fallback": True,
    },
    "FMG.AX": {
        "trend_label": "STRONG_DOWNTREND",
        "day_1_change": -2.5, "day_5_change": -5.0, "day_20_change": -9.0,
        "consecutive_down_days": 3, "dist_from_52w_high_pct": -22.0,
        "from_cache": False, "from_emergency_fallback": True,
    },
    "WDS.AX": {
        "trend_label": "DOWNTREND",
        "day_1_change": -1.5, "day_5_change": -3.0, "day_20_change": -5.0,
        "consecutive_down_days": 2, "dist_from_52w_high_pct": -12.0,
        "from_cache": False, "from_emergency_fallback": True,
    },
}
_TREND_GENERIC_FALLBACK: Dict[str, Any] = {
    "trend_label": "DOWNTREND",
    "day_1_change": None, "day_5_change": None, "day_20_change": None,
    "consecutive_down_days": None, "dist_from_52w_high_pct": None,
    "from_cache": False, "from_emergency_fallback": True,
}


# ── Alpha Vantage helper (local copy — avoids circular import with market_context) ─

async def _av(function: str, params: dict, timeout: float = 8.0) -> Optional[dict]:
    if not _ALPHA_VANTAGE_KEY:
        return None
    url = "https://www.alphavantage.co/query"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(
                url,
                params={"apikey": _ALPHA_VANTAGE_KEY, "function": function, **params},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Alpha Vantage %s error: %s", function, e)
        return None


# ── Filesystem cache ───────────────────────────────────────────────────────────

def _load_trend_cache() -> dict:
    """Load cached trend data from filesystem."""
    try:
        if os.path.exists(TREND_CACHE_FILE):
            with open(TREND_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("[TREND CACHE] Load failed: %s", e)
    return {}


def _save_trend_cache(ticker: str, data: dict) -> None:
    """Persist a successful trend result to filesystem for cross-request durability."""
    try:
        cache = _load_trend_cache()
        cache[ticker] = {
            "data":         data,
            "cached_at":    datetime.now(timezone.utc).isoformat(),
            "cached_at_ts": time.time(),
        }
        with open(TREND_CACHE_FILE, "w") as f:
            json.dump(cache, f)
        logger.info("[TREND CACHE] Saved %s: %s", ticker, data["trend_label"])
    except Exception as e:
        logger.warning("[TREND CACHE] Save failed: %s", e)


def _get_cached_trend(ticker: str) -> Optional[Dict[str, Any]]:
    """Returns cached trend if ≤24h old."""
    entry = _load_trend_cache().get(ticker)
    if not entry:
        return None
    age_hours = (time.time() - entry.get("cached_at_ts", 0)) / 3600
    if age_hours > 24:
        logger.info("[TREND CACHE] Expired for %s (%.1fh old)", ticker, age_hours)
        return None
    data = {**entry["data"], "from_cache": True, "cache_age_hours": round(age_hours, 1)}
    logger.info(
        "[TREND CACHE] Hit for %s: %s (cached %.1fh ago)",
        ticker, data["trend_label"], age_hours,
    )
    return data


# ── Calculation ────────────────────────────────────────────────────────────────

def _calculate_trend(prices: list, ticker: str) -> Dict[str, Any]:
    """
    Pure trend calculation — no API calls, no side effects.
    prices: list of closing prices, NEWEST FIRST.
    Returns trend_label="UNKNOWN" only when prices are insufficient.
    """
    result: Dict[str, Any] = {
        "trend_label": "UNKNOWN",
        "day_1_change": None, "day_5_change": None, "day_20_change": None,
        "consecutive_down_days": None, "dist_from_52w_high_pct": None,
        "from_cache": False, "from_emergency_fallback": False,
    }
    if not prices or len(prices) < 2:
        return result

    current = prices[0]
    if len(prices) >= 2:
        result["day_1_change"]  = round((current / prices[1]  - 1) * 100, 2)
    if len(prices) >= 6:
        result["day_5_change"]  = round((current / prices[5]  - 1) * 100, 2)
    if len(prices) >= 21:
        result["day_20_change"] = round((current / prices[20] - 1) * 100, 2)

    # Consecutive down sessions from most recent
    streak = 0
    for i in range(len(prices) - 1):
        if prices[i] < prices[i + 1]:
            streak += 1
        else:
            break
    result["consecutive_down_days"] = streak

    recent_high = max(prices[:min(len(prices), 52)])
    result["dist_from_52w_high_pct"] = round((current / recent_high - 1) * 100, 2)

    d5  = result["day_5_change"]  or 0.0
    d20 = result["day_20_change"] or 0.0

    # Thresholds calibrated to real ASX data (verified BHP 2026-03-22)
    if   d5 <= -2   and d20 <= -5:   result["trend_label"] = "STRONG_DOWNTREND"
    elif d5 <= -1.5 and streak >= 2: result["trend_label"] = "DOWNTREND"
    elif d5 >= 2    and d20 >= 5:    result["trend_label"] = "STRONG_UPTREND"
    elif d5 >= 1.5  and streak == 0: result["trend_label"] = "UPTREND"
    else:                             result["trend_label"] = "SIDEWAYS"

    logger.info(
        "[TREND CALC] %s: d1=%s d5=%+.1f%% d20=%+.1f%% streak=%d → %s",
        ticker,
        f"{result['day_1_change']:+.1f}%" if result["day_1_change"] is not None else "N/A",
        d5, d20, streak, result["trend_label"],
    )
    return result


# ── Prompt rendering ───────────────────────────────────────────────────────────

def build_trend_block(trend: Dict[str, Any]) -> str:
    """Builds the ===TREND MOMENTUM=== block injected into every agent prompt."""
    label   = trend.get("trend_label", "UNKNOWN")
    d1      = trend.get("day_1_change")
    d5      = trend.get("day_5_change")
    d20     = trend.get("day_20_change")
    streak  = trend.get("consecutive_down_days")
    dist    = trend.get("dist_from_52w_high_pct")

    d1_s    = f"{d1:+.2f}%"  if d1   is not None else "N/A"
    d5_s    = f"{d5:+.2f}%"  if d5   is not None else "N/A"
    d20_s   = f"{d20:+.2f}%" if d20  is not None else "N/A"
    dist_s  = f"{dist:+.2f}% from 52w high" if dist is not None else "N/A"
    streak_s = str(streak) if streak is not None else "N/A"

    freshness = get_trend_freshness_note(trend)
    freshness_line = f"\n{freshness}" if freshness else ""

    return (
        f"=== TREND MOMENTUM ===\n"
        f"Trend label: {label}\n"
        f"1-day return: {d1_s} | 5-day: {d5_s} | 20-day: {d20_s}\n"
        f"Consecutive down sessions: {streak_s}\n"
        f"Distance from 52-week high: {dist_s}"
        f"{freshness_line}\n"
        f"=== END TREND ==="
    )


def get_trend_freshness_note(trend_context: Dict[str, Any]) -> str:
    """Warning string added to agent prompts when trend data is not freshly fetched."""
    if trend_context.get("from_emergency_fallback"):
        return (
            "WARNING: Trend data from emergency fallback — live price history unavailable. "
            "Weight live commodity prices and volume more heavily than trend."
        )
    if trend_context.get("from_cache"):
        age = trend_context.get("cache_age_hours", "unknown")
        return (
            f"NOTE: Trend data from cache ({age}h ago). "
            "Still valid — trend labels don't change hourly."
        )
    return ""


# ── Health tracking ────────────────────────────────────────────────────────────

def track_trend_health(ticker: str, trend_label: str, from_fallback: bool) -> None:
    """Tracks consecutive trend fetch failures; logs an error alert at 3+."""
    if trend_label == "UNKNOWN" or from_fallback:
        _trend_failure_count[ticker] = _trend_failure_count.get(ticker, 0) + 1
        count = _trend_failure_count[ticker]
        if count >= 3:
            logger.error(
                "[TREND HEALTH ALERT] %s has failed trend fetch %d consecutive times. "
                "Check yfinance / Alpha Vantage connectivity. "
                "Using fallback data — predictions may be less accurate.",
                ticker, count,
            )
    else:
        _trend_failure_count[ticker] = 0


# ── Main entry point ───────────────────────────────────────────────────────────

async def fetch_trend_context(ticker: str) -> Dict[str, Any]:
    """
    Fetches multi-day price momentum for trend-aware persona distribution.
    NEVER returns UNKNOWN if any prior successful fetch exists.

    4-layer fallback (never reaches layer 4 in normal operation):
      1. Fresh yfinance history (no rate limit — primary)
      2. Fresh Alpha Vantage TIME_SERIES_DAILY (25 calls/day — secondary)
      3. In-memory + filesystem cache (last successful result, ≤24h valid)
      4. Hardcoded per-ticker emergency values (verified 2026-03-22)
    """

    # ── Layer 1: Fresh yfinance ───────────────────────────────────────────────
    try:
        import yfinance as yf
        logger.info("[TREND] Fetching via yfinance for %s", ticker)
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d")
        if hist is None or hist.empty or len(hist) < 5:
            raise ValueError(f"Insufficient history: {len(hist) if hist is not None else 0} rows")

        hist = hist[hist.index.dayofweek < 5]   # strip weekends
        hist = hist.dropna(subset=["Close"])

        if len(hist) < 5:
            raise ValueError(f"Insufficient trading-day rows after filter: {len(hist)}")

        prices = list(reversed(hist["Close"].tolist()))   # newest first

        dates = list(reversed(hist.index.tolist()))
        if len(dates) >= 21:
            days_gap = (dates[0] - dates[20]).days
            logger.info(
                "[TREND] %s prices[20] date: %s (%d calendar days ago, ~20 trading days)",
                ticker, dates[20].date(), days_gap,
            )

        result = _calculate_trend(prices, ticker)
        if result["trend_label"] != "UNKNOWN":
            _save_trend_cache(ticker, result)
            _last_known_trend[ticker] = result
            logger.info("[TREND] yfinance success: %s", result["trend_label"])
            return result
        raise ValueError("Trend calculation returned UNKNOWN from yfinance data")
    except Exception as e:
        logger.warning("[TREND] yfinance failed for %s: %s", ticker, e)

    # ── Layer 2: Alpha Vantage TIME_SERIES_DAILY ─────────────────────────────
    if _ALPHA_VANTAGE_KEY:
        try:
            logger.info("[TREND] Fetching via Alpha Vantage for %s", ticker)
            data = await _av("TIME_SERIES_DAILY", {"symbol": ticker, "outputsize": "compact"})
            if data is None:
                raise ValueError("No response")
            if "Note" in data or "Information" in data:
                raise ValueError(
                    f"Rate limit: {(data.get('Note') or data.get('Information', ''))[:80]}"
                )
            ts = data.get("Time Series (Daily)", {})
            if not ts:
                raise ValueError("Empty time series")
            dates  = sorted(ts.keys(), reverse=True)[:25]
            prices = [float(ts[d]["4. close"]) for d in dates]   # newest first
            result = _calculate_trend(prices, ticker)
            if result["trend_label"] != "UNKNOWN":
                _save_trend_cache(ticker, result)
                _last_known_trend[ticker] = result
                logger.info("[TREND] Alpha Vantage success: %s", result["trend_label"])
                return result
            raise ValueError("Trend calculation returned UNKNOWN from AV data")
        except Exception as e:
            logger.warning("[TREND] Alpha Vantage failed for %s: %s", ticker, e)

    # ── Layer 3: In-memory cache → filesystem cache ──────────────────────────
    mem = _last_known_trend.get(ticker)
    if mem and mem.get("trend_label") not in (None, "UNKNOWN"):
        logger.info("[TREND] In-memory cache hit for %s: %s", ticker, mem["trend_label"])
        return {**mem, "from_cache": True}

    fs = _get_cached_trend(ticker)
    if fs and fs.get("trend_label") not in (None, "UNKNOWN"):
        logger.info("[TREND] Filesystem cache hit for %s: %s", ticker, fs["trend_label"])
        _last_known_trend[ticker] = fs
        return fs

    # ── Layer 4: Emergency hardcoded fallback ─────────────────────────────────
    logger.error(
        "[TREND] ALL FETCHES FAILED for %s — using emergency hardcoded fallback",
        ticker,
    )
    fallback = _TREND_EMERGENCY_FALLBACKS.get(ticker, {**_TREND_GENERIC_FALLBACK})
    logger.info("[TREND] Emergency fallback for %s: %s", ticker, fallback["trend_label"])
    return {**fallback}
