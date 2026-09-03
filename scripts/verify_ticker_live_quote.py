"""Offline browser → real quote RPC/lifecycle → synthetic Yahoo-wire verification.

Build first, then uv run python scripts/verify_ticker_live_quote.py.
No credentials, provider requests, scans or operator data are used.
"""

import asyncio
import base64
from contextlib import asynccontextmanager
import json
import mimetypes
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from yfinance.pricing_pb2 import PricingData

from copenet.core.market.live_quote import LiveQuoteSubscription
from copenet.core.market.models import DashboardPayload
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_market_quote import MARKET_QUOTE_METHODS
from copenet.host.rpc_schema import RequestFrame

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "src/copenet/host/frontend/dist"


def detail(symbol):
    bars = [{"t": 1756684800 + i * 86400, "o": 99 + i / 10, "h": 103 + i / 10,
             "l": 98 + i / 10, "c": 100 + i / 10, "v": 1000} for i in range(60)]
    return {"symbol": symbol, "name": "Synthetic quote preview", "asOf": "Synthetic",
            "quote": {"price": 105.9, "changePct": 0.1, "comparison": "previous_daily_bar", "priceBasis": "split_adjusted"},
            "series": {"daily": bars, "weekly": bars, "monthly": bars}, "verdict": [], "signals": [],
            "evidence": [], "events": [], "kill": "", "intelligence": None}


async def verify(browser, width):
    context = await browser.new_context(viewport={"width": width, "height": 900})
    requests, errors, resources, feeds = [], [], [], []
    tasks = set()

    class Feed:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.symbol = None
            self.active = False

        async def tick(self, price=123.45, **extra):
            wire = PricingData(id=self.symbol, price=price, time=int(time.time() * 1000),
                               currency="USD", market_hours=1, **extra)
            await self.queue.put(json.dumps({"message": base64.b64encode(wire.SerializeToString()).decode()}))

        async def send(self, raw):
            if self.symbol is None:
                self.symbol = json.loads(raw)["subscribe"][0]
                await self.tick(day_volume=1200000)

        async def recv(self):
            return await self.queue.get()

    @asynccontextmanager
    async def connector(*args, **kwargs):
        feed = Feed()
        feed.active = True
        feeds.append(feed)
        assert sum(f.active for f in feeds) == 1, "Overlapping upstream subscriptions"
        try:
            yield feed
        finally:
            feed.active = False

    async def serve(route):
        path = urlparse(route.request.url)
        if path.hostname not in {"127.0.0.1", "copenet-preview.test"}:
            await route.abort()
            return
        target = DIST / path.path.lstrip("/")
        if not target.is_file():
            target = DIST / "index.html"
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or "application/octet-stream")

    def spawn(coroutine):
        task = asyncio.create_task(coroutine)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    def socket(ws):
        lock = asyncio.Lock()
        async def send(frame):
            ws.send(json.dumps(frame))
        async def emit(payload):
            await send({"type": "event", "event": "market.quote", "payload": payload})
        subscription = LiveQuoteSubscription(emit, connector=connector)
        resources.append(subscription)

        async def reply(raw):
            async with lock:
                request = json.loads(raw)
                method, params = request["method"], request.get("params", {})
                requests.append(method)
                if method in MARKET_QUOTE_METHODS:
                    await dispatch_rpc(RequestFrame(request["id"], method, params), send, None, set(), quote_subscription=subscription)
                    return
                responses = {
                    "connect": {}, "market.dashboard.get": DashboardPayload.empty(as_of="Synthetic").to_wire(),
                    "market.watchlist.get": {"items": [], "lists": ["Synthetic"], "active": "Synthetic"},
                    "market.ticker.get": detail(params.get("symbol", "TEST")),
                    "market.ticker.evidence.get": {"evidence": [], "events": [], "warnings": []},
                    "market.financial.metrics.list": {"metrics": []}, "market.alerts.state": {"alerts": [], "events": [], "evaluations": []},
                    "market.brief.get": {"brief": None}, "market.read.get": {"read": None, "sessions": []},
                }
                ok = method in responses
                await send({"type": "res", "id": request["id"], "ok": ok,
                            "payload" if ok else "error": responses[method] if ok else {"message": "Not used by this isolated preview"}})

        ws.on_message(lambda raw: spawn(reply(raw)))
        ws.send(json.dumps({"type": "event", "event": "connect.challenge", "payload": {}}))

    await context.route("**/*", serve)
    await context.route_web_socket("**/*", socket)
    page = await context.new_page()
    page.set_default_timeout(10000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        # Non-loopback HTTP exercises the insecure-origin constraints of tailnet HTTP.
        host = "copenet-preview.test" if width == 390 else "127.0.0.1"
        await page.goto(f"http://{host}:17124/market/TEST", wait_until="networkidle")
        if width == 390:
            assert not await page.evaluate('window.isSecureContext')
        await page.locator('.tw-livequote').get_by_text('Streaming', exact=True).wait_for()
        await page.locator('.tw-livequote').get_by_text('Day vol 1.2M', exact=True).wait_for()
        await feeds[-1].tick(price=124.50)
        await page.locator('.tw-livequote').get_by_text('$124.50', exact=True).wait_for()
        await page.locator('.tw-livequote').get_by_text('Day vol —', exact=True).wait_for()
        assert len(feeds) == 1
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await feeds[-1].tick(day_volume=1200020)
        await page.locator('.tw-livequote').get_by_text('Day vol 1.2M', exact=True).wait_for()
        await page.locator('.tw-assetbar').screenshot(path=str(ROOT / f'docs/imgs/ticker-live-quote-{width}.png'))

        await page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true, value:'hidden'}); document.dispatchEvent(new Event('visibilitychange'))")
        await page.locator('.tw-livequote').get_by_text('Paused', exact=True).wait_for()
        async with asyncio.timeout(1):
            while any(f.active for f in feeds):
                await asyncio.sleep(0.01)
        await page.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true, value:'visible'}); document.dispatchEvent(new Event('visibilitychange'))")
        await page.locator('.tw-livequote').get_by_text('Streaming', exact=True).wait_for()
        assert len(feeds) == 2
        await page.evaluate("history.pushState({}, '', '/market/DEMO'); dispatchEvent(new PopStateEvent('popstate'))")
        await page.locator('.tw-assetbar__symbol').get_by_text('DEMO', exact=True).wait_for()
        await page.locator('.tw-livequote').get_by_text('Streaming', exact=True).wait_for()
        assert len(feeds) == 3 and feeds[-1].symbol == 'DEMO'
        await page.get_by_role('button', name='Back to Market', exact=True).click()
        async with asyncio.timeout(1):
            while any(f.active for f in feeds):
                await asyncio.sleep(0.01)
        assert not {"market.refresh", "market.brief.run", "market.scans.run"}.intersection(requests)
        assert not errors, errors
        print(f"PASS {width}px: stream/readout/volume/hidden/resume/switch/unmount; no scan; no console errors")
    finally:
        for resource in resources:
            await resource.close()
        await context.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for width in (1440, 1100, 390):
                await verify(browser, width)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
