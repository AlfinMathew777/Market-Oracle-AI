"""AISStream WebSocket integration for real-time vessel tracking at Port Hedland.

Monitors bulk carrier congestion at Australia's largest iron ore export port
as a leading indicator for BHP, RIO, FMG export volumes.

API key required: Free instant key at aisstream.io
"""

import asyncio
import websockets
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

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
    "connected": False,
    "status": "not_started"
}


async def _stream_port_hedland():
    """Background WebSocket connection to AISStream for Port Hedland monitoring."""
    
    api_key = os.getenv("AISSTREAM_API_KEY")
    
    if not api_key:
        logger.warning("AISSTREAM_API_KEY not configured - vessel tracking disabled")
        _vessel_cache["status"] = "pending_api_key"
        _vessel_cache["connected"] = False
        return
    
    uri = "wss://stream.aisstream.io/v0/stream"
    
    subscribe_message = {
        "APIKey": api_key,
        "BoundingBoxes": [[
            [PORT_HEDLAND_BBOX["min_lat"], PORT_HEDLAND_BBOX["min_lon"]],  # [lat, lon] — AISStream standard
            [PORT_HEDLAND_BBOX["max_lat"], PORT_HEDLAND_BBOX["max_lon"]]
        ]],
        "FilterMessageTypes": ["PositionReport"]
    }
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            logger.info(f"Connecting to AISStream WebSocket (attempt {retry_count + 1}/{max_retries})...")
            
            async with websockets.connect(uri, ping_interval=30, ping_timeout=10) as websocket:
                # Send subscription
                await websocket.send(json.dumps(subscribe_message))
                logger.info("? AISStream connected - monitoring Port Hedland vessels")
                
                _vessel_cache["status"] = "connected"
                _vessel_cache["connected"] = True
                retry_count = 0  # Reset on successful connection
                
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
                                _update_cache(vessels_seen)
                    
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from AISStream")
                        continue
                    except KeyError as ke:
                        logger.warning(f"Unexpected AISStream message format: {ke}")
                        continue
                        
        except websockets.exceptions.WebSocketException as ws_err:
            logger.error(f"AISStream WebSocket error: {ws_err}")
            _vessel_cache["status"] = "error"
            _vessel_cache["connected"] = False
            retry_count += 1
            await asyncio.sleep(min(2 ** retry_count, 30))  # Exponential backoff
            
        except Exception as e:
            logger.error(f"AISStream connection error: {str(e)}")
            _vessel_cache["status"] = "error"
            _vessel_cache["connected"] = False
            _vessel_cache["error"] = str(e)
            retry_count += 1
            await asyncio.sleep(min(2 ** retry_count, 30))  # Exponential backoff
    
    # Max retries exhausted
    logger.error("AISStream connection failed after max retries")
    _vessel_cache["status"] = "failed"
    _vessel_cache["connected"] = False


def _update_cache(vessels_seen: dict):
    """Update global cache with latest vessel data."""
    # Bulk carriers are ship types 70-79
    bulk_carriers = [
        v for v in vessels_seen.values()
        if 70 <= v.get("ship_type", 0) <= 79
    ]
    
    count = len(bulk_carriers)
    
    # Determine congestion level based on bulk carrier count
    if count > 15:
        congestion = "HIGH"
    elif count > 8:
        congestion = "MEDIUM"
    elif count > 0:
        congestion = "LOW"
    else:
        congestion = "EMPTY"
    
    _vessel_cache.update({
        "vessels": list(vessels_seen.values()),
        "bulk_carrier_count": count,
        "vessel_count": len(vessels_seen),
        "congestion_level": congestion,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "connected": True,
        "status": "live"
    })
    
    logger.info(f"Port Hedland update: {count} bulk carriers, {len(vessels_seen)} total vessels, congestion: {congestion}")


def start_ais_background_stream():
    """Start WebSocket stream in background thread on app startup.
    
    Gracefully handles missing API key by logging warning and returning early.
    """
    import threading
    
    api_key = os.getenv("AISSTREAM_API_KEY")
    
    if not api_key:
        logger.warning("?  AISSTREAM_API_KEY not configured - vessel tracking disabled. Get free key at aisstream.io")
        _vessel_cache["status"] = "pending_api_key"
        _vessel_cache["connected"] = False
        return  # Early return - app starts without crashing
    
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_stream_port_hedland())
        except Exception as e:
            logger.error(f"AIS background stream crashed: {str(e)}")
            _vessel_cache["status"] = "crashed"
            _vessel_cache["connected"] = False
    
    thread = threading.Thread(target=run, daemon=True, name="AISStream-Background")
    thread.start()
    logger.info("? AISStream background thread started")


def get_port_hedland_status() -> Dict:
    """Return current cached Port Hedland vessel data.
    
    Returns graceful pending state if API key is missing.
    """
    
    if not os.getenv("AISSTREAM_API_KEY"):
        return {
            "vessel_count": 0,
            "bulk_carrier_count": 0,
            "congestion_level": "UNKNOWN",
            "status": "pending_api_key",
            "connected": False,
            "message": "AISStream API key not configured. Get free instant key at aisstream.io",
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
