"""Geoscience Australia API integration for mineral deposit locations.

Uses Geoscience Australia's Digital Atlas ArcGIS Feature Services to query
major mineral deposit locations (lithium, iron ore, rare earths, gold, etc.).

No API key required - public open data.
"""

import requests
import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Geoscience Australia Digital Atlas Feature Service
# Major Mineral Deposits layer (layer 7)
GA_FEATURE_SERVICE_URL = "https://services.ga.gov.au/gis/rest/services/Australian_Minerals/MapServer/7/query"

# Use mock data for development (real API is slow ~2-5 seconds)
USE_MOCK_GEOSCIENCE = os.getenv("USE_MOCK_GEOSCIENCE", "True").lower() == "true"


def get_mineral_deposits(mineral: str, limit: int = 50) -> List[Dict]:
    """
    Query Geoscience Australia for mineral deposit locations.
    
    Args:
        mineral: Commodity type ("Lithium", "Iron", "Rare Earths", "Gold", etc.)
        limit: Maximum number of deposits to return
    
    Returns:
        List of deposit dicts with name, lat, lon, commodity, endowment_mt
    """
    if USE_MOCK_GEOSCIENCE:
        return _get_mock_deposits(mineral)
    
    try:
        # Build ArcGIS REST query
        # Format: where=COMMODITY LIKE '%Lithium%'&outFields=*&f=json
        query_params = {
            "where": f"COMMODITY LIKE '%{mineral}%'",
            "outFields": "DEPOSIT_NAME,LATITUDE,LONGITUDE,COMMODITY,ENDOWMENT_MT,STATE",
            "f": "json",
            "resultRecordCount": limit,
            "orderByFields": "ENDOWMENT_MT DESC"  # Largest deposits first
        }
        
        logger.info(f"Querying Geoscience Australia for {mineral} deposits...")
        
        response = requests.get(GA_FEATURE_SERVICE_URL, params=query_params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        features = data.get("features", [])
        deposits = []
        
        for feature in features:
            attrs = feature.get("attributes", {})
            
            deposits.append({
                "name": attrs.get("DEPOSIT_NAME", "Unknown"),
                "lat": attrs.get("LATITUDE"),
                "lon": attrs.get("LONGITUDE"),
                "commodity": attrs.get("COMMODITY", ""),
                "endowment_mt": attrs.get("ENDOWMENT_MT", 0),
                "state": attrs.get("STATE", ""),
                "source": "Geoscience Australia"
            })
        
        logger.info(f"Found {len(deposits)} {mineral} deposits")
        return deposits
        
    except Exception as e:
        logger.error(f"Geoscience Australia API error: {str(e)}")
        # Fallback to mock
        return _get_mock_deposits(mineral)


def _get_mock_deposits(mineral: str) -> List[Dict]:
    """Return mock mineral deposit data for Australian strategic resources."""
    
    mock_deposits = {
        "Lithium": [
            {"name": "Greenbushes", "lat": -33.85, "lon": 116.05, "commodity": "Lithium", "endowment_mt": 71.3, "state": "WA"},
            {"name": "Earl Grey", "lat": -27.22, "lon": 120.45, "commodity": "Lithium", "endowment_mt": 189.0, "state": "WA"},
            {"name": "Mount Marion", "lat": -30.12, "lon": 119.48, "commodity": "Lithium", "endowment_mt": 50.2, "state": "WA"},
            {"name": "Pilgangoora", "lat": -21.28, "lon": 118.48, "commodity": "Lithium", "endowment_mt": 35.8, "state": "WA"},
            {"name": "Wodgina", "lat": -21.19, "lon": 118.72, "commodity": "Lithium", "endowment_mt": 32.4, "state": "WA"},
            {"name": "Bald Hill", "lat": -32.18, "lon": 121.32, "commodity": "Lithium", "endowment_mt": 18.7, "state": "WA"}
        ],
        "Iron": [
            {"name": "Mt. Whaleback", "lat": -23.37, "lon": 119.66, "commodity": "Iron", "endowment_mt": 1650.0, "state": "WA"},
            {"name": "Mt. Tom Price", "lat": -22.69, "lon": 117.78, "commodity": "Iron", "endowment_mt": 1200.0, "state": "WA"},
            {"name": "Paraburdoo", "lat": -23.19, "lon": 117.67, "commodity": "Iron", "endowment_mt": 950.0, "state": "WA"},
            {"name": "Hope Downs", "lat": -23.02, "lon": 119.70, "commodity": "Iron", "endowment_mt": 820.0, "state": "WA"},
            {"name": "Jimblebar", "lat": -23.34, "lon": 119.23, "commodity": "Iron", "endowment_mt": 450.0, "state": "WA"},
            {"name": "Christmas Creek", "lat": -22.97, "lon": 119.48, "commodity": "Iron", "endowment_mt": 380.0, "state": "WA"}
        ],
        "Rare Earths": [
            {"name": "Mount Weld", "lat": -28.88, "lon": 122.35, "commodity": "Rare Earths", "endowment_mt": 45.0, "state": "WA"},
            {"name": "Nolans Bore", "lat": -22.11, "lon": 134.87, "commodity": "Rare Earths", "endowment_mt": 56.0, "state": "NT"},
            {"name": "Browns Range", "lat": -18.72, "lon": 128.24, "commodity": "Rare Earths", "endowment_mt": 8.5, "state": "WA"},
            {"name": "Dubbo", "lat": -32.35, "lon": 148.65, "commodity": "Rare Earths", "endowment_mt": 75.0, "state": "NSW"}
        ],
        "Gold": [
            {"name": "Super Pit (Kalgoorlie)", "lat": -30.78, "lon": 121.49, "commodity": "Gold", "endowment_mt": 0.045, "state": "WA"},
            {"name": "Boddington", "lat": -32.78, "lon": 116.47, "commodity": "Gold", "endowment_mt": 0.032, "state": "WA"},
            {"name": "Cadia Valley", "lat": -33.45, "lon": 148.98, "commodity": "Gold", "endowment_mt": 0.028, "state": "NSW"},
            {"name": "Telfer", "lat": -21.72, "lon": 122.18, "commodity": "Gold", "endowment_mt": 0.025, "state": "WA"}
        ]
    }
    
    # Normalize mineral name to match keys
    mineral_key = mineral.capitalize()
    if mineral_key not in mock_deposits:
        # Try partial match
        for key in mock_deposits.keys():
            if mineral.lower() in key.lower():
                mineral_key = key
                break
    
    deposits = mock_deposits.get(mineral_key, [])
    
    logger.info(f"MOCK: Returning {len(deposits)} {mineral} deposits")
    
    # Add source field
    for deposit in deposits:
        deposit['source'] = 'Geoscience Australia Mock Data'
    
    return deposits


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
