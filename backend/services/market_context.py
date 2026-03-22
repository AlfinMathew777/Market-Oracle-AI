"""Live market context fetcher — injected into every agent prompt before simulation.

Fetches (in parallel):
  - Iron Ore 62% Fe futures (yfinance TIO=F → Alpha Vantage fallback)
  - AUD/USD exchange rate   (Alpha Vantage → yfinance fallback)
  - Brent Crude             (yfinance BZ=F → FRED fallback)
  - Ticker price + RSI + MACD (yfinance + Alpha Vantage)
  - Recent news with recency decay weights (MarketAux, last 24h only)

All fetches have try/except with graceful STALE fallback — never blocks simulation.
"""

import os
import re
import json
import time
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
_FRED_API_KEY      = os.getenv("FRED_API_KEY", "")
_MARKETAUX_KEY     = os.getenv("MARKETAUX_API_KEY", "")
_GUARDIAN_API_KEY  = os.getenv("GUARDIAN_API_KEY", "")
_FINNHUB_API_KEY   = os.getenv("FINNHUB_API_KEY", "")
_GNEWS_API_KEY     = os.getenv("GNEWS_API_KEY", "")

STALE = "STALE"


# ── Intraday market data cache (4-minute TTL) ─────────────────────────────────

class MarketDataCache:
    """
    Short-lived in-process cache for intraday market data.
    Forces fresh fetch every 4 minutes — prevents stale volume/price data
    accumulating across simulations in a long-running Railway process.
    """
    def __init__(self, ttl_seconds: int = 240):  # 4 minutes
        self._cache: dict = {}
        self._timestamps: dict = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[dict]:
        if key not in self._cache:
            return None
        age = time.time() - self._timestamps[key]
        if age > self.ttl:
            logger.info("[CACHE] Expired: %s (%.0fs old > %ds TTL) — forcing fresh fetch",
                        key, age, self.ttl)
            del self._cache[key]
            del self._timestamps[key]
            return None
        logger.info("[CACHE] Hit: %s (%.0fs old, TTL %ds) — using cached data",
                    key, age, self.ttl)
        return self._cache[key]

    def set(self, key: str, value: dict) -> None:
        self._cache[key] = value
        self._timestamps[key] = time.time()
        logger.info("[CACHE] Stored: %s (expires in %ds)", key, self.ttl)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)


# Single module-level instance — shared across all simulation runs in the process
market_cache = MarketDataCache(ttl_seconds=240)


# ── News relevance weighting ───────────────────────────────────────────────────

def news_weight(
    hours_old: float,
    category: str = "",
    headline: str = "",
    ticker: str = "BHP",
) -> float:
    """
    Calculates relevance weight for a news item before injecting into agent prompts.
    Company-specific news never fully decays. Geopolitical noise decays faster.
    """
    # Step 1: Base time decay
    if hours_old > 72:
        base = 0.05
    elif hours_old > 48:
        base = 0.2
    elif hours_old > 24:
        base = 0.4
    elif hours_old > 6:
        base = 0.75
    else:
        base = 1.0

    # Step 2: Category multipliers (applied before boosts)
    category_upper = category.upper()

    # Geopolitical violence = noise for commodity stocks
    if any(k in category_upper for k in ["EXPLOSIONS", "REMOTE VIOLENCE", "BATTLES", "RIOTS"]):
        base *= 0.65

    # Strategic/economic developments stay highly relevant
    if "STRATEGIC" in category_upper or "ECONOMIC" in category_upper:
        base = max(base, 0.75)

    # Step 3: Supply chain events stay relevant regardless of age
    supply_keywords = [
        "port", "canal", "suez", "strait", "shipping", "tanker",
        "freight", "logistics", "ban", "sanctions",
    ]
    if any(k in headline.lower() for k in supply_keywords):
        base = max(base, 0.80)

    # Step 4: Company-specific boost — headline directly mentions ticker (recent only)
    # Applied LAST so it overrides geopolitical decay for fresh company news
    ticker_clean = ticker.replace(".AX", "").upper()
    if ticker_clean in headline.upper() and hours_old <= 48:
        base = max(base, 0.85)

    return round(min(base, 1.0), 3)


def weight_to_label(w: float) -> str:
    """Signal strength label for agent prompts."""
    if w >= 0.85:
        return "CRITICAL"
    elif w >= 0.70:
        return "HIGH"
    elif w >= 0.45:
        return "MEDIUM"
    else:
        return "LOW — treat as background noise only"


# ── Alpha Vantage helper ───────────────────────────────────────────────────────

async def _av(function: str, params: dict, timeout: float = 8.0) -> Optional[dict]:
    if not _ALPHA_VANTAGE_KEY:
        return None
    url = "https://www.alphavantage.co/query"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params={"apikey": _ALPHA_VANTAGE_KEY, "function": function, **params})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Alpha Vantage %s error: %s", function, e)
        return None


# ── Individual fetchers ────────────────────────────────────────────────────────

async def _fetch_iron_ore() -> Dict[str, Any]:
    """Iron Ore 62% Fe — SGX TIO=F via yfinance, Alpha Vantage fallback."""
    try:
        import yfinance as yf
        t = yf.Ticker("TIO=F")
        info = t.fast_info
        price = getattr(info, "last_price", None)
        prev  = getattr(info, "previous_close", price)
        if price and prev and prev > 0:
            return {"price": round(float(price), 2), "change_pct": round((price - prev) / prev * 100, 2), "status": "live"}
    except Exception as e:
        logger.warning("Iron ore yfinance: %s", e)

    data = await _av("IRON_ORE", {})
    if data and "data" in data and len(data["data"]) >= 2:
        try:
            p0 = float(data["data"][0]["value"])
            p1 = float(data["data"][1]["value"])
            return {"price": round(p0, 2), "change_pct": round((p0 - p1) / p1 * 100, 2), "status": "live"}
        except Exception:
            pass

    return {"price": 97.5, "change_pct": 0.0, "status": STALE}


async def _fetch_audusd() -> Dict[str, Any]:
    """AUD/USD — Alpha Vantage realtime rate, yfinance fallback."""
    if _ALPHA_VANTAGE_KEY:
        try:
            data = await _av("CURRENCY_EXCHANGE_RATE", {"from_currency": "AUD", "to_currency": "USD"})
            if data and "Realtime Currency Exchange Rate" in data:
                rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                import yfinance as yf
                info = yf.Ticker("AUDUSD=X").fast_info
                prev = getattr(info, "previous_close", rate)
                chg  = round((rate - prev) / prev * 100, 2) if prev > 0 else 0.0
                return {"rate": round(rate, 4), "change_pct": chg, "status": "live"}
        except Exception as e:
            logger.warning("AUD/USD AV: %s", e)

    try:
        import yfinance as yf
        info = yf.Ticker("AUDUSD=X").fast_info
        rate = getattr(info, "last_price", None)
        prev = getattr(info, "previous_close", rate)
        if rate and prev and prev > 0:
            return {"rate": round(float(rate), 4), "change_pct": round((rate - prev) / prev * 100, 2), "status": "live"}
    except Exception as e:
        logger.warning("AUD/USD yfinance: %s", e)

    return {"rate": 0.6500, "change_pct": 0.0, "status": STALE}


