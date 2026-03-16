"""Market Oracle AI - FastAPI Backend Server."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging
from pathlib import Path

# Import routes
from routes.data import router as data_router
from routes.simulate import router as simulate_router

# Import services
from services.ais_service import start_ais_background_stream, get_port_hedland_status
from services.fred_service import get_all_australian_macro
from services.news_service import get_asx_news_sentiment
from services.gdelt_service import get_gdelt_sentiment_score

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("🚀 Market Oracle AI starting...")
    start_ais_background_stream()
    logger.info("✓ Startup complete")
    yield


app = FastAPI(
    title="Market Oracle AI API",
    description="ASX prediction platform with 50-agent swarm intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(data_router)
app.include_router(simulate_router)



@app.get("/")
def root():
    return {
        "name": "Market Oracle AI API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "data": [
                "/api/data/acled",
                "/api/data/asx-prices",
                "/api/data/port-hedland",
                "/api/data/macro-context",
                "/api/data/australian-macro",
                "/api/data/gdelt-sentiment",
                "/api/data/mineral-deposits",
                "/api/data/pre-simulation-sentiment"
            ],
            "simulation": [
                "/api/simulate"
            ],
            "health": [
                "/api/health"
            ]
        }
    }


@app.get("/api/health")
async def health_check():
    """Comprehensive health check showing real API connection status for all data sources."""
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
        acled_key = os.getenv("ACLED_API_KEY")
        return "ACLED", {
            "status": "PENDING_KEY" if not acled_key else "OK",
            "note": "Get free key at acleddata.com/access" if not acled_key else "Key configured",
            "source": "acleddata.com"
        }

    # Run all checks concurrently
    results = await asyncio.gather(
        check_fred(), check_marketaux(), check_gdelt(),
        check_yfinance(), check_aisstream(), check_acled()
    )

    data_sources = {name: result for name, result in results}
    live_count = sum(1 for s in data_sources.values() if s.get("status") == "OK")

    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_sources": data_sources,
        "live_data_sources": f"{live_count}/{len(data_sources)}",
        "demo_ready": live_count >= 3,
        "response_time_ms": round((time.time() - t_start) * 1000, 2),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
