"""Market Oracle AI - FastAPI Backend Server."""

import sys
import io
import os

# Force UTF-8 for ALL I/O on Windows before anything else loads
os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Re-wrap stdout/stderr with UTF-8 encoding regardless of terminal settings
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import asyncio
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging
from pathlib import Path

# ── Infrastructure singletons (initialized in lifespan, shared across requests) ─
# These must be module-level so circuit breakers accumulate state across calls.
_llm_router = None        # LLMRouter — circuit breakers only work if reused
_health_monitor = None    # HealthMonitor — tracks stuck/error-loop agents
_error_memory = None      # ErrorMemory — anti-pattern injection


def get_llm_router():
    """Return the shared LLMRouter instance (created at startup)."""
    return _llm_router


def get_health_monitor():
    """Return the shared HealthMonitor instance."""
    return _health_monitor


def get_error_memory():
    """Return the shared ErrorMemory instance."""
    return _error_memory


# Import routes
from routes.data import router as data_router
from routes.simulate import router as simulate_router
from routes.predictions import router as predictions_router
from routes.quant import router as quant_router  # NEW — quant engine endpoints
from routes.reasoning import router as reasoning_router
from routes.trade_execution import router as trade_router
from routes.accuracy import router as accuracy_router
from routes.stream import router as stream_router
from routes.news import router as news_router
from routes.admin import router as admin_router  # Kill switch + system status

# Import services
from services.ais_service import start_ais_background_stream, get_port_hedland_status
from services.fred_service import get_all_australian_macro
from services.news_service import get_asx_news_sentiment
from services.gdelt_service import get_gdelt_sentiment_score

ROOT_DIR = Path(__file__).parent

# Load environment-specific .env file (.env.development / .env.staging / .env.production)
# Falls back to generic .env if the env-specific file doesn't exist.
# config.environment must be imported BEFORE any other module reads env vars.
from config.environment import ENV, log_environment_banner
load_dotenv(ROOT_DIR / '.env')  # base .env still loaded as lowest-priority fallback

# Configure logging with UTF-8 handler so unicode in LLM responses never crashes
_log_handler = logging.StreamHandler(sys.stderr)
_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])

logger = logging.getLogger(__name__)

# ── Sentry (optional — only active when SENTRY_DSN is set) ────────────────────
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1,   # 10% of requests traced
        send_default_pii=False,
    )
    logger.info("Sentry initialised")

# ── API Key auth ───────────────────────────────────────────────────────────────
_API_KEY = os.getenv("API_KEY", "")  # Set in .env / Render env vars


def _check_api_key(request: Request) -> bool:
    """Return True if the request carries a valid API key (or auth is disabled)."""
    if not _API_KEY:
        return True  # Auth not configured — open access (dev mode)
    return request.headers.get("X-API-Key") == _API_KEY


def require_api_key(request: Request):
    """Dependency that enforces API key on mutation endpoints."""
    if not _check_api_key(request):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


async def _prewarm_caches():
    """Pre-populate slow caches in background so first request is instant."""
    from services.asx_service import ASXService
    from services.chokepoint_monitor_service import get_enriched_chokepoint_risks
    from services.acled_service import ACLEDService

    async def warm(name, fn):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, fn)
            logger.info("Cache pre-warmed: %s", name)
        except Exception as e:
            logger.warning("Cache pre-warm failed (%s): %s", name, e)

    asx = ASXService()
    acled = ACLEDService()
    await asyncio.gather(
        warm("ASX prices",   asx.get_current_prices),
        warm("Chokepoints",  get_enriched_chokepoint_risks),
        warm("ACLED events", acled.get_events),
    )


async def _hourly_tasks():
    """Background loop: accuracy checks every hour."""
    while True:
        await asyncio.sleep(3600)
        try:
            from database import run_accuracy_checks
            n = await run_accuracy_checks()
            if n:
                logger.info("Accuracy check: resolved %d predictions", n)
        except Exception as e:
            logger.warning("Hourly accuracy check failed: %s", e)
        try:
            from services.accuracy_tracker import resolve_pending_predictions
            n2 = await resolve_pending_predictions()
            if n2:
                logger.info("Reasoning accuracy check: resolved %d predictions", n2)
        except Exception as e:
            logger.warning("Reasoning accuracy check failed: %s", e)
        try:
            from services.prediction_resolver import auto_resolve_pending_predictions
            n3 = await auto_resolve_pending_predictions(limit=50)
            if n3:
                logger.info("Prediction log: resolved %d predictions", n3)
        except Exception as e:
            logger.warning("Prediction log auto-resolve failed: %s", e)


