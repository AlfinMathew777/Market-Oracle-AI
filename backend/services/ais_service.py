"""AISStream API integration for real-time vessel tracking at Port Hedland.

WebSocket connection to AISStream for live AIS (Automatic Identification System)
vessel position data. Monitors Port Hedland shipping congestion as a leading
indicator for BHP, RIO, FMG iron ore export volumes.

API key required: Free instant key at aisstream.io
"""

import asyncio
import websockets
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)

# REAL DATA - no mock fallback
USE_MOCK_DATA = False

# AISStream API configuration
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY")

# Port Hedland bounding box (world's largest iron ore export port)
PORT_HEDLAND_BBOX = {
    "min_lat": -21.0,
    "max_lat": -19.5,
    "min_lon": 117.5,
    "max_lon": 119.5
}

# Global vessel cache - updated by background WebSocket stream
_vessel_cache = {
    "vessels": [],
    "bulk_carrier_count": 0,
    "vessel_count": 0,
    "congestion_level": "UNKNOWN",
    "updated_at": None,
    "status": "not_started"
}


async def _stream_port_hedland():
    """Background WebSocket connection to AISStream for Port Hedland monitoring."""
    
    if not AISSTREAM_API_KEY:
        logger.error("AISSTREAM_API_KEY not configured - cannot start vessel monitoring")
        _vessel_cache["status"] = "pending_api_key"
        return
    
    uri = "wss://stream.aisstream.io/v0/stream"
    
    subscribe_message = {
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": [[
            [PORT_HEDLAND_BBOX["min_lon"], PORT_HEDLAND_BBOX["min_lat"]],
            [PORT_HEDLAND_BBOX["max_lon"], PORT_HEDLAND_BBOX["max_lat"]]
        ]],
        "FilterMessageTypes": ["PositionReport"]
    }
    
    try:
        logger.info("Connecting to AISStream WebSocket for Port Hedland monitoring...")
        
        async with websockets.connect(uri) as websocket:
            # Send subscription
            await websocket.send(json.dumps(subscribe_message))
            logger.info("✓ Connected to AISStream - monitoring Port Hedland vessels")
            
            _vessel_cache["status"] = "connected"
            vessels_seen = {}
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get("MessageType") == "PositionReport":
                        position = data["Message"]["PositionReport"]
                        metadata = data.get("MetaData", {})
                        
                        mmsi = str(position["UserID"])
                        ship_type = metadata.get("ShipType", 0)
                        
                        vessels_seen[mmsi] = {
                            "mmsi": mmsi,
                            "lat": position["Latitude"],
                            "lon": position["Longitude"],
                            "speed": position.get("Sog", 0),
                            "course": position.get("Cog", 0),
                            "ship_type": ship_type,
                            "ship_name": metadata.get("ShipName", "Unknown"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        
                        # Update cache every 30 messages (reduce CPU load)
                        if len(vessels_seen) % 30 == 0:
                            # Bulk carriers are ship types 70-79
                            bulk_carriers = [
                                v for v in vessels_seen.values()
                                if 70 <= v.get("ship_type", 0) <= 79
                            ]
                            
                            count = len(bulk_carriers)
                            
                            _vessel_cache.update({
                                "vessels": list(vessels_seen.values()),
                                "bulk_carrier_count": count,
                                "vessel_count": len(vessels_seen),
                                "congestion_level": "HIGH" if count > 10 else "MEDIUM" if count > 5 else "LOW",
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                                "status": "live"
                            })
                            
                            logger.info(f"Port Hedland update: {count} bulk carriers, {len(vessels_seen)} total vessels")
                
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from AISStream")
                    continue
                except KeyError as ke:
                    logger.warning(f"Unexpected message format: {ke}")
                    continue
                    
    except Exception as e:
        logger.error(f"AISStream connection error: {str(e)}")
        _vessel_cache["status"] = "error"
        _vessel_cache["error"] = str(e)


def start_ais_background_stream():
    """Start WebSocket stream in background thread on app startup."""
    import threading
    
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_stream_port_hedland())
        except Exception as e:
            logger.error(f"AIS background stream crashed: {str(e)}")
            _vessel_cache["status"] = "crashed"
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("AISStream background thread started")


def get_port_hedland_status() -> Dict:
    """Return current cached Port Hedland vessel data."""
    
    if not AISSTREAM_API_KEY:
        return {
            "vessel_count": 0,
            "bulk_carrier_count": 0,
            "congestion_level": "UNKNOWN",
            "status": "pending_api_key",
            "message": "AISStream API key not configured. Get free key at aisstream.io (2 minutes)",
            "updated_at": None
        }
    
    if _vessel_cache["status"] == "not_started":
        return {
            **_vessel_cache,
            "message": "AISStream connection initializing..."
        }
    
    return _vessel_cache


class AISService:
    """Legacy class wrapper for compatibility."""
    
    def get_port_hedland_status(self) -> Dict:
        return get_port_hedland_status()
