"""API routes for Market Oracle AI data endpoints."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from services.acled_service import ACLEDService
from services.asx_service import ASXService
from services.ais_service import AISService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])

# Initialize services
acled_service = ACLEDService()
asx_service = ASXService()
ais_service = AISService()

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
        
        # Get events from service
        events = acled_service.get_recent_events(limit=50)
        
        # Convert to GeoJSON
        geojson = acled_service.to_geojson(events)
        
        return {
            "status": "success",
            "data": geojson,
            "count": len(events),
            "cache_ttl": CACHE_TTL['acled'],
            "data_source": "mock" if acled_service.use_mock else "acled_api"
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


@router.get("/health")
async def data_health_check():
    """Health check for data endpoints."""
    return {
        "status": "healthy",
        "endpoints": [
            "/api/data/acled",
            "/api/data/asx-prices",
            "/api/data/port-hedland"
        ]
    }