async def _fetch_brent() -> Dict[str, Any]:
    """Brent Crude — yfinance BZ=F, FRED DCOILBRENTEU fallback."""
    try:
        import yfinance as yf
        info = yf.Ticker("BZ=F").fast_info
        price = getattr(info, "last_price", None)
        prev  = getattr(info, "previous_close", price)
        if price and prev and prev > 0:
            return {"price": round(float(price), 2), "change_pct": round((price - prev) / prev * 100, 2), "status": "live"}
    except Exception as e:
        logger.warning("Brent yfinance: %s", e)

    if _FRED_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={"series_id": "DCOILBRENTEU", "api_key": _FRED_API_KEY,
                            "file_type": "json", "sort_order": "desc", "limit": 2}
                )
                r.raise_for_status()
                obs = r.json().get("observations", [])
                if len(obs) >= 2:
                    p0 = float(obs[0]["value"])
                    p1 = float(obs[1]["value"])
                    return {"price": round(p0, 2), "change_pct": round((p0 - p1) / p1 * 100, 2), "status": "live"}
        except Exception as e:
            logger.warning("Brent FRED: %s", e)

    return {"price": 82.5, "change_pct": 0.0, "status": STALE}


async def _fetch_ticker_technicals(ticker: str) -> Dict[str, Any]:
    """Ticker price, intraday price change %, volume ratio, RSI(14), MACD signal."""
    result: Dict[str, Any] = {
        "price": 47.0, "price_change_pct": None, "volume_vs_avg": 1.0,
        "rsi": None, "macd_signal": "NEUTRAL", "status": STALE
    }

    # Price + volume + intraday change via yfinance
    try:
        import yfinance as yf
        t    = yf.Ticker(ticker)
        info = t.fast_info
        price = float(getattr(info, "last_price", 47.0))
        prev  = float(getattr(info, "previous_close", price))
        result["price"]  = round(price, 2)
        result["status"] = "live"
        if prev > 0:
            result["price_change_pct"] = round((price - prev) / prev * 100, 2)

        # Intraday volume via fast_info — updates live during market hours.
        # fast_info.regular_market_volume = current session's accumulated volume.
        # three_month_average_volume      = rolling 3-month daily avg (baseline).
        # This avoids the daily-history bug where hist[-1] stays frozen at the
        # previous close's volume until the current session data arrives via history().
        intraday_vol = getattr(info, "regular_market_volume", None)
        avg_3m       = getattr(info, "three_month_average_volume", None)
        if intraday_vol and avg_3m and avg_3m > 0:
            result["volume_vs_avg"] = round(float(intraday_vol) / float(avg_3m), 2)
            logger.info("[VOLUME] %s intraday=%s avg3m=%s ratio=%.2f",
                        ticker, intraday_vol, avg_3m, result["volume_vs_avg"])
        else:
            # Fallback to daily history only when fast_info fields unavailable
            hist = t.history(period="31d")
            if not hist.empty and len(hist) > 1:
                avg_vol = hist["Volume"].iloc[:-1].mean()
                today   = hist["Volume"].iloc[-1]
                if avg_vol > 0:
                    result["volume_vs_avg"] = round(today / avg_vol, 2)
                    logger.info("[VOLUME] %s daily fallback ratio=%.2f", ticker, result["volume_vs_avg"])
    except Exception as e:
        logger.warning("Ticker price yfinance (%s): %s", ticker, e)

    # Intraday price change % via Alpha Vantage GLOBAL_QUOTE (more reliable than yfinance fast_info)
    if _ALPHA_VANTAGE_KEY and result["price_change_pct"] is None:
        try:
            data = await _av("GLOBAL_QUOTE", {"symbol": ticker})
            if data and "Global Quote" in data:
                raw = data["Global Quote"].get("10. change percent", "")
                if raw:
                    result["price_change_pct"] = round(float(raw.replace("%", "").strip()), 2)
        except Exception as e:
            logger.warning("Ticker GLOBAL_QUOTE AV (%s): %s", ticker, e)

    # RSI via Alpha Vantage
    if _ALPHA_VANTAGE_KEY:
        try:
            data = await _av("RSI", {"symbol": ticker, "interval": "daily", "time_period": 14, "series_type": "close"})
            if data and "Technical Analysis: RSI" in data:
                latest = sorted(data["Technical Analysis: RSI"].keys())[-1]
                result["rsi"] = round(float(data["Technical Analysis: RSI"][latest]["RSI"]), 1)
        except Exception as e:
            logger.warning("RSI AV: %s", e)

        # MACD signal via Alpha Vantage
        try:
            data = await _av("MACD", {"symbol": ticker, "interval": "daily", "series_type": "close"})
            if data and "Technical Analysis: MACD" in data:
                latest   = sorted(data["Technical Analysis: MACD"].keys())[-1]
                macd_val = float(data["Technical Analysis: MACD"][latest]["MACD"])
                sig_val  = float(data["Technical Analysis: MACD"][latest]["MACD_Signal"])
                if macd_val > sig_val:
                    result["macd_signal"] = "BULLISH_CROSS"
                elif macd_val < sig_val:
                    result["macd_signal"] = "BEARISH_CROSS"
                else:
                    result["macd_signal"] = "NEUTRAL"
        except Exception as e:
            logger.warning("MACD AV: %s", e)

    return result


def log_news_date_range(news_items: list, label: str = "NEWS") -> None:
    """Logs the date range of a news item list. Call before and after filtering."""
    if not news_items:
        logger.info("[%s] No news items", label)
        return
    dates = []
    for item in news_items:
        raw = (item.get("published_at") or item.get("event_date")
               or item.get("date") or item.get("timestamp"))
        if raw:
            dates.append(str(raw))
    if dates:
        dates.sort()
        logger.info("[%s] %d items | oldest: %s | newest: %s",
                    label, len(news_items), dates[0], dates[-1])
    else:
        logger.info("[%s] %d items (no parseable dates)", label, len(news_items))


