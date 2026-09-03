"""One ephemeral ticker subscription per viewer; never writes bars or runs scans."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import math
import time
from typing import Any, Awaitable, Callable

from websockets.asyncio.client import connect

from .yahoo_stream import YAHOO_STREAM_URL, decode_yahoo_stream_message

LEASE_SECONDS = 75
HEARTBEAT_SECONDS = 15
RECONNECT_DELAYS = (3, 15, 60)


def normalize_live_quote(message: dict, symbol: str, now: float) -> dict | None:
    """Validate Yahoo's untrusted payload once. Absent volume is not zero."""
    if message.get("id") != symbol:
        return None

    def number(key: str) -> float | None:
        raw = message.get(key)
        if isinstance(raw, bool) or raw is None:
            return None
        try:
            value = float(raw)
            return value if math.isfinite(value) else None
        except (ValueError, TypeError, OverflowError):
            return None

    price, timestamp = number("price"), number("time")
    if price is None or price <= 0 or timestamp is None:
        return None
    timestamp = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    if timestamp <= 0 or timestamp > now + 60:
        return None
    volume = number("day_volume")
    return {
        "symbol": symbol,
        "price": price,
        "quoteTime": timestamp,
        "receivedAt": now,
        "dayVolume": int(volume) if volume is not None and 0 <= volume <= 2**53 - 1 else None,
        "changePct": number("change_percent"),
        "currency": message.get("currency") if isinstance(message.get("currency"), str) else None,
        "marketHours": {0: "pre-market", 1: "regular", 2: "post-market", 3: "extended"}.get(message.get("market_hours"), "unknown"),
    }


class LiveQuoteSubscription:
    """Browser-owned resource with cancellation, bounded reconnects and a dead-tab lease.

    Own the transport instead of AsyncWebSocket.listen(): its reconnect loop can
    retain a closed socket. The protocol/decoder are shared with the yfinance probe.
    """

    def __init__(self, emit: Callable[[dict], Awaitable[None]], *, connector=connect):
        self._emit = emit
        self._connector = connector
        self._task: asyncio.Task | None = None
        self._subscription_id: str | None = None
        self._symbol: str | None = None
        self._expires = 0.0

    async def subscribe(self, symbol: str, subscription_id: str) -> None:
        if self._subscription_id == subscription_id and self._symbol == symbol:
            self._expires = time.monotonic() + LEASE_SECONDS
            return
        await self.close()
        self._symbol, self._subscription_id = symbol, subscription_id
        self._expires = time.monotonic() + LEASE_SECONDS
        self._task = asyncio.create_task(self._run(symbol, subscription_id))

    async def unsubscribe(self, subscription_id: str) -> None:
        # A late cleanup for A must not close the newly opened B.
        if self._subscription_id == subscription_id:
            await self.close()

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._subscription_id = self._symbol = None

    async def _run(self, symbol: str, subscription_id: str) -> None:
        async def emit(status: str, quote: dict | None = None) -> None:
            await self._emit({"subscriptionId": subscription_id, "symbol": symbol, "status": status, "quote": quote})

        try:
            last_time = 0.0
            for attempt in range(len(RECONNECT_DELAYS) + 1):
                if time.monotonic() >= self._expires:
                    await emit("paused")
                    return
                await emit("connecting" if attempt == 0 else "reconnecting")
                try:
                    async with self._connector(YAHOO_STREAM_URL, open_timeout=10, close_timeout=2, ping_interval=20, ping_timeout=20) as socket:
                        await socket.send(json.dumps({"subscribe": [symbol]}))
                        await emit("waiting")
                        next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS
                        while time.monotonic() < self._expires:
                            timeout = min(next_heartbeat, self._expires) - time.monotonic()
                            try:
                                raw = await asyncio.wait_for(socket.recv(), timeout=max(0.001, timeout))
                            except TimeoutError:
                                raw = None
                            if raw is not None:
                                try:
                                    quote = normalize_live_quote(decode_yahoo_stream_message(raw), symbol, time.time())
                                except (ValueError, TypeError, KeyError):
                                    quote = None
                                if quote and quote["quoteTime"] >= last_time:
                                    last_time = quote["quoteTime"]
                                    await emit("streaming", quote)
                            if time.monotonic() >= next_heartbeat:
                                await socket.send(json.dumps({"subscribe": [symbol]}))
                                next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS
                        await emit("paused")
                        return
                except Exception:
                    if attempt == len(RECONNECT_DELAYS):
                        await emit("unavailable")
                        return
                    await emit("reconnecting")
                    await asyncio.sleep(min(RECONNECT_DELAYS[attempt], max(0, self._expires - time.monotonic())))
        except Exception:
            # A disconnected downstream ends the resource, never an orphan task.
            return
