"""API routes for AussieIntel data endpoints — Redis-first, service fallback."""

from fastapi import APIRouter, HTTPException
from typing import Optional
import asyncio
import logging

from services.acled_service import ACLEDService
from services.asx_service import ASXService
from services.ais_service import AISService
from services.macro_service import MacroService
from services.abs_service import ABSService
from services.gdelt_service import get_gdelt_sentiment_score
from services.geoscience_service import get_mineral_deposits
from services.chokepoint_service import get_all_chokepoint_risks, get_asx_oil_risk_prediction
from services.chokepoint_monitor_service import get_enriched_chokepoint_risks
from services.australian_impact_engine import predict_australian_impact
from services.redis_client import cache_get, cache_set, cache_get_meta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])

# In-memory news cache — fallback when Redis is not configured (local dev)
_news_mem_cache: list = []
_news_mem_ts: float = 0.0

# Services used as live fallbacks when Redis cache is cold
acled_service = ACLEDService()
asx_service   = ASXService()
ais_service   = AISService()
macro_service = MacroService()
abs_service   = ABSService()


# ── ACLED ─────────────────────────────────────────────────────────────────────

@router.get("/acled")
async def get_acled_events():
    """GET /api/data/acled — conflict events GeoJSON.
    Returns live ACLED data when available, falls back to GDELT live news events,
    and uses demo data only as a last resort.
    """
    cached = await cache_get("acled:events:v1")
    if cached and cached.get("status") == "live":
        return {"status": "success", "data": cached,
                "count": cached.get("count", 0), "source": "cache"}

    logger.info("Cache miss — fetching live events")
    try:
        geojson = acled_service.get_events()

        # If ACLED is blocked/unavailable, fall back to live RSS news events
        if geojson.get("status") == "demo":
            logger.info("ACLED unavailable — fetching RSS live events")
            loop = asyncio.get_event_loop()
            rss_data = await loop.run_in_executor(None, acled_service.get_rss_events)

            if rss_data.get("status") == "live":
                await cache_set("acled:events:v1", rss_data, ttl=900)  # 15 min cache
                return {"status": "success", "data": rss_data,
                        "count": rss_data.get("count", 0), "source": "rss_live"}

            # RSS also failed — cache demo data briefly so we don't hammer feeds
            await cache_set("acled:events:v1", geojson, ttl=300)
            return {"status": "success", "data": geojson,
                    "count": geojson.get("count", 0), "source": "demo"}

        # ACLED returned real data — cache for 6 hours
        await cache_set("acled:events:v1", geojson, ttl=21600)
        return {"status": "success", "data": geojson,
                "count": geojson.get("count", 0), "source": "live"}
    except Exception as e:
        logger.error("Events fetch failed: %s", e)
        raise HTTPException(status_code=503, detail="Event data temporarily unavailable")


# ── ASX Prices ────────────────────────────────────────────────────────────────

@router.get("/asx-prices")
async def get_asx_prices():
    """GET /api/data/asx-prices — current ticker prices, served from Redis cache."""
    cached = await cache_get("asx:prices:v1")
    if cached:
        return {"status": "success", "data": cached,
                "count": len(cached), "source": "cache"}

    logger.info("Redis miss — fetching ASX prices live")
    try:
        prices = asx_service.get_current_prices()
        if not prices:
            raise HTTPException(status_code=503, detail="Unable to fetch ASX prices")
        await cache_set("asx:prices:v1", prices, ttl=300)
        return {"status": "success", "data": prices,
                "count": len(prices), "source": "live"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ASX prices live fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch ASX prices")


# ── Port Hedland (AIS) ────────────────────────────────────────────────────────

@router.get("/port-hedland")
async def get_port_hedland_status():
    """GET /api/data/port-hedland — vessel snapshot from AIS relay via Redis."""
    cached = await cache_get("ais:port-hedland:v1")
    if cached:
        return {"status": "success", "data": cached,
                "source": "ais_relay", "cache_ttl": 120}

    # Fall back to in-process WebSocket data if relay not up yet
    status = ais_service.get_port_hedland_status()
    return {"status": "success", "data": status,
            "source": status.get("data_source", "in_process"), "cache_ttl": 300}


# ── Macro Context ─────────────────────────────────────────────────────────────

@router.get("/macro-context")
async def get_macro_context():
    """GET /api/data/macro-context — AUD/USD, iron ore, ASX 200, RBA rate."""
    cached = await cache_get("macro:context:v1")
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}

    logger.info("Redis miss — fetching macro context live")
    try:
        context = macro_service.get_macro_context()
        await cache_set("macro:context:v1", context, ttl=3600)
        return {"status": "success", "data": context, "source": "live"}
    except Exception as e:
        logger.error("Macro context live fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch macro context")


# ── Australian Macro (FRED / ABS) ─────────────────────────────────────────────

