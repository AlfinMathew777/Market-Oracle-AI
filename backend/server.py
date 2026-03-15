"""Market Oracle AI - FastAPI Backend Server."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import logging
from pathlib import Path

# Import routes
from routes.data import router as data_router
from routes.simulate import router as simulate_router

# Import AIS background stream starter
from services.ais_service import start_ais_background_stream

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Oracle AI API",
    description="ASX prediction platform with 50-agent swarm intelligence",
    version="1.0.0"
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


@app.on_event("startup")
async def startup_event():
    """Run initialization tasks on application startup."""
    logger.info("🚀 Market Oracle AI starting...")
    
    # Start AISStream background WebSocket connection
    # This will gracefully handle missing API key with warning log
    start_ais_background_stream()
    
    logger.info("✓ Startup complete")


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
    import time
    from datetime import datetime, timezone
    
    start = time.time()

    status = {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_sources": {}
    }

    # FRED — test live connection
    try:
        from services.fred_service import get_all_australian_macro
        macro = get_all_australian_macro()
        if macro['status'] == 'success':
            status["data_sources"]["FRED"] = {
                "status": "OK" if macro['data'] else "EMPTY",
                "fields_returned": len(macro['data']),
                "source": "fred.stlouisfed.org"
            }
        else:
            status["data_sources"]["FRED"] = {
                "status": "PENDING_KEY",
                "message": macro.get('message', 'Key not configured')
            }
    except Exception as e:
        status["data_sources"]["FRED"] = {"status": "ERROR", "error": str(e)}

    # MarketAux — test live connection
    try:
        from services.news_service import get_asx_news_sentiment
        news = get_asx_news_sentiment(["BHP.AX"], hours=24)
        if news['status'] == 'success':
            status["data_sources"]["MarketAux"] = {
                "status": "OK" if news.get("articles", 0) > 0 else "NO_ARTICLES",
                "articles_returned": news.get("articles", 0),
                "source": "marketaux.com"
            }
        else:
            status["data_sources"]["MarketAux"] = {
                "status": "PENDING_KEY" if 'pending' in news.get('status', '') else "ERROR",
                "message": news.get('message', 'Unknown error')
            }
    except Exception as e:
        status["data_sources"]["MarketAux"] = {"status": "ERROR", "error": str(e)}

    # GDELT — test live connection
    try:
        from services.gdelt_service import get_gdelt_sentiment_score
        gdelt = get_gdelt_sentiment_score("Australia iron ore", max_records=10)
        if gdelt['status'] == 'success' or gdelt['status'] == 'no_data':
            status["data_sources"]["GDELT"] = {
                "status": "OK",
                "source": "gdeltproject.org",
                "cached": gdelt.get("from_cache", False),
                "articles": gdelt.get("article_count", 0)
            }
        elif gdelt['status'] == 'rate_limited':
            status["data_sources"]["GDELT"] = {
                "status": "RATE_LIMITED",
                "message": "Rate limited - using 1hr cache",
                "cached": gdelt.get("from_cache", False)
            }
        else:
            status["data_sources"]["GDELT"] = {
                "status": "ERROR",
                "error": gdelt.get('error', 'Unknown error')
            }
    except Exception as e:
        status["data_sources"]["GDELT"] = {"status": "ERROR", "error": str(e)}

    # yfinance — test live connection
    try:
        import yfinance as yf
        bhp = yf.Ticker("BHP.AX").fast_info
        status["data_sources"]["yfinance"] = {
            "status": "OK",
            "test_ticker": "BHP.AX",
            "last_price": round(bhp.last_price, 2) if hasattr(bhp, 'last_price') else None,
            "source": "finance.yahoo.com"
        }
    except Exception as e:
        status["data_sources"]["yfinance"] = {"status": "ERROR", "error": str(e)}

    # AISStream — check background stream status
    try:
        from services.ais_service import get_port_hedland_status
        ais = get_port_hedland_status()
        key_present = bool(os.getenv("AISSTREAM_API_KEY"))
        
        if ais.get("connected"):
            status["data_sources"]["AISStream"] = {
                "status": "OK",
                "congestion_level": ais.get("congestion_level", "UNKNOWN"),
                "vessel_count": ais.get("vessel_count", 0),
                "source": "aisstream.io"
            }
        elif not key_present:
            status["data_sources"]["AISStream"] = {
                "status": "PENDING_KEY",
                "note": "Get free key at aisstream.io",
                "source": "aisstream.io"
            }
        else:
            status["data_sources"]["AISStream"] = {
                "status": "CONNECTING",
                "message": ais.get("status", "Initializing"),
                "source": "aisstream.io"
            }
    except Exception as e:
        status["data_sources"]["AISStream"] = {"status": "ERROR", "error": str(e)}

    # ACLED — check key presence
    acled_key = os.getenv("ACLED_API_KEY")
    status["data_sources"]["ACLED"] = {
        "status": "LIVE" if acled_key else "PENDING_KEY",
        "note": "Get free key at acleddata.com/access" if not acled_key else "Key configured",
        "source": "acleddata.com"
    }

    status["response_time_ms"] = round((time.time() - start) * 1000, 2)

    # Overall status
    live_count = sum(1 for s in status["data_sources"].values() if s.get("status") == "OK")
    total_count = len(status["data_sources"])
    status["live_data_sources"] = f"{live_count}/{total_count}"
    status["demo_ready"] = live_count >= 3  # at minimum FRED + MarketAux + yfinance

    return status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