async def _alert_check_loop():
    """Run all alert checks every 5 minutes."""
    # Brief initial delay so DB and caches are warm before first check
    await asyncio.sleep(120)
    while True:
        try:
            from monitoring.alerts import check_all_alerts
            new = await check_all_alerts()
            if new:
                logger.info("Alert loop: %d new alert(s)", len(new))
        except Exception as e:
            logger.warning("Alert check loop failed: %s", e)
        await asyncio.sleep(300)  # 5 minutes


async def _news_refresh_loop():
    """Refresh Australian news cache every 15 minutes."""
    while True:
        try:
            from scripts.seed_au_news import fetch_feed
            import httpx, time, hashlib
            from services.redis_client import cache_set

            RSS_FEEDS = [
                {"url": "https://www.afr.com/rss",                          "source": "AFR",           "region": "AU"},
                {"url": "https://www.smh.com.au/rss/business.xml",          "source": "SMH Business",  "region": "AU"},
                {"url": "https://www.abc.net.au/news/feed/2942460/rss.xml", "source": "ABC Business",  "region": "AU"},
                {"url": "https://stockhead.com.au/feed/",                   "source": "Stockhead",     "region": "AU"},
                {"url": "https://www.miningweekly.com/rss",                 "source": "Mining Weekly", "region": "AU"},
                {"url": "https://oilprice.com/rss/main",                    "source": "OilPrice",      "region": "GLOBAL"},
                {"url": "https://www.mining.com/feed/",                     "source": "Mining.com",    "region": "GLOBAL"},
                {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",      "source": "BBC World",     "region": "GEO"},
                {"url": "https://www.theaustralian.com.au/feed",            "source": "The Australian","region": "AU"},
                {"url": "https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "source": "RBA",       "region": "AU"},
            ]

            async with httpx.AsyncClient(
                headers={"User-Agent": "AussieIntel/1.0 news-aggregator"},
                limits=httpx.Limits(max_connections=10),
            ) as client:
                results = await asyncio.gather(
                    *[fetch_feed(client, feed) for feed in RSS_FEEDS],
                    return_exceptions=True,
                )

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
                # Also update the in-memory fallback cache in data route
                try:
                    import time as _time
                    from routes.data import _news_mem_cache as _nmc, _news_mem_ts as _nmt
                    import routes.data as _data_mod
                    _data_mod._news_mem_cache = unique
                    _data_mod._news_mem_ts = _time.time()
                except Exception:
                    pass
                logger.info("News cache refreshed: %d articles", len(unique))

        except Exception as e:
            logger.warning("News refresh failed: %s", e)

        await asyncio.sleep(900)  # 15 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global _llm_router, _health_monitor, _error_memory
    logger.info("AussieIntel starting...")

    # Initialise SQLite persistence
    try:
        from database import init_db
        await init_db()
    except Exception as e:
        logger.warning("DB init failed (non-critical): %s", e)

    # ── Infrastructure singletons ─────────────────────────────────────────────
    # LLMRouter must be a singleton so circuit breakers persist across requests.
    # Creating a new LLMRouter per simulation resets all circuit state.
    try:
        from llm_router import LLMRouter
        _llm_router = LLMRouter()
        logger.info("LLMRouter singleton initialised (circuit breakers active)")
    except Exception as e:
        logger.warning("LLMRouter init failed (non-critical): %s", e)

    try:
        from infrastructure.health_monitor import HealthMonitor
        _health_monitor = HealthMonitor(stuck_threshold=60, error_loop_threshold=3)
        logger.info("HealthMonitor initialised")
    except Exception as e:
        logger.warning("HealthMonitor init failed (non-critical): %s", e)

    try:
        from infrastructure.error_memory import ErrorMemory
        _error_memory = ErrorMemory(max_per_ticker=10)
        logger.info("ErrorMemory initialised")
    except Exception as e:
        logger.warning("ErrorMemory init failed (non-critical): %s", e)

    # Start AIS WebSocket stream (fallback for when relay isn't up yet)
    start_ais_background_stream()

    # Pre-warm caches and start background tasks
    asyncio.create_task(_prewarm_caches())
    asyncio.create_task(_hourly_tasks())
    asyncio.create_task(_news_refresh_loop())
    asyncio.create_task(_alert_check_loop())

    # Mark existing garbage predictions and resolve pending ones at boot
    async def _boot_cleanup():
        try:
            from database import mark_existing_garbage_predictions
            n_excl = await mark_existing_garbage_predictions()
            if n_excl:
                logger.info("Boot: excluded %d garbage predictions from stats", n_excl)
        except Exception as e:
            logger.warning("Boot garbage marking failed: %s", e)
        try:
            from services.prediction_resolver import auto_resolve_pending_predictions
            n_res = await auto_resolve_pending_predictions(limit=200)
            if n_res:
                logger.info("Boot: resolved %d pending predictions", n_res)
        except Exception as e:
            logger.warning("Boot prediction resolve failed: %s", e)

    asyncio.create_task(_boot_cleanup())

    log_environment_banner()
    from system_state import PAPER_MODE
    logger.info(
        "Startup complete — ENV=%s | PAPER_MODE=%s | cache pre-warm and accuracy checks running in background",
        ENV,
        PAPER_MODE,
    )
    yield


app = FastAPI(
    title="Market Oracle AI API",
    description="ASX prediction platform with 50-agent swarm intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Configure CORS — supports single URL, comma-separated list, or wildcard "*"
_FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
_LOCAL_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:3001", "http://127.0.0.1:3001",
]
_PROD_ORIGINS = ["https://asx.marketoracle.ai"]

if _FRONTEND_URL == "*":
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        logger.error("CRITICAL: CORS wildcard blocked in production — falling back to safe origin list")
        _ALLOWED_ORIGINS = _PROD_ORIGINS
        _ALLOW_CREDENTIALS = True
    else:
        _ALLOWED_ORIGINS = ["*"]
        _ALLOW_CREDENTIALS = False  # credentials not allowed with wildcard
elif _FRONTEND_URL:
    # Support comma-separated list of allowed origins
    _ALLOWED_ORIGINS = [o.strip() for o in _FRONTEND_URL.split(",") if o.strip()] + _LOCAL_ORIGINS + _PROD_ORIGINS
    _ALLOW_CREDENTIALS = True
else:
    _ALLOWED_ORIGINS = _LOCAL_ORIGINS + _PROD_ORIGINS
    _ALLOW_CREDENTIALS = True

logger.info("CORS allowed origins: %s", _ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Environment"] = ENV
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Include routers
app.include_router(data_router)
app.include_router(simulate_router)
app.include_router(predictions_router)
app.include_router(quant_router)  # NEW — /api/quant/* endpoints
app.include_router(reasoning_router)  # Reasoning Synthesizer — /api/reasoning/*
app.include_router(trade_router)       # Trade execution — /api/trade/*
app.include_router(accuracy_router)    # Accuracy tracking — /api/accuracy/*
app.include_router(stream_router)      # Real-time streaming — /api/stream/*
app.include_router(news_router)        # ASX news aggregator — /api/news/*
app.include_router(admin_router)       # Admin: kill switch, status, data-feeds

FRONTEND_BUILD = ROOT_DIR.parent / "frontend" / "build"


@app.get("/api/health")
async def health_check(request: Request):
    """Comprehensive health check — no auth required, rate-limited to 30/min."""
    t_start = time.time()

    async def check_fred():
        try:
            macro = await asyncio.get_event_loop().run_in_executor(None, get_all_australian_macro)
            if macro['status'] == 'success':
                return "FRED", {"status": "OK" if macro['data'] else "EMPTY", "fields_returned": len(macro['data']), "source": "fred.stlouisfed.org"}
            return "FRED", {"status": "PENDING_KEY", "message": macro.get('message', 'Key not configured')}
        except Exception as e:
            return "FRED", {"status": "ERROR", "error": str(e)}

    async def check_marketaux():
        try:
            news = await asyncio.get_event_loop().run_in_executor(None, lambda: get_asx_news_sentiment(["BHP.AX"], hours=24))
            if news['status'] == 'success':
                return "MarketAux", {"status": "OK" if news.get("articles", 0) > 0 else "NO_ARTICLES", "articles_returned": news.get("articles", 0), "source": "marketaux.com"}
            return "MarketAux", {"status": "PENDING_KEY" if 'pending' in news.get('status', '') else "ERROR", "message": news.get('message', 'Unknown error')}
        except Exception as e:
            return "MarketAux", {"status": "ERROR", "error": str(e)}

    async def check_gdelt():
        try:
            gdelt = await asyncio.get_event_loop().run_in_executor(None, lambda: get_gdelt_sentiment_score("Australia iron ore", max_records=10))
            if gdelt['status'] in ('success', 'no_data'):
                return "GDELT", {"status": "OK", "source": "gdeltproject.org", "cached": gdelt.get("from_cache", False), "articles": gdelt.get("article_count", 0)}
            if gdelt['status'] == 'rate_limited':
                return "GDELT", {"status": "RATE_LIMITED", "message": "Rate limited - using 1hr cache", "cached": gdelt.get("from_cache", False)}
            return "GDELT", {"status": "ERROR", "error": gdelt.get('error', 'Unknown error')}
        except Exception as e:
            return "GDELT", {"status": "ERROR", "error": str(e)}

    async def check_yfinance():
        try:
            import yfinance as yf
            bhp = await asyncio.get_event_loop().run_in_executor(None, lambda: yf.Ticker("BHP.AX").fast_info)
            return "yfinance", {"status": "OK", "test_ticker": "BHP.AX", "last_price": round(bhp.last_price, 2) if hasattr(bhp, 'last_price') else None, "source": "finance.yahoo.com"}
        except Exception as e:
            return "yfinance", {"status": "ERROR", "error": str(e)}

    async def check_aisstream():
        try:
            ais = get_port_hedland_status()
            key_present = bool(os.getenv("AISSTREAM_API_KEY"))
            if ais.get("connected"):
                return "AISStream", {"status": "OK", "congestion_level": ais.get("congestion_level", "UNKNOWN"), "vessel_count": ais.get("vessel_count", 0), "source": "aisstream.io"}
            if not key_present:
                return "AISStream", {"status": "PENDING_KEY", "note": "Get free key at aisstream.io", "source": "aisstream.io"}
            return "AISStream", {"status": "CONNECTING", "message": ais.get("status", "Initializing"), "source": "aisstream.io"}
        except Exception as e:
            return "AISStream", {"status": "ERROR", "error": str(e)}

    async def check_acled():
        email = os.getenv("ACLED_EMAIL")
        password = os.getenv("ACLED_PASSWORD")
        configured = bool(email and password)
        return "ACLED", {
            "status": "OK" if configured else "PENDING_KEY",
            "note": "OAuth credentials configured" if configured else "Set ACLED_EMAIL + ACLED_PASSWORD in .env",
            "source": "acleddata.com"
        }

    results = await asyncio.gather(
        check_fred(), check_marketaux(), check_gdelt(),
        check_yfinance(), check_aisstream(), check_acled()
    )

    data_sources = {name: result for name, result in results}
    live_count = sum(1 for s in data_sources.values() if s.get("status") == "OK")

    # Circuit breaker status — open circuits mean a provider is actively failing
    circuit_status = {}
    if _llm_router is not None:
        try:
            circuit_status = _llm_router.get_circuit_status()
        except Exception:
            pass

    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_sources": data_sources,
        "live_data_sources": f"{live_count}/{len(data_sources)}",
        "demo_ready": live_count >= 3,
        "response_time_ms": round((time.time() - t_start) * 1000, 2),
        "llm_circuits": circuit_status,
    }


@app.get("/api/health/infrastructure")
async def infrastructure_health():
    """Detailed infrastructure status — circuit breakers, agent health, error memory."""
    circuits = {}
    if _llm_router is not None:
        try:
            circuits = _llm_router.get_circuit_status()
        except Exception as e:
            circuits = {"error": str(e)}

    agents = {}
    if _health_monitor is not None:
        try:
            report = _health_monitor.get_health_report()
            agents = {
                aid: {
                    "status": h.status,
                    "recommendation": h.recommendation,
                    "error_count": h.error_count,
                }
                for aid, h in report.items()
            }
        except Exception as e:
            agents = {"error": str(e)}

    memory_summary = {}
    if _error_memory is not None:
        try:
            memory_summary = {
                "tickers_tracked": len(_error_memory._failures),
                "common_mistakes": _error_memory.get_common_mistakes(),
            }
        except Exception as e:
            memory_summary = {"error": str(e)}

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_circuits": circuits,
        "agent_health": agents,
        "error_memory": memory_summary,
    }


# Serve React frontend — MUST be registered after all API routes
if FRONTEND_BUILD.exists() and (FRONTEND_BUILD / "static").exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BUILD / "static")), name="static")

    @app.get("/australia-states.geojson")
    def serve_geojson():
        return FileResponse(str(FRONTEND_BUILD / "australia-states.geojson"), media_type="application/geo+json")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(FRONTEND_BUILD / "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(str(FRONTEND_BUILD / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