@router.get("/australian-macro")
async def get_australian_macro():
    """GET /api/data/australian-macro — CPI, unemployment, GDP, savings ratio."""
    cached = await cache_get("macro:fred:v1")
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}

    logger.info("Redis miss — fetching FRED macro live")
    try:
        macro_data = abs_service.get_australian_macro()
        await cache_set("macro:fred:v1", macro_data, ttl=3600)
        return {"status": "success", "data": macro_data, "source": "live"}
    except Exception as e:
        logger.error("Australian macro live fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch Australian macro data")


# ── GDELT Sentiment ───────────────────────────────────────────────────────────

@router.get("/gdelt-sentiment")
async def get_gdelt_sentiment(topic: str):
    """GET /api/data/gdelt-sentiment?topic=China+Australia+iron+ore"""
    import hashlib
    cache_key = "gdelt:" + hashlib.md5(topic.encode()).hexdigest()[:12]
    cached = await cache_get(cache_key)
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}

    try:
        sentiment_data = get_gdelt_sentiment_score(topic)
        await cache_set(cache_key, sentiment_data, ttl=3600)
        return {"status": "success", "data": sentiment_data, "source": "live"}
    except Exception as e:
        logger.error("GDELT sentiment failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch sentiment data")


# ── News ──────────────────────────────────────────────────────────────────────

@router.get("/news")
async def get_news(query: Optional[str] = None, limit: int = 20):
    """GET /api/data/news?query=China+iron+ore&limit=20 — Australian + global news."""
    global _news_mem_cache, _news_mem_ts
    import time as _time

    # Try Redis first, then in-memory fallback
    articles = await cache_get("news:australia:v1") or []

    # Use in-memory cache if Redis miss but we have fresh data (< 15 min)
    if not articles and _news_mem_cache and (_time.time() - _news_mem_ts) < 900:
        articles = _news_mem_cache
        logger.debug("News: using in-memory cache (%d articles)", len(articles))

    # Cache cold — run seed inline so caller gets fresh data
    if not articles:
        logger.info("News cache cold — running inline seed")
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from scripts.seed_au_news import fetch_feed
            import httpx

            RSS_FEEDS = [
                {"url": "https://www.afr.com/rss",                          "source": "AFR",           "region": "AU"},
                {"url": "https://www.smh.com.au/rss/business.xml",          "source": "SMH Business",  "region": "AU"},
                {"url": "https://www.abc.net.au/news/feed/2942460/rss.xml", "source": "ABC Business",  "region": "AU"},
                {"url": "https://stockhead.com.au/feed/",                   "source": "Stockhead",     "region": "AU"},
                {"url": "https://www.miningweekly.com/rss",                 "source": "Mining Weekly", "region": "AU"},
                {"url": "https://oilprice.com/rss/main",                    "source": "OilPrice",      "region": "GLOBAL"},
                {"url": "https://www.mining.com/feed/",                     "source": "Mining.com",    "region": "GLOBAL"},
                {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",      "source": "BBC World",     "region": "GEO"},
            ]

            async with httpx.AsyncClient(
                headers={"User-Agent": "AussieIntel/1.0 news-aggregator"},
                limits=httpx.Limits(max_connections=10),
                timeout=httpx.Timeout(10.0),
            ) as client:
                tasks = [fetch_feed(client, feed) for feed in RSS_FEEDS]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            all_articles = []
            for r in results:
                if isinstance(r, list):
                    all_articles.extend(r)

            seen: set = set()
            unique = []
            for a in all_articles:
                if a["id"] not in seen:
                    seen.add(a["id"])
                    unique.append(a)

            unique.sort(key=lambda a: a["fetchedAt"], reverse=True)

            if unique:
                await cache_set("news:australia:v1", unique, ttl=900)
                _news_mem_cache = unique
                _news_mem_ts = _time.time()
                articles = unique
                logger.info("Inline news seed: %d articles", len(articles))
        except Exception as e:
            logger.warning("Inline news seed failed: %s", e)

    if query:
        keywords = [k.lower() for k in query.split()]
        def score(a):
            text = (a.get("title", "") + " " + a.get("summary", "")).lower()
            return sum(1 for k in keywords if k in text)
        articles = sorted(articles, key=score, reverse=True)

    return {
        "status": "success",
        "data": articles[:limit],
        "count": len(articles),
        "query": query,
    }


# ── Mineral Deposits ──────────────────────────────────────────────────────────

@router.get("/mineral-deposits")
async def get_geo_mineral_deposits(mineral: str = "Lithium"):
    """GET /api/data/mineral-deposits?mineral=Lithium"""
    cache_key = f"geo:mineral:{mineral.lower()}"
    cached = await cache_get(cache_key)
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}

    try:
        deposits = get_mineral_deposits(mineral)
        data = {"mineral": mineral, "count": len(deposits), "deposits": deposits}
        await cache_set(cache_key, data, ttl=86400)
        return {"status": "success", "data": data, "source": "live"}
    except Exception as e:
        logger.error("Mineral deposits fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch mineral deposit data")


# ── Chokepoints ───────────────────────────────────────────────────────────────

