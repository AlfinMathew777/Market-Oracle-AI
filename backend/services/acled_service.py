"""ACLED conflict events data service.

USE_MOCK_DATA flag controls whether to use mock data or real ACLED API.
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# TOGGLE THIS FLAG: True = mock data, False = real ACLED API
USE_MOCK_DATA = True

# Mock dataset: 8 real-world conflict events relevant to ASX tickers
MOCK_ACLED_EVENTS = [
    {
        "id": "acled_001",
        "lat": 26.9,
        "lon": 56.2,
        "event_type": "Armed Conflict",
        "country": "Iran",
        "description": "Strait of Hormuz naval tensions",
        "date": "2026-03-10",
        "fatalities": 0,
        "affected_region": "middle_east",
        "notes": "Naval standoff near Hormuz, oil tanker inspection incidents"
    },
    {
        "id": "acled_002",
        "lat": -8.8,
        "lon": 25.5,
        "event_type": "Armed Conflict",
        "country": "DRC",
        "description": "Eastern DRC conflict near Manono lithium deposit",
        "date": "2026-03-12",
        "fatalities": 14,
        "affected_region": "drc_lithium",
        "notes": "Armed groups clash near lithium mining operations"
    },
    {
        "id": "acled_003",
        "lat": 23.1,
        "lon": 113.3,
        "event_type": "Political Crisis",
        "country": "China",
        "description": "Trade policy tensions, iron ore import restrictions",
        "date": "2026-03-11",
        "fatalities": 0,
        "affected_region": "china_trade",
        "notes": "China announces new iron ore import quotas affecting Australian exporters"
    },
    {
        "id": "acled_004",
        "lat": 25.2,
        "lon": 51.5,
        "event_type": "Armed Conflict",
        "country": "Qatar/Gulf",
        "description": "Gulf shipping disruption, LNG tanker rerouting",
        "date": "2026-03-09",
        "fatalities": 0,
        "affected_region": "gulf_lng",
        "notes": "LNG tankers rerouting due to regional tensions"
    },
    {
        "id": "acled_005",
        "lat": -34.6,
        "lon": -58.4,
        "event_type": "Political Crisis",
        "country": "Argentina",
        "description": "Lithium export restrictions, mining nationalisation",
        "date": "2026-03-13",
        "fatalities": 0,
        "affected_region": "latam_lithium",
        "notes": "New government announces lithium sector nationalisation plans"
    },
    {
        "id": "acled_006",
        "lat": 25.0,
        "lon": 121.5,
        "event_type": "Military Activity",
        "country": "Taiwan Strait",
        "description": "Taiwan Strait military exercises, semiconductor supply chain risk",
        "date": "2026-03-14",
        "fatalities": 0,
        "affected_region": "taiwan_rare_earth",
        "notes": "Large-scale military exercises impacting regional rare earth logistics"
    },
    {
        "id": "acled_007",
        "lat": -20.3,
        "lon": 118.6,
        "event_type": "Industrial Action",
        "country": "Australia",
        "description": "Port Hedland workers strike, iron ore shipment delays",
        "date": "2026-03-12",
        "fatalities": 0,
        "affected_region": "pilbara_resources",
        "notes": "Port workers strike causing 48-hour iron ore shipment delays"
    },
    {
        "id": "acled_008",
        "lat": 15.5,
        "lon": 32.5,
        "event_type": "Armed Conflict",
        "country": "Sudan",
        "description": "Red Sea corridor disruption, shipping rerouting via Cape",
        "date": "2026-03-11",
        "fatalities": 8,
        "affected_region": "red_sea_shipping",
        "notes": "Conflict near Port Sudan forcing ships to reroute around Cape of Good Hope"
    }
]


class ACLEDService:
    """Service for fetching ACLED conflict event data."""
    
    def __init__(self):
        self.use_mock = USE_MOCK_DATA
        self.acled_username = os.getenv('ACLED_USERNAME')
        self.acled_password = os.getenv('ACLED_PASSWORD')
        
        if not self.use_mock and (not self.acled_username or not self.acled_password):
            logger.warning("ACLED credentials not found, falling back to mock data")
            self.use_mock = True
    
    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent conflict events.
        
        Args:
            limit: Maximum number of events to return
        
        Returns:
            List of event dictionaries
        """
        if self.use_mock:
            logger.info(f"Returning {len(MOCK_ACLED_EVENTS)} mock ACLED events")
            return MOCK_ACLED_EVENTS[:limit]
        else:
            return self._fetch_real_acled_events(limit)
    
    def _fetch_real_acled_events(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch events from real ACLED API.
        
        This will be implemented when USE_MOCK_DATA = False.
        """
        import requests
        from datetime import datetime, timedelta
        
        # ACLED API endpoint
        base_url = "https://api.acleddata.com/acled/read"
        
        # OAuth authentication (from integration playbook)
        auth_url = "https://acleddata.com/oauth/token"
        auth_data = {
            'username': self.acled_username,
            'password': self.acled_password,
            'grant_type': 'password',
            'client_id': 'acled'
        }
        
        try:
            # Get OAuth token
            auth_response = requests.post(auth_url, data=auth_data, timeout=10)
            auth_response.raise_for_status()
            access_token = auth_response.json()['access_token']
            
            # Fetch recent events
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Get events from last 30 days
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            params = {
                'limit': limit,
                'event_date': f'{start_date}:2026-12-31',
                'event_date_where': 'BETWEEN'
            }
            
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            events = []
            
            for item in data.get('data', []):
                events.append({
                    'id': item.get('event_id_cnty'),
                    'lat': float(item.get('latitude', 0)),
                    'lon': float(item.get('longitude', 0)),
                    'event_type': item.get('event_type'),
                    'country': item.get('country'),
                    'description': item.get('location'),
                    'date': item.get('event_date'),
                    'fatalities': int(item.get('fatalities', 0)),
                    'notes': item.get('notes', '')
                })
            
            logger.info(f"Fetched {len(events)} real ACLED events")
            return events
            
        except Exception as e:
            logger.error(f"Error fetching real ACLED data: {str(e)}")
            logger.warning("Falling back to mock data")
            return MOCK_ACLED_EVENTS[:limit]
    
    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific event by ID."""
        events = self.get_recent_events()
        for event in events:
            if event['id'] == event_id:
                return event
        return None
    
    def to_geojson(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert events to GeoJSON format."""
        features = []
        
        for event in events:
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [event['lon'], event['lat']]
                },
                'properties': {
                    'id': event['id'],
                    'event_type': event['event_type'],
                    'country': event['country'],
                    'description': event['description'],
                    'date': event['date'],
                    'fatalities': event['fatalities'],
                    'notes': event.get('notes', ''),
                    'affected_region': event.get('affected_region', '')
                }
            }
            features.append(feature)
        
        return {
            'type': 'FeatureCollection',
            'features': features
        }
