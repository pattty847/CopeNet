import asyncio
import base64
from contextlib import asynccontextmanager
import json
import time

import pytest
from yfinance.pricing_pb2 import PricingData

from copenet.core.market.live_quote import LiveQuoteSubscription, normalize_live_quote
from copenet.core.market import live_quote
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import RequestFrame


def encoded(symbol="TEST", price=101.5, timestamp=None, **extra):
    message = PricingData(id=symbol, price=price, time=timestamp or int(time.time() * 1000), **extra)
    return json.dumps({"message": base64.b64encode(message.SerializeToString()).decode()})


class Feed:
    def __init__(self):
        self.opened = 0
        self.active = 0
        self.maximum = 0
        self.subscriptions = []
        self.messages = asyncio.Queue()

    @asynccontextmanager
    async def connect(self, *args, **kwargs):
        self.opened += 1
        self.active += 1
        self.maximum = max(self.active, self.maximum)
        try:
            yield self
        finally:
            self.active -= 1

    async def send(self, message):
        self.subscriptions.append(json.loads(message))

    async def recv(self):
        value = await self.messages.get()
        if isinstance(value, Exception):
            raise value
        return value


async def eventually(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0.001)


def test_quote_boundary_rejects_invalid_data_and_preserves_missing_volume():
    raw = {"id": "TEST", "price": 12, "time": "1788442200000"}
    quote = normalize_live_quote(raw, "TEST", 1788442201)
    assert quote["quoteTime"] == 1788442200
    assert quote["dayVolume"] is None
    for patch in ({"id": "OTHER"}, {"price": float("nan")}, {"price": -1}, {"time": "bad"}, {"time": "999999999999999"}):
        assert normalize_live_quote({**raw, **patch}, "TEST", 1788442201) is None
    assert normalize_live_quote({**raw, "day_volume": "0"}, "TEST", 1788442201)["dayVolume"] == 0
    assert normalize_live_quote({**raw, "day_volume": "1200"}, "TEST", 1788442201)["dayVolume"] == 1200


@pytest.mark.asyncio
async def test_switch_and_late_cleanup_never_open_two_sockets():
    feed, events = Feed(), []
    async def emit(event):
        events.append(event)
    subscription = LiveQuoteSubscription(emit, connector=feed.connect)
    await subscription.subscribe("TEST", "first")
    await eventually(lambda: feed.active == 1)
    await subscription.subscribe("TEST", "first")
    assert feed.opened == 1  # lease renewal, not another connection
    await subscription.subscribe("DEMO", "second")
    await eventually(lambda: feed.opened == 2)
    await subscription.unsubscribe("first")
    assert feed.active == feed.maximum == 1
    assert feed.subscriptions == [{"subscribe": ["TEST"]}, {"subscribe": ["DEMO"]}]
    await subscription.close()
    assert feed.active == 0


@pytest.mark.asyncio
async def test_stream_drops_other_symbols_and_old_ticks_without_accumulating_volume():
    feed, events = Feed(), []
    async def emit(event):
        events.append(event)
    subscription = LiveQuoteSubscription(emit, connector=feed.connect)
    await subscription.subscribe("TEST", "first")
    now = int(time.time() * 1000)
    for message in (encoded(timestamp=now, day_volume=100), encoded("OTHER", timestamp=now),
                    encoded(timestamp=now - 1000, day_volume=99), encoded(timestamp=now, day_volume=101)):
        await feed.messages.put(message)
    await eventually(lambda: len([e for e in events if e["quote"]]) == 2)
    quotes = [e["quote"] for e in events if e["quote"]]
    assert [q["dayVolume"] for q in quotes] == [100, 101]
    await subscription.close()


@pytest.mark.asyncio
async def test_dead_view_lease_expires_without_reconnect(monkeypatch):
    monkeypatch.setattr(live_quote, "LEASE_SECONDS", 0.02)
    feed, events = Feed(), []
    async def emit(event):
        events.append(event)
    subscription = LiveQuoteSubscription(emit, connector=feed.connect)
    await subscription.subscribe("TEST", "first")
    await eventually(lambda: any(e["status"] == "paused" for e in events))
    await eventually(lambda: feed.active == 0)
    assert feed.opened == 1
    await subscription.close()


@pytest.mark.asyncio
async def test_reconnect_is_bounded_and_unsubscribe_cancels_backoff(monkeypatch):
    monkeypatch.setattr(live_quote, "RECONNECT_DELAYS", (0.001,))
    feed, events = Feed(), []
    async def emit(event):
        events.append(event)
    subscription = LiveQuoteSubscription(emit, connector=feed.connect)
    await feed.messages.put(OSError("closed"))
    await feed.messages.put(OSError("closed again"))
    await subscription.subscribe("TEST", "first")
    await eventually(lambda: any(e["status"] == "unavailable" for e in events))
    assert feed.opened == 2 and feed.active == 0
    await subscription.close()
    monkeypatch.setattr(live_quote, "RECONNECT_DELAYS", (10,))
    await feed.messages.put(OSError("closed"))
    await subscription.subscribe("TEST", "next")
    await eventually(lambda: feed.opened == 3 and feed.active == 0)
    await asyncio.wait_for(subscription.close(), 0.1)
    assert feed.opened == 3


@pytest.mark.asyncio
async def test_rpc_validates_one_symbol_and_scopes_cleanup():
    feed, frames = Feed(), []
    async def send(frame):
        frames.append(frame)
    subscription = LiveQuoteSubscription(send, connector=feed.connect)
    async def request(method, params):
        await dispatch_rpc(RequestFrame("id", method, params), send, None, set(), quote_subscription=subscription)
    await request("market.quote.subscribe", {"symbol": ["TEST", "DEMO"], "subscriptionId": "id"})
    assert frames[-1]["error"]["code"] == "INVALID_REQUEST"
    assert feed.opened == 0
    await request("market.quote.subscribe", {"symbol": "TEST", "subscriptionId": "id"})
    assert frames[-1]["ok"]
    await eventually(lambda: feed.opened == 1)
    await request("market.quote.unsubscribe", {"subscriptionId": "id"})
    assert feed.active == 0


@pytest.mark.asyncio
async def test_browser_disconnect_closes_only_its_own_upstream(monkeypatch):
    from fastapi import WebSocketDisconnect
    from copenet.host import ws_server

    feed = Feed()
    monkeypatch.setenv("COPNET_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(ws_server, "LiveQuoteSubscription", lambda emit: LiveQuoteSubscription(emit, connector=feed.connect))

    class Browser:
        def __init__(self, token):
            self.frames = []
            self.requests = iter([
                {"type": "req", "id": "auth", "method": "connect", "params": {"auth": {"token": token}}},
                {"type": "req", "id": "sub", "method": "market.quote.subscribe", "params": {"symbol": "TEST", "subscriptionId": "view"}},
            ])

        async def accept(self):
            pass

        async def send_json(self, payload):
            self.frames.append(payload)

        async def close(self, **kwargs):
            pass

        async def receive_json(self):
            try:
                return next(self.requests)
            except StopIteration:
                await eventually(lambda: feed.active == 1)
                raise WebSocketDisconnect()

    server = ws_server.CopeNetWsServer(orchestrator=object())
    rejected = Browser("incorrect")
    await server.handle(rejected)
    assert feed.opened == 0
    browser = Browser("synthetic-test-token")
    await server.handle(browser)
    assert feed.opened == 1 and feed.active == 0
    assert not server._connections
