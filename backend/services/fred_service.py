"""FRED (Federal Reserve Economic Data) API integration for Australian economic indicators.

Provides real-time Australian macro data from the St. Louis Federal Reserve database.

API key required: Free instant key at fred.stlouisfed.org/docs/api/api_key.html
"""

import requests
import logging
import os
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

# FRED API configuration
FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Australian economic series IDs
FRED_AUSTRALIAN_SERIES = {
    "RBAAONBMIND": "rba_cash_rate",           # RBA Official Cash Rate
    "DEXUSAL": "aud_usd",                     # AUD/USD Exchange Rate
    "LRHUTTTTAUM156S": "unemployment_rate",   # Unemployment Rate
    "IRLTLT01AUM156N": "long_term_rate",      # 10Y Government Bond Yield
    "AUSCPIALLQINMEI": "cpi",                 # CPI All Items
    "AUSGDPRQDSMEI": "gdp_growth",            # GDP Growth Rate
    "NAEXKP01AUQ189S": "exports"              # Exports of Goods and Services
}


def get_all_australian_macro() -> Dict:
    """
    Fetch all 7 key Australian macro indicators from FRED.
    
    Returns:
        Dict with latest values for each indicator
    """
    if not FRED_API_KEY:
        logger.error("FRED API key not configured")
        return {
            'status': 'pending_api_key',
            'message': 'FRED API key not configured. Get free instant key at fred.stlouisfed.org/docs/api (2 minutes)',
            'data': {}
        }
    
    result = {}
    
    for series_id, field_name in FRED_AUSTRALIAN_SERIES.items():
        try:
            params = {
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc"
            }
            
            response = requests.get(FRED_BASE, params=params, timeout=10)
            response.raise_for_status()
            
            observations = response.json().get("observations", [])
            
            if observations and observations[0]["value"] != ".":
                result[field_name] = {
                    "value": float(observations[0]["value"]),
                    "date": observations[0]["date"],
                    "source": "FRED",
                    "series_id": series_id
                }
                logger.info(f"FRED: {field_name} = {result[field_name]['value']}")
            else:
                logger.warning(f"FRED: No data for {series_id}")
                
        except requests.RequestException as e:
            logger.error(f"FRED error fetching {series_id}: {str(e)}")
            continue
        except (ValueError, KeyError) as parse_error:
            logger.error(f"FRED parse error for {series_id}: {parse_error}")
            continue
    
    return {
        'status': 'success',
        'data': result,
        'fetched_at': datetime.utcnow().isoformat()
    }


def get_single_series(series_id: str) -> Dict:
    """Fetch a single FRED series by ID."""
    if not FRED_API_KEY:
        return {
            'status': 'pending_api_key',
            'message': 'FRED API key not configured'
        }
    
    try:
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "limit": 10,
            "sort_order": "desc"
        }
        
        response = requests.get(FRED_BASE, params=params, timeout=10)
        response.raise_for_status()
        
        observations = response.json().get("observations", [])
        
        return {
            'status': 'success',
            'series_id': series_id,
            'observations': observations
        }
        
    except Exception as e:
        logger.error(f"FRED error: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


if __name__ == "__main__":
    # Test FRED service
    print("FRED Australian Macro Service Test")
    print("=" * 60)
    
    result = get_all_australian_macro()
    
    if result['status'] == 'success':
        for field, data in result['data'].items():
            print(f"{field}: {data['value']} (as of {data['date']})")
    else:
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