def filter_stale_news(
    news_items: list,
    max_age_days: int = 7,
    ticker: str = "BHP",
) -> tuple:
    """
    Hard date filter — drops any news item older than max_age_days.
    Company-specific news (mentioning ticker) gets a 14-day window.
    Returns (fresh_items, dropped_items) for transparency logging.
    Prevents 2025-dated events appearing in 2026 predictions.
    """
    now         = datetime.now(timezone.utc)
    ticker_clean = ticker.replace(".AX", "").upper()
    fresh:   list = []
    dropped: list = []

    for item in news_items:
        raw_date = (
            item.get("event_date") or item.get("date")
            or item.get("published_at") or item.get("timestamp")
            or item.get("created_at")
        )
        if not raw_date:
            item["date_verified"] = False
            fresh.append(item)
            continue
        try:
            raw_str = str(raw_date).strip()
            if "T" in raw_str or " " in raw_str:
                dt = datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(raw_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            age_days = (now - dt).days

            # Company-specific news stays relevant longer
            headline         = (item.get("headline", "") or item.get("title", ""))
            is_company_news  = ticker_clean in headline.upper()
            cutoff           = 14 if is_company_news else max_age_days

            if age_days <= cutoff:
                item["hours_old"]     = age_days * 24
                item["date_verified"] = True
                fresh.append(item)
            else:
                dropped.append({
                    "headline": headline[:80],
                    "date":     raw_str,
                    "age_days": age_days,
                    "reason":   f"older than {cutoff} days",
                })
        except (ValueError, TypeError) as e:
            item["date_verified"] = False
            fresh.append(item)
            logger.warning("[NEWS FILTER] Could not parse date '%s': %s", raw_date, e)

    if dropped:
        logger.info("[NEWS FILTER] Dropped %d stale items:", len(dropped))
        for d in dropped:
            logger.info("  - %s | %s | %dd old", d["headline"], d["date"], d["age_days"])

    return fresh, dropped


async def _fetch_news(ticker: str, max_items: int = 8) -> List[Dict[str, Any]]:
    """
    Recent news with relevance weights (company-specific + supply chain boosted).
    Cutoff extended to 72h so company-specific articles are never excluded by age alone.
    Filter threshold lowered to 0.25 so company-specific news at 72h (base=0.2 → boosted 0.85) passes.
    """
    items: List[Dict[str, Any]] = []
    if not _MARKETAUX_KEY:
        return items
    try:
        symbol  = ticker.replace(".AX", "")
        cutoff  = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.marketaux.com/v1/news/all",
                params={"symbols": symbol, "published_after": cutoff,
                        "api_token": _MARKETAUX_KEY, "limit": max_items}
            )
            r.raise_for_status()
            for article in r.json().get("data", []):
                pub = article.get("published_at", "")
                try:
                    pub_dt    = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    hours_old = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
                except Exception:
                    hours_old = 72.0
                # Extract category from MarketAux categories list if available
                cats     = article.get("categories") or []
                category = cats[0].get("name", "") if cats and isinstance(cats[0], dict) else str(cats[0]) if cats else ""
                headline = article.get("title", "")
                w = news_weight(
                    hours_old=hours_old,
                    category=category,
                    headline=headline,
                    ticker=ticker,
                )
                if w > 0.25:
                    items.append({
                        "title":           headline,
                        "summary":         (article.get("description") or "")[:200],
                        "hours_old":       round(hours_old, 1),
                        "weight":          w,
                        "category":        category,
                        "signal_strength": weight_to_label(w),
                        "published_at":    pub,   # kept for filter_stale_news
                    })
    except Exception as e:
        logger.warning("MarketAux news: %s", e)

    log_news_date_range(items, "MARKETAUX_RAW")
    fresh, dropped = filter_stale_news(items, max_age_days=7, ticker=ticker)
    log_news_date_range(fresh, "MARKETAUX_FILTERED")
    # Attach dropped count to each fresh item so fetch_market_context can total it
    for item in fresh:
        item.setdefault("_stale_dropped", len(dropped))
    return fresh[:max_items]


# ── Fetch lessons from prediction_log ─────────────────────────────────────────

async def _fetch_lessons(ticker: str, limit: int = 5) -> List[str]:
    """Fetch the last N reflection lessons for the given ticker from prediction_log."""
    try:
        from database import get_db, init_db
        await init_db()
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                "SELECT lesson FROM prediction_log WHERE ticker=? AND lesson IS NOT NULL "
                "ORDER BY predicted_at DESC LIMIT ?",
                (ticker, limit)
            ) as cur:
                rows = await cur.fetchall()
        return [r["lesson"] for r in rows if r.get("lesson")]
    except Exception as e:
        logger.warning("Could not fetch lessons: %s", e)
        return []


# ── Broad market session fetcher ──────────────────────────────────────────────

async def _fetch_broad_market() -> Dict[str, Any]:
    """
    Fetches ASX 200 (^AXJO) and S&P 500 (^GSPC) intraday % change via Alpha Vantage.
    Classifies session type. Falls back gracefully — never blocks pipeline.
    """
    result: Dict[str, Any] = {
        "axjo_change_pct": None,
        "spx_change_pct":  None,
        "market_session":  "UNKNOWN",
    }

    if not _ALPHA_VANTAGE_KEY:
        return result

    async def _quote(symbol: str) -> Optional[float]:
        try:
            data = await _av("GLOBAL_QUOTE", {"symbol": symbol})
            if data and "Global Quote" in data:
                raw = data["Global Quote"].get("09. change percent", "")
                return round(float(raw.replace("%", "").strip()), 2)
        except Exception as e:
            logger.warning("Broad market quote %s: %s", symbol, e)
        return None

    axjo, spx = await asyncio.gather(_quote("^AXJO"), _quote("^GSPC"))
    result["axjo_change_pct"] = axjo
    result["spx_change_pct"]  = spx

    # Classify session
    if axjo is not None and spx is not None:
        if axjo <= -1.0 and spx <= -1.0:
            result["market_session"] = "BROAD_SELLOFF"
        elif axjo >= 1.0 and spx >= 1.0:
            result["market_session"] = "BROAD_RALLY"
        elif axjo <= -0.5 or spx <= -0.5:
            result["market_session"] = "MILD_RISK_OFF"
        elif axjo >= 0.5 or spx >= 0.5:
            result["market_session"] = "MILD_RISK_ON"
        else:
            result["market_session"] = "FLAT"
    elif axjo is not None:
        if axjo <= -1.0:
            result["market_session"] = "BROAD_SELLOFF"
        elif axjo >= 1.0:
            result["market_session"] = "BROAD_RALLY"

    return result


# ── Trend momentum fetcher ────────────────────────────────────────────────────

