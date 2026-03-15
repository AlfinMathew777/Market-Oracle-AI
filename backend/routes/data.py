"""API routes for Market Oracle AI data endpoints."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from services.acled_service import ACLEDService
from services.asx_service import ASXService
from services.ais_service import AISService
from services.macro_service import MacroService
from services.abs_service import ABSService
from services.gdelt_service import get_gdelt_sentiment_score
from services.geoscience_service import get_mineral_deposits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])

# Initialize services
acled_service = ACLEDService()
asx_service = ASXService()
ais_service = AISService()
macro_service = MacroService()
abs_service = ABSService()

# Simple in-memory cache (will be replaced with Redis later)
cache = {}
CACHE_TTL = {
    'acled': 1800,  # 30 minutes
    'asx': 300,     # 5 minutes
    'ais': 300      # 5 minutes
}


@router.get("/acled")
async def get_acled_events():
    """
    GET /api/data/acled
    
    Fetch latest 50 ACLED conflict events in GeoJSON format.
    Cache TTL: 1800 seconds (30 minutes)
    
    Returns:
        GeoJSON FeatureCollection with conflict events
    """
    try:
        logger.info("Fetching ACLED events...")
        
        # Get events from service (already returns GeoJSON)
        geojson = acled_service.get_events()
        
        return {
            "status": "success",
            "data": geojson,
            "count": geojson.get('count', 0),
            "cache_ttl": CACHE_TTL['acled']
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/acled: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch ACLED data: {str(e)}")


@router.get("/asx-prices")
async def get_asx_prices():
    """
    GET /api/data/asx-prices
    
    Fetch current prices for BHP.AX, RIO.AX, FMG.AX, CBA.AX, LYC.AX.
    Cache TTL: 300 seconds (5 minutes)
    
    Returns:
        List of ticker price data with change percentages
    """
    try:
        logger.info("Fetching ASX prices...")
        
        prices = asx_service.get_current_prices()
        
        if not prices:
            # If yfinance fails, return cached or error
            raise HTTPException(status_code=503, detail="Unable to fetch ASX prices")
        
        return {
            "status": "success",
            "data": prices,
            "count": len(prices),
            "cache_ttl": CACHE_TTL['asx']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /api/data/asx-prices: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch ASX prices: {str(e)}")


@router.get("/port-hedland")
async def get_port_hedland_status():
    """
    GET /api/data/port-hedland
    
    Fetch Port Hedland vessel status and congestion level.
    Bounding box: lat -20.31 ±1.0, lon 118.58 ±1.5
    Cache TTL: 300 seconds (5 minutes)
    
    Returns:
        vessel_count, bulk_carrier_count, congestion_level (LOW/MEDIUM/HIGH), avg_wait_time
    """
    try:
        logger.info("Fetching Port Hedland AIS data...")
        
        status = ais_service.get_port_hedland_status()
        
        return {
            "status": "success",
            "data": status,
            "cache_ttl": CACHE_TTL['ais'],
            "data_source": status.get('data_source', 'unknown')
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/port-hedland: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Port Hedland data: {str(e)}")


@router.get("/macro-context")
async def get_macro_context():
    """
    GET /api/data/macro-context
    
    Fetch macro economic indicators for the context strip:
    - Fed Funds Rate (FRED)
    - AUD/USD (Yahoo Finance)
    - Iron Ore Spot (Yahoo Finance with fallback)
    - RBA Cash Rate (hardcoded)
    - ASX 200 Index (Yahoo Finance)
    
    Returns:
        Dict with all 5 macro indicators
    """
    try:
        logger.info("Fetching macro context...")
        
        context = macro_service.get_macro_context()
        
        return {
            "status": "success",
            "data": context
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/macro-context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch macro context: {str(e)}")


@router.get("/australian-macro")
async def get_australian_macro():
    """
    GET /api/data/australian-macro
    
    Fetch Australian macroeconomic indicators from ABS and RBA:
    - CPI (inflation)
    - RBA Cash Rate
    - GDP Growth
    - Unemployment Rate
    - Household Debt-to-Income Ratio
    - Household Saving Ratio
    - Terms of Trade Change
    - Labor Productivity Change
    
    Returns:
        Dict with 8+ Australian macro indicators
    """
    try:
        logger.info("Fetching Australian macro indicators...")
        
        macro_data = abs_service.get_australian_macro()
        
        return {
            "status": "success",
            "data": macro_data
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/australian-macro: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Australian macro data: {str(e)}")


@router.get("/gdelt-sentiment")
async def get_gdelt_sentiment(topic: str):
    """
    GET /api/data/gdelt-sentiment?topic=China+Australia+iron+ore
    
    Query GDELT for news sentiment on a topic in the last 24 hours.
    Returns average tone score, article count, and sentiment classification.
    
    Args:
        topic: Search keywords (e.g., "China Australia iron ore", "RBA rate decision")
    
    Returns:
        Dict with avgtone, article_count, sentiment, signal_strength, sample articles
    """
    try:
        logger.info(f"Fetching GDELT sentiment for topic: {topic}")
        
        sentiment_data = get_gdelt_sentiment_score(topic)
        
        return {
            "status": "success",
            "data": sentiment_data
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/gdelt-sentiment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch GDELT sentiment: {str(e)}")


@router.get("/mineral-deposits")
async def get_geo_mineral_deposits(mineral: str = "Lithium"):
    """
    GET /api/data/mineral-deposits?mineral=Lithium
    
    Query Geoscience Australia for major mineral deposit locations.
    
    Args:
        mineral: Commodity type (Lithium, Iron, Rare Earths, Gold, etc.)
    
    Returns:
        List of deposits with name, lat, lon, endowment
    """
    try:
        logger.info(f"Fetching Geoscience Australia deposits for: {mineral}")
        
        deposits = get_mineral_deposits(mineral)
        
        return {
            "status": "success",
            "data": {
                "mineral": mineral,
                "count": len(deposits),
                "deposits": deposits
            }
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/mineral-deposits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch mineral deposits: {str(e)}")


@router.get("/health")
async def data_health_check():
    """Health check for data endpoints."""
    return {
        "status": "healthy",
        "endpoints": [
            "/api/data/acled",
            "/api/data/asx-prices",
            "/api/data/port-hedland",
            "/api/data/macro-context",
            "/api/data/australian-macro",
            "/api/data/gdelt-sentiment",
            "/api/data/mineral-deposits",
            "/api/data/pre-simulation-sentiment"
        ]
    }


@router.get("/pre-simulation-sentiment")
async def get_pre_simulation_sentiment(tickers: str, topic: str):
    """
    GET /api/data/pre-simulation-sentiment?tickers=BHP.AX,RIO.AX&topic=China+iron+ore+ban
    
    Generate combined pre-simulation context by merging:
    - GDELT geopolitical sentiment
    - MarketAux ticker-specific news sentiment
    - Current commodity prices (Brent, Gold) and ticker sensitivity
    
    This is the 'powerful signal' that combines multiple data sources before
    the 50-agent simulation runs.
    
    Args:
        tickers: Comma-separated ASX tickers (e.g., "BHP.AX,RIO.AX,FMG.AX")
        topic: Event topic/description for GDELT query
    
    Returns:
        Dict with combined sentiment, individual signals, and commodity context
    """
    try:
        # Parse tickers
        ticker_list = [t.strip() for t in tickers.split(',')]
        
        logger.info(f"Generating pre-simulation context for {len(ticker_list)} tickers, topic: '{topic}'")
        
        # Import and call the pre-simulation context generator
        from services.market_intelligence import get_pre_simulation_context
        
        context = get_pre_simulation_context(ticker_list, topic)
        
        return {
            "status": "success",
            "data": context
        }
        
    except Exception as e:
        logger.error(f"Error in /api/data/pre-simulation-sentiment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate pre-simulation context: {str(e)}")

