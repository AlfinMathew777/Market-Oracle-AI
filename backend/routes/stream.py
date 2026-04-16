"""
Real-time Streaming WebSocket Route
-------------------------------------
Clients connect and subscribe to one or more ASX tickers.
Receive live price updates and prediction signal broadcasts.
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from services.realtime_stream import stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])

# WebSocket connection rate limiter — max 5 connections per IP per 60 seconds
_ws_connections: dict = defaultdict(list)
_WS_MAX_PER_IP = 5
_WS_WINDOW_SECS = 60


def _ws_rate_check(client_ip: str) -> bool:
    """Return True if the connection is allowed, False if rate limit exceeded."""
    now = time.time()
    _ws_connections[client_ip] = [
        ts for ts in _ws_connections[client_ip]
        if now - ts < _WS_WINDOW_SECS
    ]
    if len(_ws_connections[client_ip]) >= _WS_MAX_PER_IP:
        return False
    _ws_connections[client_ip].append(now)
    return True


@router.websocket("/prices")
async def price_stream(
    websocket: WebSocket,
    tickers: str = Query(..., description="Comma-separated ASX tickers, e.g. BHP.AX,RIO.AX"),
):
    """
    WebSocket endpoint for real-time price streaming.

    Connect with: ws://<host>/api/stream/prices?tickers=BHP.AX,RIO.AX

    Messages sent to client:
    - {"type": "subscribed", "tickers": [...], "timestamp": "..."}
    - {"type": "price", "ticker": "BHP.AX", "price": 45.23, "previous": 45.10, "change_pct": 0.29, "timestamp": "..."}
    - {"type": "signal", "ticker": "BHP.AX", "payload": {...}, "timestamp": "..."}
    """
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not _ws_rate_check(client_ip):
        logger.warning("WebSocket rate limit exceeded for %s", client_ip)
        await websocket.close(code=1008, reason="Rate limit exceeded")
        return

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        await websocket.close(code=1008, reason="No tickers specified")
        return

    await stream_manager.connect(websocket, ticker_list)
    try:
        while True:
            # Keep connection alive; client can send ping messages
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        await stream_manager.disconnect(websocket)


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "realtime_stream",
        "active_clients": len(stream_manager._clients),
        "subscribed_tickers": list(stream_manager._subscriptions.keys()),
    }