def _fetch_daily_prices(ticker: str, days: int = 25) -> Optional[list]:
    """
    Fetch daily closing prices for the last `days` calendar days via yfinance.
    Returns a list of floats (oldest → newest), or None on failure.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{days}d")
        if hist.empty or len(hist) < 2:
            return None
        return list(hist["Close"].dropna())
    except Exception as e:
        logger.warning("[TREND] _fetch_daily_prices failed for %s: %s", ticker, e)
        return None


async def fetch_trend_context(ticker: str) -> Dict[str, Any]:
    """
    Calculate multi-day momentum metrics from daily closing prices.

    Returns:
      trend_label         : "STRONG_DOWNTREND" | "DOWNTREND" | "NEUTRAL" | "UPTREND" | "STRONG_UPTREND"
      day_1_change        : float % (1-day return)
      day_5_change        : float % (5-day return)
      day_20_change       : float % (20-day return)
      consecutive_down_days : int (how many consecutive sessions closed lower)
      dist_from_52w_high_pct: float % (how far below the 52-week high, negative = below)
      trend_block         : str (pre-formatted block for agent prompts)
    """
    _default = {
        "trend_label": "NEUTRAL",
        "day_1_change": None,
        "day_5_change": None,
        "day_20_change": None,
        "consecutive_down_days": 0,
        "dist_from_52w_high_pct": None,
        "trend_block": "=== TREND MOMENTUM ===\nTrend data unavailable.\n=== END TREND ===",
    }

    try:
        # Run in executor to avoid blocking asyncio event loop
        loop = asyncio.get_event_loop()
        prices = await loop.run_in_executor(None, _fetch_daily_prices, ticker, 25)
        if prices is None or len(prices) < 6:
            return _default

        current = prices[-1]

        # Returns
        day_1  = round((prices[-1] / prices[-2] - 1) * 100, 2) if len(prices) >= 2 else None
        day_5  = round((prices[-1] / prices[-6] - 1) * 100, 2) if len(prices) >= 6 else None
        day_20 = round((prices[-1] / prices[0]  - 1) * 100, 2) if len(prices) >= 20 else None

        # Consecutive down days (from most recent session backwards)
        consec_down = 0
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] < prices[i - 1]:
                consec_down += 1
            else:
                break

        # Distance from 52-week high (use the 25 days we have as proxy if <252 days)
        # Attempt a longer fetch for the 52w high
        try:
            import yfinance as yf
            t52 = yf.Ticker(ticker)
            hist52 = await loop.run_in_executor(None, lambda: t52.history(period="252d"))
            if not hist52.empty:
                high_52w = float(hist52["Close"].max())
            else:
                high_52w = max(prices)
        except Exception:
            high_52w = max(prices)

        dist_52w = round((current / high_52w - 1) * 100, 2)  # negative if below

        # Classify trend label
        bearish_score = 0
        if day_5  is not None and day_5  < -3:  bearish_score += 1
        if day_20 is not None and day_20 < -5:  bearish_score += 1
        if consec_down >= 3:                     bearish_score += 1
        if dist_52w < -10:                       bearish_score += 1

        bullish_score = 0
        if day_5  is not None and day_5  > 3:   bullish_score += 1
        if day_20 is not None and day_20 > 5:   bullish_score += 1
        if consec_down == 0 and day_5 is not None and day_5 > 0:  bullish_score += 1
        if dist_52w > -3:                        bullish_score += 1

        if bearish_score >= 3:
            trend_label = "STRONG_DOWNTREND"
        elif bearish_score == 2:
            trend_label = "DOWNTREND"
        elif bullish_score >= 3:
            trend_label = "STRONG_UPTREND"
        elif bullish_score == 2:
            trend_label = "UPTREND"
        else:
            trend_label = "NEUTRAL"

        # Build human-readable trend block
        d1_str  = f"{day_1:+.2f}%"  if day_1  is not None else "N/A"
        d5_str  = f"{day_5:+.2f}%"  if day_5  is not None else "N/A"
        d20_str = f"{day_20:+.2f}%" if day_20 is not None else "N/A"
        d52_str = f"{dist_52w:+.2f}% from 52w high"

        trend_block = (
            f"=== TREND MOMENTUM ===\n"
            f"Trend label: {trend_label}\n"
            f"1-day return: {d1_str} | 5-day: {d5_str} | 20-day: {d20_str}\n"
            f"Consecutive down sessions: {consec_down}\n"
            f"Distance from 52-week high: {d52_str}\n"
            f"=== END TREND ==="
        )

        logger.info(
            "[TREND] %s label=%s 1d=%s 5d=%s 20d=%s consec_down=%d dist52w=%s",
            ticker, trend_label, d1_str, d5_str, d20_str, consec_down, d52_str,
        )

        return {
            "trend_label":            trend_label,
            "day_1_change":           day_1,
            "day_5_change":           day_5,
            "day_20_change":          day_20,
            "consecutive_down_days":  consec_down,
            "dist_from_52w_high_pct": dist_52w,
            "trend_block":            trend_block,
        }

    except Exception as e:
        logger.warning("[TREND] fetch_trend_context failed for %s: %s", ticker, e)
        return _default


# ── Market session confidence modifier ────────────────────────────────────────

def apply_market_session_modifier(
    confidence: float,
    direction: str,
    market_session: str,
) -> tuple:
    """
    Reduces confidence when prediction goes against the broad market.
    direction must be 'bullish' | 'bearish' | 'neutral'.
    Returns (adjusted_confidence, warning_str_or_None).
    """
    contrarian_cases = {
        ("bullish", "BROAD_SELLOFF"):  (0.65, "CONTRARIAN: Bullish call on a broad selloff day — confidence reduced"),
        ("bearish", "BROAD_RALLY"):    (0.70, "CONTRARIAN: Bearish call on a broad rally day — confidence reduced"),
        ("bullish", "MILD_RISK_OFF"):  (0.85, "Mild risk-off session — slight confidence reduction"),
        ("bearish", "MILD_RISK_ON"):   (0.85, "Mild risk-on session — slight confidence reduction"),
    }
    key = (direction.lower(), market_session)
    if key in contrarian_cases:
        multiplier, warning = contrarian_cases[key]
        return round(confidence * multiplier, 3), warning
    return confidence, None


# ── Volume interpretation ──────────────────────────────────────────────────────

def interpret_volume(
    volume_vs_avg: Optional[float],
    price_change_pct: Optional[float] = None,
) -> str:
    """
    Interprets volume paired with intraday price direction.
    Volume alone is ambiguous — direction determines whether it is accumulation or distribution.
    """
    if volume_vs_avg is None:
        return "Volume: UNAVAILABLE"

    if volume_vs_avg >= 3.0:
        vol_level = "EXTREME"
    elif volume_vs_avg >= 2.0:
        vol_level = "HIGH"
    elif volume_vs_avg >= 1.3:
        vol_level = "ELEVATED"
    else:
        vol_level = "NORMAL"

    if vol_level == "NORMAL":
        return f"Volume: {volume_vs_avg:.2f}x avg -> NORMAL — no unusual activity"

    if price_change_pct is not None:
        if price_change_pct <= -0.5 and vol_level in ("EXTREME", "HIGH"):
            return (
                f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} SELLOFF "
                f"(price {price_change_pct:+.2f}% on high volume = "
                f"institutional DISTRIBUTION — STRONGLY BEARISH)"
            )
        elif price_change_pct >= 0.5 and vol_level in ("EXTREME", "HIGH"):
            return (
                f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} RALLY "
                f"(price {price_change_pct:+.2f}% on high volume = "
                f"institutional ACCUMULATION — STRONGLY BULLISH)"
            )
        elif abs(price_change_pct) < 0.5 and vol_level in ("EXTREME", "HIGH"):
            return (
                f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} INDECISION "
                f"(price flat {price_change_pct:+.2f}% on high volume = "
                f"contested session — NEUTRAL)"
            )
        # ELEVATED level with price direction
        if price_change_pct < -0.5:
            return f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} (price {price_change_pct:+.2f}% — moderate selling pressure)"
        elif price_change_pct > 0.5:
            return f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} (price {price_change_pct:+.2f}% — moderate buying pressure)"
        return f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} (price flat — indecision)"

    # No price direction available
    return (
        f"Volume: {volume_vs_avg:.2f}x avg -> {vol_level} "
        f"(direction unknown — DO NOT assume bullish or bearish. "
        f"Wait for price confirmation before voting directionally.)"
    )


# ── Data quality checker ───────────────────────────────────────────────────────

def check_data_quality(market_data: dict) -> dict:
    """
    Audits fetched market data and flags stale/missing fields.
    Returns a quality report injected into the API response.
    """
    issues: List[str] = []
    stale_fields: List[str] = []

    required_fields = {
        "iron_ore_price":      (50, 200),
        "audusd_rate":         (0.50, 0.90),
        "brent_price":         (40, 150),
        "ticker_price":        (5, 500),
        "ticker_volume_vs_avg": (0, 20),
        "ticker_rsi":          (1, 99),   # None already caught by RSI fix
    }

    for field, (min_val, max_val) in required_fields.items():
        val = market_data.get(field)
        if val is None:
            stale_fields.append(field)
            issues.append(f"{field}: MISSING")
        elif not (min_val <= float(val) <= max_val):
            stale_fields.append(field)
            issues.append(f"{field}: OUT OF RANGE ({val})")

    data_quality = "GOOD" if not issues else ("PARTIAL" if len(issues) == 1 else "POOR")

    return {
        "data_quality":      data_quality,
        "stale_fields":      stale_fields,
        "data_issues":       issues,
        "show_data_warning": data_quality == "POOR",
    }


# ── Open-Meteo: Port Hedland weather (no API key) ─────────────────────────────

# WMO weather code → severity label
_WMO_SEVERE = {95, 96, 97, 98, 99}   # thunderstorm / tropical storm
_WMO_DISRUPT = {51,53,55,61,63,65,80,81,82,85,86}  # rain / showers

async def _fetch_weather_port_hedland() -> Dict[str, Any]:
    """
    Fetch 3-day weather forecast for Port Hedland (−20.31°S, 118.60°E).
    Uses Open-Meteo — completely free, no API key required.
    Returns a short alert string when conditions are operationally significant.
    """
    _default = {"alert": "", "status": "unavailable"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude":  -20.31,
                    "longitude": 118.60,
                    "daily": "weathercode,windspeed_10m_max,precipitation_sum",
                    "timezone": "Australia/Perth",
                    "forecast_days": 3,
                },
            )
            r.raise_for_status()
            data = r.json().get("daily", {})

        codes  = data.get("weathercode", [])
        winds  = data.get("windspeed_10m_max", [])
        precip = data.get("precipitation_sum", [])
        days   = ["Today", "Tomorrow", "Day+2"]

        alerts = []
        for i, (code, wind, rain) in enumerate(zip(codes, winds, precip)):
            day = days[i] if i < len(days) else f"Day+{i}"
            wind = float(wind or 0)
            rain = float(rain or 0)
            code = int(code or 0)

            if wind >= 90 or code in _WMO_SEVERE:
                alerts.append(
                    f"[CYCLONE RISK — {day}] Wind {wind:.0f} km/h, "
                    f"rain {rain:.0f}mm — PORT LIKELY CLOSED → STRONGLY BEARISH for iron ore exports"
                )
            elif wind >= 60:
                alerts.append(
                    f"[STORM WARNING — {day}] Wind {wind:.0f} km/h → possible Port Hedland disruption → BEARISH"
                )
            elif wind >= 40 or code in _WMO_DISRUPT:
                alerts.append(
                    f"[WEATHER CAUTION — {day}] Wind {wind:.0f} km/h, rain {rain:.0f}mm → minor disruption risk"
                )

        if not alerts:
            logger.info("[WEATHER] Port Hedland: clear conditions")
            return {"alert": "", "status": "live"}

        alert_str = (
            "=== PORT HEDLAND WEATHER ALERT ===\n"
            + "\n".join(alerts)
            + "\n=== END WEATHER ==="
        )
        logger.info("[WEATHER] Port Hedland alert: %s", alerts[0])
        return {"alert": alert_str, "status": "live"}

    except Exception as e:
        logger.warning("[WEATHER] Port Hedland fetch failed: %s", e)
        return _default


# ── The Guardian: high-quality geopolitical + economic news ───────────────────

async def _fetch_guardian_news(ticker: str, event_keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch relevant articles from The Guardian Open Platform API.
    Free API key — get one at: https://bonobo.capi.guim.co.uk/register/developer
    Set env var: GUARDIAN_API_KEY
    Returns list of news items in the same format as _fetch_news().
    """
    if not _GUARDIAN_API_KEY:
        return []
    try:
        ticker_clean = ticker.replace(".AX", "")
        # Build query: company name + commodity + key event terms
        query_terms = [ticker_clean] + [k for k in event_keywords if len(k) > 4][:4]
        query = " OR ".join(f'"{t}"' for t in query_terms[:4])

        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://content.guardianapis.com/search",
                params={
                    "q":            query,
                    "section":      "business,world,australia-news,environment",
                    "order-by":     "newest",
                    "page-size":    6,
                    "from-date":    since,
                    "show-fields":  "trailText,wordcount",
                    "api-key":      _GUARDIAN_API_KEY,
                },
            )
            r.raise_for_status()
            articles = r.json().get("response", {}).get("results", [])

        items = []
        now = datetime.now(timezone.utc)
        for a in articles:
            pub_str  = a.get("webPublicationDate", "")
            headline = a.get("webTitle", "")
            if not headline:
                continue
            try:
                pub_dt    = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                hours_old = (now - pub_dt).total_seconds() / 3600
            except Exception:
                hours_old = 48.0

            w = news_weight(hours_old=hours_old, category="STRATEGIC", headline=headline, ticker=ticker)
            if w > 0.20:
                items.append({
                    "title":           f"[Guardian] {headline}",
                    "summary":         (a.get("fields", {}).get("trailText") or "")[:200],
                    "hours_old":       round(hours_old, 1),
                    "weight":          w,
                    "signal_strength": weight_to_label(w),
                    "published_at":    pub_str,
                    "source":          "guardian",
                })

        logger.info("[GUARDIAN] %d articles fetched for %s", len(items), ticker)
        return items[:5]

    except Exception as e:
        logger.warning("[GUARDIAN] Fetch failed: %s", e)
        return []