@router.get("/chokepoints")
async def get_chokepoints(enriched: bool = True):
    """GET /api/data/chokepoints — maritime chokepoint risk scores."""
    cache_key = "chokepoints:enriched:v1" if enriched else "chokepoints:base:v1"
    cached = await cache_get(cache_key)
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}

    try:
        data = get_enriched_chokepoint_risks() if enriched else get_all_chokepoint_risks()
        await cache_set(cache_key, data, ttl=3600)
        return {"status": "success", "data": data, "source": "live"}
    except Exception as e:
        logger.error("Chokepoints failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch chokepoint data")


@router.get("/chokepoint-impact")
async def get_chokepoint_impact(chokepoints: str, duration_days: int = 7):
    """GET /api/data/chokepoint-impact?chokepoints=hormuz,malacca&duration_days=7"""
    try:
        cp_list = [c.strip() for c in chokepoints.split(",") if c.strip()]
        impact   = predict_australian_impact(cp_list, duration_days)
        oil_risk = get_asx_oil_risk_prediction(cp_list)
        return {"status": "success", "data": {**impact, "oil_risk": oil_risk}}
    except Exception as e:
        logger.error("Chokepoint impact failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to calculate chokepoint impact")


# ── Pre-simulation sentiment ──────────────────────────────────────────────────

@router.get("/pre-simulation-sentiment")
async def get_pre_simulation_sentiment(tickers: str, topic: str):
    """GET /api/data/pre-simulation-sentiment?tickers=BHP.AX,RIO.AX&topic=China+ban"""
    try:
        ticker_list = [t.strip() for t in tickers.split(",")]
        from services.market_intelligence import get_pre_simulation_context
        context = get_pre_simulation_context(ticker_list, topic)
        return {"status": "success", "data": context}
    except Exception as e:
        logger.error("Pre-simulation sentiment failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch pre-simulation sentiment")


# ── RBA ───────────────────────────────────────────────────────────────────────

@router.get("/rba")
async def get_rba_status():
    """GET /api/data/rba — RBA meeting calendar, last decision, meeting-today flag."""
    from services.rba_service import get_rba_status
    cached = await cache_get("rba:status:v1")
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}
    data = get_rba_status()
    await cache_set("rba:status:v1", data, ttl=3600)
    return {"status": "success", "data": data, "source": "live"}


@router.get("/china-demand")
async def get_china_demand_signal():
    """GET /api/data/china-demand — GDELT-based China steel/manufacturing demand signal."""
    cached = await cache_get("signal:china:steel")
    if cached:
        return {"status": "success", "data": cached, "source": "cache"}
    from services.china_demand_service import get_china_demand_signal
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, get_china_demand_signal)
    if data.get("status") == "success":
        await cache_set("signal:china:steel", data, ttl=3600)
    return {"status": "success", "data": data, "source": "live"}


# ── Data-layer health ─────────────────────────────────────────────────────────

@router.get("/health")
async def data_health_check():
    """Health check showing Redis cache freshness for all data sources."""
    import time
    keys = {
        "acled":      ("acled:events:v1",       6 * 60),
        "asx_prices": ("asx:prices:v1",          10),
        "macro":      ("macro:context:v1",        70),
        "fred":       ("macro:fred:v1",           70),
        "news":       ("news:australia:v1",       20),
        "ais":        ("ais:port-hedland:v1",     5),
        "ais_relay":  ("ais:relay:heartbeat",     10),
    }
    now_ms = int(time.time() * 1000)
    results = {}
    for name, (key, max_stale_min) in keys.items():
        meta = await cache_get_meta(key)
        if meta and meta.get("fetchedAt"):
            age_min = (now_ms - meta["fetchedAt"]) / 60000
            results[name] = {
                "status": "OK" if age_min <= max_stale_min else "STALE",
                "age_minutes": round(age_min, 1),
                "max_stale_minutes": max_stale_min,
            }
        else:
            results[name] = {"status": "COLD", "age_minutes": None}

    overall = "healthy" if all(r["status"] == "OK" for r in results.values()) else "degraded"
    return {"status": overall, "caches": results}


# ── Alternative data sources ───────────────────────────────────────────────────

@router.get("/alt-data/health")
async def alt_data_health():
    """GET /api/data/alt-data/health — ping each alternative data source."""
    from data_sources.aggregator import data_aggregator
    return await data_aggregator.health_check_all()


@router.get("/alt-data/sample/{ticker}")
async def alt_data_sample(ticker: str):
    """
    GET /api/data/alt-data/sample/BHP.AX — fetch all sources for a ticker.

    Debug endpoint: shows what signals each source is producing right now.
    Not rate-limited beyond the global 120/min — internal use only.
    """
    from data_sources.aggregator import data_aggregator
    from utils.sector_classifier import get_sector

    ticker = ticker.upper()
    sector = get_sector(ticker)

    all_data = await data_aggregator.gather_all(ticker, sector=sector)
    composite = data_aggregator.aggregate_signal(all_data)

    return {
        "status": "success",
        "ticker": ticker,
        "sector": sector,
        "composite": composite,
        "per_source": {
            name: [p.to_dict() for p in points]
            for name, points in all_data.items()
        },
    }
