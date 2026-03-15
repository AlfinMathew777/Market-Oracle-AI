"""ACLED (Armed Conflict Location & Event Data Project) API integration.

Provides real-time conflict event data from ACLED's researcher API.
Free tier available for research purposes.

API key required: Register at acleddata.com/access
"""

import requests
import logging
import os
from typing import List, Dict

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

# ACLED API configuration
ACLED_EMAIL = os.getenv("ACLED_EMAIL")
ACLED_API_KEY = os.getenv("ACLED_API_KEY")
ACLED_BASE = "https://api.acleddata.com/acled/read"

# Regions with direct ASX stock exposure
RELEVANT_COUNTRIES = [
    "China", "Iran", "Democratic Republic of Congo",
    "Taiwan", "Sudan", "Argentina", "Chile",
    "Papua New Guinea", "Indonesia", "Myanmar",
    "Ukraine", "Russia", "Israel", "Yemen",
    "Australia", "United States", "Singapore"
]


class ACLEDService:
    """Service for fetching real conflict events from ACLED."""
    
    def get_events(self) -> Dict:
        """
        Fetch real conflict events from last 30 days filtered to ASX-relevant regions.
        
        Returns:
            GeoJSON FeatureCollection with conflict events
        """
        # Check if API keys are configured
        if not ACLED_EMAIL or not ACLED_API_KEY:
            logger.error("ACLED API credentials not configured")
            return {
                'type': 'FeatureCollection',
                'count': 0,
                'features': [],
                'error': 'ACLED API key not configured',
                'status': 'pending_api_key',
                'message': 'Get free researcher key at acleddata.com/access (5 minutes)'
            }
        
        try:
            params = {
                "key": ACLED_API_KEY,
                "email": ACLED_EMAIL,
                "country": "|".join(RELEVANT_COUNTRIES),
                "fields": "event_id_cnty|event_date|event_type|country|location|latitude|longitude|fatalities|notes",
                "limit": 50,
                "format": "json",
                "order": "event_date:desc"
            }
            
            logger.info(f"Fetching ACLED events for {len(RELEVANT_COUNTRIES)} countries...")
            
            response = requests.get(ACLED_BASE, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            events = data.get("data", [])
            
            # Convert to GeoJSON
            features = []
            for event in events:
                if not event.get("latitude") or not event.get("longitude"):
                    continue
                
                try:
                    feature = {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [float(event["longitude"]), float(event["latitude"])]
                        },
                        'properties': {
                            'id': event["event_id_cnty"],
                            'event_type': event["event_type"],
                            'country': event["country"],
                            'location': event["location"],
                            'description': event["notes"][:200] if event["notes"] else event["event_type"],
                            'event_date': event["event_date"],
                            'fatalities': int(event["fatalities"] or 0),
                            'notes': event["notes"] if event["notes"] else "",
                            'affected_region': self._classify_region(event)
                        }
                    }
                    features.append(feature)
                except (ValueError, KeyError) as parse_error:
                    logger.warning(f"Skipping malformed event: {parse_error}")
                    continue
            
            logger.info(f"Fetched {len(features)} valid ACLED events")
            
            return {
                'type': 'FeatureCollection',
                'count': len(features),
                'features': features,
                'source': 'ACLED API (Live)',
                'status': 'live'
            }
            
        except requests.Timeout:
            logger.error("ACLED API timeout")
            return self._error_response("API timeout after 15s")
        except requests.HTTPError as http_err:
            logger.error(f"ACLED HTTP error: {http_err}")
            if http_err.response.status_code == 401:
                return self._error_response("Invalid ACLED API credentials")
            return self._error_response(f"HTTP {http_err.response.status_code}")
        except Exception as e:
            logger.error(f"ACLED error: {str(e)}")
            return self._error_response(str(e))
    
    def _classify_region(self, event: dict) -> str:
        """Classify event into ASX-relevant regions."""
        country = event.get("country", "").lower()
        
        if "china" in country:
            return "china_trade"
        elif "iran" in country or "yemen" in country:
            return "middle_east"
        elif "congo" in country:
            return "drc_lithium"
        elif "taiwan" in country:
            return "taiwan_rare_earth"
        elif "sudan" in country:
            return "red_sea_shipping"
        elif "australia" in country:
            return "australia_domestic"
        elif "united states" in country:
            return "us_trade_policy"
        elif "singapore" in country:
            return "asean_trade"
        else:
            return "other"
    
    def _error_response(self, error_msg: str) -> Dict:
        """Return error response in GeoJSON format."""
        return {
            'type': 'FeatureCollection',
            'count': 0,
            'features': [],
            'error': error_msg,
            'status': 'error',
            'message': 'ACLED data unavailable - check API credentials'
        }