# ── OpenSanctions: sanctions entity check (no API key) ────────────────────────

# Countries known to have active broad sanctions regimes
_SANCTIONED_COUNTRIES = {
    "russia", "iran", "north korea", "myanmar", "belarus",
    "syria", "cuba", "venezuela", "sudan", "zimbabwe",
    "dprk", "crimea", "dpr", "lnr",
}

async def _fetch_sanctions_context(event_keywords: List[str]) -> Dict[str, Any]:
    """
    Check OpenSanctions for entities related to the event.
    No API key required — free public API.
    Returns a short sanctions block if relevant entities are found.
    """
    _empty = {"block": "", "count": 0}
    try:
        # Only query if event involves a sanctioned country/context
        kw_lower = {k.lower() for k in event_keywords}
        if not kw_lower.intersection(_SANCTIONED_COUNTRIES):
            return _empty

        # Use the most specific sanctioned country keyword as the query
        query_term = next(k for k in kw_lower if k in _SANCTIONED_COUNTRIES)

        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.opensanctions.org/search/default",
                params={"q": query_term, "schema": "Organization", "limit": 5},
            )
            r.raise_for_status()
            results = r.json().get("results", [])

        if not results:
            return _empty

        names = [e.get("caption", "") for e in results[:3] if e.get("caption")]
        count = len(results)
        block = (
            f"=== SANCTIONS CONTEXT ===\n"
            f"OpenSanctions: {count} sanctioned entities found related to '{query_term}'\n"
            f"Examples: {', '.join(names)}\n"
            f"IMPLICATION: Sanctions exposure → supply chain risk, payment disruption, demand uncertainty → BEARISH bias\n"
            f"=== END SANCTIONS ==="
        )
        logger.info("[SANCTIONS] %d entities found for '%s'", count, query_term)
        return {"block": block, "count": count}

    except Exception as e:
        logger.warning("[SANCTIONS] Fetch failed: %s", e)
        return _empty


