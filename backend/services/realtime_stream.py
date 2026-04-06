"""
Real-time Streaming Service
---------------------------
WebSocket-based streaming for live prices and signal broadcasts.
Manages per-ticker subscriptions and heartbeats.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Price poll interval in seconds
_PRICE_POLL_INTERVAL = 15


class StreamManager:
    """
    Manages active WebSocket connections and broadcasts real-time data.

    Clients subscribe to one or more tickers; the manager polls prices
    and pushes updates whenever a price changes by > 0.01%.
    """

    def __init__(self) -> None:
        # ticker → set of connected websockets
        self._subscriptions: dict[str, set[WebSocket]] = {}
        # websocket → set of subscribed tickers
        self._clients: dict[WebSocket, set[str]] = {}
        # ticker → last known price (for change detection)
        self._last_prices: dict[str, float] = {}
        self._price_poll_task: Optional[asyncio.Task] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, tickers: list[str]) -> None:
        """Accept a new WebSocket connection and subscribe it to the given tickers."""
        await websocket.accept()
        self._clients[websocket] = set()

        for ticker in tickers:
            ticker = ticker.upper().strip()
            if ticker not in self._subscriptions:
                self._subscriptions[ticker] = set()
            self._subscriptions[ticker].add(websocket)
            self._clients[websocket].add(ticker)

        logger.info("WebSocket connected — tickers: %s (total clients: %d)", tickers, len(self._clients))

        # Confirm subscription
        await self._send(websocket, {
            "type": "subscribed",
            "tickers": list(self._clients[websocket]),
            "timestamp": _now(),
        })

        # Start price polling if not already running
        if self._price_poll_task is None or self._price_poll_task.done():
            self._price_poll_task = asyncio.create_task(self._price_poll_loop())

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection and clean up subscriptions."""
        tickers = self._clients.pop(websocket, set())
        for ticker in tickers:
            self._subscriptions.get(ticker, set()).discard(websocket)
            if not self._subscriptions.get(ticker):
                self._subscriptions.pop(ticker, None)
        logger.info("WebSocket disconnected (remaining clients: %d)", len(self._clients))

    async def broadcast_signal(self, ticker: str, signal: dict[str, Any]) -> None:
        """Push a new prediction signal to all clients subscribed to the ticker."""
        subscribers = self._subscriptions.get(ticker.upper(), set())
        if not subscribers:
            return
        message = {"type": "signal", "ticker": ticker, "payload": signal, "timestamp": _now()}
        await self._broadcast_to(subscribers, message)

    # ── Internal price polling ─────────────────────────────────────────────────

    async def _price_poll_loop(self) -> None:
        """Background task: poll prices for all subscribed tickers."""
        while self._clients:
            try:
                tickers = list(self._subscriptions.keys())
                if tickers:
                    await self._fetch_and_broadcast_prices(tickers)
            except Exception as e:
                logger.error("Price poll error: %s", e)
            await asyncio.sleep(_PRICE_POLL_INTERVAL)

    async def _fetch_and_broadcast_prices(self, tickers: list[str]) -> None:
        """Fetch current prices and broadcast updates for tickers that changed."""
        loop = asyncio.get_event_loop()

        def _fetch_all(tickers: list[str]) -> dict[str, float]:
            import yfinance as yf
            prices: dict[str, float] = {}
            for ticker in tickers:
                try:
                    info = yf.Ticker(ticker).fast_info
                    price = getattr(info, "last_price", None)
                    if price:
                        prices[ticker] = price
                except Exception as e:
                    logger.debug("Price fetch skipped for %s: %s", ticker, e)
            return prices

        try:
            prices = await loop.run_in_executor(None, _fetch_all, tickers)
        except Exception as e:
            logger.warning("Batch price fetch failed: %s", e)
            return

        for ticker, price in prices.items():
            last = self._last_prices.get(ticker)
            if last is None or abs(price - last) / last > 0.0001:  # > 0.01% change
                self._last_prices[ticker] = price
                await self._broadcast_price(ticker, price, last)

    async def _broadcast_price(
        self, ticker: str, price: float, previous: Optional[float]
    ) -> None:
        subscribers = self._subscriptions.get(ticker, set())
        if not subscribers:
            return
        change_pct = ((price - previous) / previous * 100) if previous else 0.0
        message = {
            "type": "price",
            "ticker": ticker,
            "price": round(price, 4),
            "previous": round(previous, 4) if previous else None,
            "change_pct": round(change_pct, 4),
            "timestamp": _now(),
        }
        await self._broadcast_to(set(subscribers), message)

    async def _broadcast_to(self, sockets: set[WebSocket], message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    @staticmethod
    async def _send(websocket: WebSocket, message: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.warning("Failed to send message: %s", e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Module-level singleton — imported by the route and by broadcast_signal callers
stream_manager = StreamManager()
