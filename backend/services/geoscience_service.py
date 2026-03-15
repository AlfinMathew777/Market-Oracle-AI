"""Geoscience Australia API integration for mineral deposit locations.

Uses Geoscience Australia's WFS (Web Feature Service) to query major mineral
deposit locations (lithium, iron ore, rare earths, gold, etc.).

No API key required - public open government data.
"""

import requests
import logging
import os
from typing import List, Dict

logger = logging.getLogger(__name__)

# Geoscience Australia WFS endpoint for Critical Minerals
GA_WFS_URL = "https://services.ga.gov.au/gis/services/Critical_Minerals/MapServer/WFSServer"

# REAL DATA - no mock fallback
USE_MOCK_GEOSCIENCE = False


def get_mineral_deposits(mineral: str, limit: int = 50) -> List[Dict]:
    """
    Query Geoscience Australia WFS for mineral deposit locations.
    
    Args:
        mineral: Commodity type ("Lithium", "Iron", "Rare Earths", "Gold", etc.)
        limit: Maximum number of deposits to return
    
    Returns:
        List of deposit dicts with name, lat, lon, commodity, endowment_mt
    """
    try:
        # Build WFS query
        query_params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": "Critical_Minerals:MineralDeposits",
            "outputFormat": "application/json",
            "count": limit,
            "CQL_FILTER": f"COMMODITY LIKE '%{mineral}%'"
        }
        
        logger.info(f"Querying Geoscience Australia WFS for {mineral} deposits...")
        
        response = requests.get(GA_WFS_URL, params=query_params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        features = data.get("features", [])
        
        deposits = []
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])
            
            deposits.append({
                "name": props.get("DEPOSIT_NAME", "Unknown"),
                "lon": coords[0],
                "lat": coords[1],
                "commodity": props.get("COMMODITY", ""),
                "endowment_mt": props.get("ENDOWMENT_MT", 0),
                "state": props.get("STATE", ""),
                "source": "Geoscience Australia WFS (Live)"
            })
        
        logger.info(f"Found {len(deposits)} {mineral} deposits from Geoscience Australia")
        return deposits
        
    except requests.Timeout:
        logger.error("Geoscience Australia WFS timeout (15s)")
        return _error_deposits("API timeout - Geoscience Australia WFS slow")
    except requests.RequestException as e:
        logger.error(f"Geoscience Australia WFS error: {str(e)}")
        return _error_deposits(f"API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error querying Geoscience Australia: {str(e)}")
        return _error_deposits(f"Unexpected error: {str(e)}")


def _error_deposits(error_msg: str) -> List[Dict]:
    """Return error response as empty list with error logged."""
    logger.error(f"Mineral deposits unavailable: {error_msg}")
    return []


if __name__ == "__main__":
    # Test geoscience service
    test_minerals = ["Lithium", "Iron", "Rare Earths", "Gold"]
    
    print("Geoscience Australia Mineral Deposits Service Test")
    print("=" * 60)
    
    for mineral in test_minerals:
        deposits = get_mineral_deposits(mineral)
        print(f"\n{mineral}: {len(deposits)} deposits")
        for dep in deposits[:3]:
            print(f"  - {dep['name']}: {dep['lat']:.2f}, {dep['lon']:.2f} ({dep['endowment_mt']} Mt)")