# ── Finnhub: earnings surprise + sentiment (free key) ─────────────────────────

async def _fetch_finnhub_signals(ticker: str) -> Dict[str, Any]:
    """
    Fetch latest earnings surprise and recommendation trend from Finnhub.
    Free API key (60 calls/min) — sign up at https://finnhub.io
    Set env var: FINNHUB_API_KEY
    Returns a 1-line signal for the agent prompt.
    """
    _empty = {"line": "", "status": "unavailable"}
    if not _FINNHUB_API_KEY:
        return _empty
    try:
        # Finnhub uses ticker without .AX for international stocks
        fh_ticker = ticker.replace(".AX", "")
        async with httpx.AsyncClient(timeout=8.0) as client:
            earnings_r, rec_r = await asyncio.gather(
                client.get(
                    "https://finnhub.io/api/v1/stock/earnings",
                    params={"symbol": fh_ticker, "limit": 1, "token": _FINNHUB_API_KEY},
                ),
                client.get(
                    "https://finnhub.io/api/v1/stock/recommendation",
                    params={"symbol": fh_ticker, "token": _FINNHUB_API_KEY},
                ),
                return_exceptions=True,
            )

        lines = []

        # Latest earnings beat/miss
        if not isinstance(earnings_r, Exception) and earnings_r.status_code == 200:
            eps_data = earnings_r.json()
            if eps_data:
                latest = eps_data[0]
                actual   = latest.get("actual")
                estimate = latest.get("estimate")
                period   = latest.get("period", "")
                if actual is not None and estimate is not None and estimate != 0:
                    surprise_pct = round((actual - estimate) / abs(estimate) * 100, 1)
                    if surprise_pct > 5:
                        lines.append(
                            f"Finnhub Earnings ({period}): BEAT by {surprise_pct:+.1f}% "
                            f"(EPS actual={actual} vs est={estimate}) → BULLISH"
                        )
                    elif surprise_pct < -5:
                        lines.append(
                            f"Finnhub Earnings ({period}): MISSED by {surprise_pct:+.1f}% "
                            f"(EPS actual={actual} vs est={estimate}) → BEARISH"
                        )
                    else:
                        lines.append(
                            f"Finnhub Earnings ({period}): IN LINE (EPS {actual} vs est {estimate}) → NEUTRAL"
                        )

        # Analyst recommendations
        if not isinstance(rec_r, Exception) and rec_r.status_code == 200:
            rec_data = rec_r.json()
            if rec_data:
                latest_rec = rec_data[0]
                buy        = latest_rec.get("buy", 0) + latest_rec.get("strongBuy", 0)
                sell       = latest_rec.get("sell", 0) + latest_rec.get("strongSell", 0)
                hold       = latest_rec.get("hold", 0)
                total      = buy + sell + hold
                if total > 0:
                    buy_pct = round(buy / total * 100)
                    lines.append(
                        f"Analyst consensus: {buy} BUY / {hold} HOLD / {sell} SELL "
                        f"({buy_pct}% bullish) — {latest_rec.get('period', '')}"
                    )

        if not lines:
            return _empty

        logger.info("[FINNHUB] Signals for %s: %s", ticker, lines[0][:60])
        return {"line": " | ".join(lines), "status": "live"}

    except Exception as e:
        logger.warning("[FINNHUB] Fetch failed for %s: %s", ticker, e)
        return _empty


# ── GNews: real-time news including Chinese sources (free key) ─────────────────

