"""AIS vessel tracking service for Port Hedland.

USE_MOCK_DATA flag controls whether to use mock data or real AISStream API.
"""

import os
from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# TOGGLE THIS FLAG: True = mock data, False = real AISStream API
USE_MOCK_DATA = True

# Port Hedland bounding box (lat -20.31 ±1.0, lon 118.58 ±1.5)
PORT_HEDLAND_BBOX = {
    'lat_min': -21.31,
    'lat_max': -19.31,
    'lon_min': 117.08,
    'lon_max': 120.08
}

# Mock data: realistic Port Hedland congestion during peak export season
MOCK_PORT_HEDLAND_DATA = {
    "vessel_count": 14,
    "bulk_carrier_count": 11,
    "congestion_level": "HIGH",
    "vessels": ["IMO9674562", "IMO9445618", "IMO9312847"],
    "avg_wait_time_hours": 38,
    "data_source": "mock",
    "bbox": PORT_HEDLAND_BBOX
}


class AISService:
    """Service for fetching AIS vessel tracking data for Port Hedland."""
    
    def __init__(self):
        self.use_mock = USE_MOCK_DATA
        self.ais_api_key = os.getenv('AISSTREAM_API_KEY')
        
        if not self.use_mock and not self.ais_api_key:
            logger.warning("AISStream API key not found, falling back to mock data")
            self.use_mock = True
    
    def get_port_hedland_status(self) -> Dict[str, Any]:
        """Get current Port Hedland vessel status and congestion.
        
        Returns:
            Dict with vessel count, congestion level, and metadata
        """
        if self.use_mock:
            logger.info("Returning mock Port Hedland AIS data")
            data = MOCK_PORT_HEDLAND_DATA.copy()
            data['updated_at'] = datetime.now().isoformat()
            return data
        else:
            return self._fetch_real_ais_data()
    
    def _fetch_real_ais_data(self) -> Dict[str, Any]:
        """Fetch real AIS data from AISStream API.
        
        This will be implemented when USE_MOCK_DATA = False.
        """
        import requests
        
        try:
            # AISStream WebSocket API would be used in production
            # For REST fallback, we would query their API with bbox
            
            # Example AISStream REST endpoint (adjust based on actual API)
            url = "https://stream.aisstream.io/v0/stream"
            headers = {
                'Authorization': f'Bearer {self.ais_api_key}'
            }
            
            bbox = PORT_HEDLAND_BBOX
            params = {
                'bbox': f"{bbox['lon_min']},{bbox['lat_min']},{bbox['lon_max']},{bbox['lat_max']}"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            vessels = response.json()
            
            # Process vessel data
            vessel_count = len(vessels)
            bulk_carrier_count = sum(1 for v in vessels if v.get('ship_type', '').lower() in ['cargo', 'tanker', 'bulk'])
            
            # Determine congestion level
            if vessel_count >= 12:
                congestion = "HIGH"
            elif vessel_count >= 7:
                congestion = "MEDIUM"
            else:
                congestion = "LOW"
            
            return {
                'vessel_count': vessel_count,
                'bulk_carrier_count': bulk_carrier_count,
                'congestion_level': congestion,
                'vessels': [v.get('mmsi') or v.get('imo') for v in vessels[:10]],
                'avg_wait_time_hours': self._estimate_wait_time(congestion),
                'data_source': 'aisstream',
                'bbox': bbox,
                'updated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching real AIS data: {str(e)}")
            logger.warning("Falling back to mock data")
            data = MOCK_PORT_HEDLAND_DATA.copy()
            data['updated_at'] = datetime.now().isoformat()
            return data
    
    def _estimate_wait_time(self, congestion: str) -> int:
        """Estimate wait time based on congestion level."""
        if congestion == "HIGH":
            return 36
        elif congestion == "MEDIUM":
            return 18
        else:
            return 6
