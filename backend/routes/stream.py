"""
Real-time Streaming WebSocket Route
-------------------------------------
Clients connect and subscribe to one or more ASX tickers.
Receive live price updates and prediction signal broadcasts.
"""

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from services.realtime_stream import stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])


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