async def _fetch_gnews(ticker: str, event_keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch relevant news from GNews — covers Chinese-language sources.
    Free key: 100 req/day — sign up at https://gnews.io
    Set env var: GNEWS_API_KEY
    Returns list of news items compatible with _fetch_news() format.
    """
    if not _GNEWS_API_KEY:
        return []
    try:
        ticker_clean = ticker.replace(".AX", "")
        # Narrow query to avoid noise
        commodity_terms = [t for t in event_keywords if t in (
            "iron ore", "coal", "copper", "gold", "lithium", "oil", "gas",
            "china", "australia", "mining", "steel", "bhp", "rio", "fmg",
        )]
        query = " ".join([ticker_clean] + commodity_terms[:2]) or ticker_clean

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://gnews.io/api/v4/search",
                params={
                    "q":       query,
                    "lang":    "en",
                    "country": "au",
                    "max":     5,
                    "sortby":  "publishedAt",
                    "apikey":  _GNEWS_API_KEY,
                },
            )
            r.raise_for_status()
            articles = r.json().get("articles", [])

        items = []
        now = datetime.now(timezone.utc)
        for a in articles:
            headline = a.get("title", "")
            pub_str  = a.get("publishedAt", "")
            if not headline:
                continue
            try:
                pub_dt    = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                hours_old = (now - pub_dt).total_seconds() / 3600
            except Exception:
                hours_old = 48.0

            w = news_weight(hours_old=hours_old, headline=headline, ticker=ticker)
            if w > 0.20:
                items.append({
                    "title":           f"[GNews] {headline}",
                    "summary":         (a.get("description") or "")[:200],
                    "hours_old":       round(hours_old, 1),
                    "weight":          w,
                    "signal_strength": weight_to_label(w),
                    "published_at":    pub_str,
                    "source":          "gnews",
                })

        logger.info("[GNEWS] %d articles for %s", len(items), ticker)
        return items[:4]

    except Exception as e:
        logger.warning("[GNEWS] Fetch failed: %s", e)
        return []


# ── Polymarket prediction market fetcher ───────────────────────────────────────

# Maps ASX tickers to commodity/macro keywords for Polymarket search
_TICKER_TOPICS: Dict[str, List[str]] = {
    "BHP.AX":  ["iron ore", "copper", "coal", "mining", "bhp", "australia", "china steel"],
    "RIO.AX":  ["iron ore", "aluminium", "aluminum", "mining", "rio tinto", "australia", "china"],
    "FMG.AX":  ["iron ore", "fortescue", "australia", "pilbara", "china", "steel"],
    "WDS.AX":  ["lng", "gas", "oil", "energy", "woodside", "australia"],
    "STO.AX":  ["oil", "gas", "energy", "santos", "australia", "lng"],
    "NCM.AX":  ["gold", "mining", "newcrest", "australia"],
    "NST.AX":  ["gold", "mining", "australia"],
    "OZL.AX":  ["copper", "mining", "australia"],
    "S32.AX":  ["aluminium", "manganese", "coal", "mining", "south32", "australia"],
    "MIN.AX":  ["lithium", "iron ore", "mineral resources", "australia"],
    "PLS.AX":  ["lithium", "battery", "ev", "pilbara minerals", "australia"],
    "TWE.AX":  ["wine", "china tariff", "agriculture", "australia"],
    "WBC.AX":  ["bank", "rba", "interest rate", "australia", "housing"],
    "CBA.AX":  ["bank", "rba", "interest rate", "australia", "housing"],
}

# Commodity/macro terms always relevant for ASX mining/resources market
_ALWAYS_RELEVANT = [
    "iron ore", "china", "australia", "commodity", "oil", "gold", "copper",
    "aud", "rba", "interest rate", "steel", "coal", "lithium", "mining",
    "russia", "ukraine", "middle east", "taiwan", "sanctions",
]


def _score_polymarket(question: str, keywords: List[str]) -> float:
    """Score a Polymarket question by exact keyword overlap. Higher = more relevant."""
    q = question.lower()
    score = 0.0
    for kw in keywords:
        if kw.lower() in q:
            score += 1.0
            # Bonus for high-relevance commodity terms
            if kw in ("iron ore", "china", "australia", "copper", "gold"):
                score += 0.5
    return score


async def fetch_polymarket_context(
    event_keywords: List[str],
    ticker: str,
) -> Dict[str, Any]:
    """
    Fetch relevant Polymarket prediction markets for this event + ticker.

    Uses the public Polymarket Gamma API (no auth required, no API key needed).
    Returns top 5 markets scored by relevance, formatted as a prompt block.
    Never blocks simulation — returns graceful empty result on any failure.
    """
    _empty = {
        "markets": [],
        "polymarket_block": "",   # empty = don't add noise to prompt if no data
        "status": "unavailable",
    }

    try:
        ticker_topics = _TICKER_TOPICS.get(ticker, [])
        all_keywords  = list(set(event_keywords + ticker_topics + _ALWAYS_RELEVANT))

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false", "limit": 200},
            )
            r.raise_for_status()
            raw = r.json()

        if not isinstance(raw, list):
            logger.warning("[POLYMARKET] Unexpected response type: %s", type(raw))
            return _empty

        scored = []
        for m in raw:
            question = m.get("question", "")
            if not question:
                continue
            score = _score_polymarket(question, all_keywords)
            if score < 1.0:
                continue

            # Parse outcomes and prices (Polymarket stores them as JSON strings)
            try:
                outcomes   = json.loads(m.get("outcomes", "[]"))    if isinstance(m.get("outcomes"),      str) else []
                price_list = json.loads(m.get("outcomePrices", "[]")) if isinstance(m.get("outcomePrices"), str) else []
                prices     = [float(p) for p in price_list]
            except Exception:
                outcomes, prices = [], []

            volume    = float(m.get("volume",    0) or 0)
            end_date  = (m.get("endDate") or "")[:10] or "open"

            # Build outcome display string
            if len(outcomes) == 2 and len(prices) == 2:
                yes_pct = round(prices[0] * 100)
                no_pct  = round(prices[1] * 100)
                outcome_str = f"YES {yes_pct}% / NO {no_pct}%"
                if yes_pct >= 65:
                    signal = "BULLISH_SIGNAL"
                elif yes_pct <= 35:
                    signal = "BEARISH_SIGNAL"
                else:
                    signal = "NEUTRAL"
                yes_prob = prices[0]
            elif len(outcomes) > 2 and prices:
                best_i    = prices.index(max(prices))
                best_out  = outcomes[best_i] if best_i < len(outcomes) else "?"
                best_pct  = round(max(prices) * 100)
                outcome_str = f"Leading: {best_out} ({best_pct}%)"
                signal      = "NEUTRAL"
                yes_prob    = None
            else:
                outcome_str = "prices unavailable"
                signal      = "NEUTRAL"
                yes_prob    = None

            scored.append({
                "question":        question,
                "outcome_str":     outcome_str,
                "signal":          signal,
                "volume_usd":      round(volume),
                "end_date":        end_date,
                "relevance_score": score,
                "yes_probability": yes_prob,
            })

        # Sort: relevance first, then volume
        scored.sort(key=lambda x: (-x["relevance_score"], -x["volume_usd"]))
        top = scored[:5]

        if not top:
            return _empty

        lines = [
            "=== PREDICTION MARKET SIGNALS (Polymarket — Real Money) ===",
            "These are financial bets by sophisticated traders. Treat as strong forward-looking signals.",
        ]
        for m in top:
            vol_str = f"${m['volume_usd']:,}" if m["volume_usd"] > 0 else "n/a"
            lines.append(
                f"[{m['signal']}] \"{m['question']}\"\n"
                f"  Odds: {m['outcome_str']} | Volume: {vol_str} | Expires: {m['end_date']}"
            )
        lines.append("=== END PREDICTION MARKETS ===")

        logger.info("[POLYMARKET] %d relevant markets for %s", len(top), ticker)
        return {
            "markets":         top,
            "polymarket_block": "\n".join(lines),
            "status":          "live",
        }

    except Exception as e:
        logger.warning("[POLYMARKET] Failed: %s", e)
        return _empty


# ── Main entry point ───────────────────────────────────────────────────────────

async def fetch_market_context(ticker: str, event_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch all live market data for the given ticker in parallel.

    Results are cached for 4 minutes (MarketDataCache TTL=240s) to avoid
    redundant API calls, while ensuring volume/price data refreshes frequently
    enough to differ across simulations run minutes apart.

    Returns a dict with:
      - individual numeric fields (iron_ore_price, audusd_rate, etc.)
      - context_block: pre-formatted string to inject into every agent prompt
      - lessons: list of reflection lessons from prediction_log
      - fetched_at: ISO timestamp string
    """
    cache_key = f"market_context_{ticker}"
    cached = market_cache.get(cache_key)
    if cached is not None:
        return cached

    fetch_start = datetime.now(timezone.utc)
    logger.info("[MARKET] Fresh fetch starting for %s ...", ticker)

    results = await asyncio.gather(
        _fetch_iron_ore(),                                          # 0
        _fetch_audusd(),                                            # 1
        _fetch_brent(),                                             # 2
        _fetch_ticker_technicals(ticker),                           # 3
        _fetch_news(ticker),                                        # 4
        _fetch_lessons(ticker),                                     # 5
        _fetch_broad_market(),                                      # 6
        fetch_trend_context(ticker),                                # 7
        fetch_polymarket_context(event_keywords or [], ticker),     # 8
        _fetch_weather_port_hedland(),                              # 9
        _fetch_guardian_news(ticker, event_keywords or []),         # 10
        _fetch_sanctions_context(event_keywords or []),             # 11
        _fetch_finnhub_signals(ticker),                             # 12
        _fetch_gnews(ticker, event_keywords or []),                 # 13
        return_exceptions=True,
    )

    def safe(r, fallback):
        return fallback if isinstance(r, Exception) else r

    iron       = safe(results[0], {"price": 97.5,  "change_pct": 0.0, "status": STALE})
    audusd     = safe(results[1], {"rate":  0.6500, "change_pct": 0.0, "status": STALE})
    brent      = safe(results[2], {"price": 82.5,  "change_pct": 0.0, "status": STALE})
    tech       = safe(results[3], {"price": 47.0,  "volume_vs_avg": 1.0, "rsi": None, "macd_signal": "NEUTRAL", "status": STALE})
    news       = safe(results[4], [])
    lessons    = safe(results[5], [])
    broad      = safe(results[6], {"axjo_change_pct": None, "spx_change_pct": None, "market_session": "UNKNOWN"})
    trend      = safe(results[7], {"trend_label": "NEUTRAL", "day_1_change": None, "day_5_change": None,
                                    "day_20_change": None, "consecutive_down_days": 0,
                                    "dist_from_52w_high_pct": None,
                                    "trend_block": "=== TREND MOMENTUM ===\nTrend data unavailable.\n=== END TREND ==="})
    polymarket = safe(results[8],  {"markets": [], "polymarket_block": "", "status": "unavailable"})
    weather    = safe(results[9],  {"alert": "", "status": "unavailable"})
    guardian   = safe(results[10], [])
    sanctions  = safe(results[11], {"found": False, "block": "", "entities": []})
    finnhub    = safe(results[12], {"signal": "", "status": "unavailable"})
    gnews      = safe(results[13], [])

    fetch_ts = fetch_start.strftime("%Y-%m-%d %H:%M UTC")

    # ── Bug Fix 1: RSI interpretation — never expose raw 50.0 to agents ────────
    raw_rsi = tech.get("rsi")
    if raw_rsi is None or float(raw_rsi) == 50.0:
        ticker_rsi = None
        rsi_label  = f"{ticker} RSI: UNAVAILABLE — skip RSI in technical analysis, use volume and MACD only"
    else:
        ticker_rsi = float(raw_rsi)
        if ticker_rsi >= 70:
            rsi_signal = "OVERBOUGHT"
        elif ticker_rsi <= 30:
            rsi_signal = "OVERSOLD"
        else:
            rsi_signal = "NEUTRAL"
        rsi_label = f"{ticker} RSI(14)={ticker_rsi} -> {rsi_signal}"

    # ── Bug Fix 3: Volume interpretation — direction-aware ────────────────────
    volume_label = interpret_volume(
        volume_vs_avg=tech.get("volume_vs_avg"),
        price_change_pct=tech.get("price_change_pct"),
    )

    def _chg(v: float) -> str:
        return f"{'+' if v >= 0 else ''}{v}%"

    def _stale(d: dict) -> str:
        return " [STALE—use with caution]" if d.get("status") == STALE else ""

    # Broad market session block
    axjo_str = f"{broad['axjo_change_pct']:+.2f}%" if broad["axjo_change_pct"] is not None else "N/A"
    spx_str  = f"{broad['spx_change_pct']:+.2f}%"  if broad["spx_change_pct"]  is not None else "N/A"
    market_session = broad["market_session"]
    broad_block = (
        f"=== BROAD MARKET SESSION ===\n"
        f"ASX 200 today: {axjo_str} | S&P 500 today: {spx_str}\n"
        f"Session type: {market_session}\n"
        f"=== END BROAD MARKET ==="
    )

    # Merge all news sources; Guardian/GNews items may lack signal_strength
    all_news = list(news)
    for item in (guardian + gnews):
        if item not in all_news:
            all_news.append(item)

    news_block = "\n".join(
        f"[{n.get('signal_strength', 'MEDIUM')}] {n['title']} ({n.get('hours_old', '?')}h ago)"
        for n in all_news
    ) if all_news else "No recent news within 24h threshold."

    weather_alert  = weather.get("alert", "")
    sanctions_block = sanctions.get("block", "")
    finnhub_line   = finnhub.get("signal", "")

    lessons_block = (
        "\n".join(f"- {l}" for l in lessons)
        if lessons else "No past lessons available yet."
    )

    poly_block = polymarket["polymarket_block"]

    context_block = f"""{trend['trend_block']}
=== LIVE MARKET CONTEXT (fetched {fetch_ts}) ===
Iron Ore 62% Fe: ${iron['price']}/t | Change: {_chg(iron['change_pct'])}{_stale(iron)}
AUD/USD: {audusd['rate']} | Change: {_chg(audusd['change_pct'])}{_stale(audusd)}
Brent Crude: ${brent['price']}/bbl | Change: {_chg(brent['change_pct'])}{_stale(brent)}
{ticker} Price: ${tech['price']}{_stale(tech)} | {volume_label}
{rsi_label} | MACD Signal: {tech['macd_signal']}
=== END MARKET CONTEXT ===
{broad_block}
{("=== PORT HEDLAND WEATHER ALERT ===\n" + weather_alert + "\n=== END WEATHER ===\n") if weather_alert else ""}{poly_block + chr(10) if poly_block else ""}{(sanctions_block + chr(10)) if sanctions_block else ""}{("=== ANALYST & EARNINGS (Finnhub) ===\n" + finnhub_line + "\n=== END ANALYST ===\n") if finnhub_line else ""}=== NEWS SIGNALS (recency + relevance weighted) ===
{news_block}
=== END NEWS ===
=== LESSONS FROM PAST PREDICTIONS ===
{lessons_block}
=== END LESSONS ==="""

    # ── Bug Fix 5: Data quality audit ──────────────────────────────────────────
    quality_report = check_data_quality({
        "iron_ore_price":      iron["price"],
        "audusd_rate":         audusd["rate"],
        "brent_price":         brent["price"],
        "ticker_price":        tech["price"],
        "ticker_volume_vs_avg": tech.get("volume_vs_avg"),
        "ticker_rsi":          ticker_rsi,
    })

    result = {
        "iron_ore_price":      iron["price"],
        "iron_ore_change_pct": iron["change_pct"],
        "audusd_rate":         audusd["rate"],
        "audusd_change_pct":   audusd["change_pct"],
        "brent_price":             brent["price"],
        "brent_change_pct":        brent["change_pct"],
        "ticker_price":            tech["price"],
        "ticker_price_change_pct": tech.get("price_change_pct"),
        "ticker_volume_vs_avg":    tech.get("volume_vs_avg"),
        "ticker_rsi":              ticker_rsi,
        "ticker_macd_signal":  tech["macd_signal"],
        "news_items":          news,
        "lessons":             lessons,
        "context_block":       context_block,
        "fetched_at":          fetch_ts,
        "data_freshness":      fetch_ts,
        # Bug Fix 5: quality fields propagated to API response
        "data_quality":        quality_report["data_quality"],
        "data_issues":         quality_report["data_issues"],
        "show_data_warning":   quality_report["show_data_warning"],
        # Fix 2: broad market session
        "axjo_change_pct":     broad["axjo_change_pct"],
        "spx_change_pct":      broad["spx_change_pct"],
        "market_session":      market_session,
        # Fix 3: stale news count (taken from first item if any, else 0)
        "stale_news_dropped":  news[0].get("_stale_dropped", 0) if news else 0,
        # Trend Momentum fields
        "trend_label":            trend["trend_label"],
        "day_1_change":           trend.get("day_1_change"),
        "day_5_change":           trend.get("day_5_change"),
        "day_20_change":          trend.get("day_20_change"),
        "consecutive_down_days":  trend.get("consecutive_down_days", 0),
        "dist_from_52w_high_pct": trend.get("dist_from_52w_high_pct"),
        # Polymarket prediction market signals
        "polymarket_markets":     polymarket["markets"],
        "polymarket_status":      polymarket["status"],
        # New API signals
        "weather_alert":          weather_alert,
        "weather_status":         weather.get("status"),
        "sanctions_found":        sanctions.get("found", False),
        "sanctions_entities":     sanctions.get("entities", []),
        "finnhub_signal":         finnhub_line,
        "guardian_news_count":    len(guardian),
        "gnews_count":            len(gnews),
    }

    logger.info("[MARKET] Fetch complete for %s: volume_vs_avg=%.2f price_chg=%s fetched_at=%s",
                ticker,
                result["ticker_volume_vs_avg"] or 0.0,
                result.get("ticker_price_change_pct"),
                fetch_ts)
    market_cache.set(cache_key, result)
    return result
