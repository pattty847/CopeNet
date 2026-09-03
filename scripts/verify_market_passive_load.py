"""Offline browser regression: viewing Market never starts a full scan.

Run after npm run build: uv run python scripts/verify_market_passive_load.py
Every HTTP/WebSocket request is intercepted; no server, credentials, or vendor data.
"""

import asyncio
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from copenet.core.market.models import DashboardPayload

DIST = Path(__file__).resolve().parents[1] / "src/copenet/host/frontend/dist"
SCAN_METHODS = {"market.refresh", "market.brief.run"}


async def verify(browser, scenario):
    context = await browser.new_context(viewport={"width": 1100, "height": 850})
    requests = []
    errors = []
    dashboard = DashboardPayload.empty(as_of="No synthetic scan yet").to_wire()
    brief = None if scenario != "stale" else {
        "briefDate": "2000-01-03", "generatedAt": "2000-01-03T15:00:00Z",
        "headline": "Synthetic stale briefing", "newEvidence": [], "signalFlips": [],
        "rrgShifts": [], "movers": [], "firstSweep": False,
    }

    async def serve(route):
        path = urlparse(route.request.url)
        if path.hostname != "127.0.0.1":
            await route.abort()
            return
        target = DIST / path.path.lstrip("/")
        if not target.is_file():
            if path.path.startswith("/market"):
                target = DIST / "index.html"
            else:
                await route.fulfill(status=404, body="isolated test")
                return
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or "application/octet-stream")

    def socket(ws):
        def reply(raw):
            request = json.loads(raw)
            method = request["method"]
            requests.append(method)
            responses = {
                "connect": {}, "market.dashboard.get": dashboard,
                "market.brief.get": {"brief": brief},
                "market.watchlist.get": {"items": [], "lists": ["Synthetic"], "active": "Synthetic"},
                "market.read.get": {"read": None, "sessions": []},
                "market.refresh": {"startedAt": "synthetic", "runId": "synthetic"},
                "market.brief.run": {"startedAt": "synthetic"},
            }
            ok = method in responses and not (scenario == "offline" and method in {"market.dashboard.get", "market.brief.get"})
            frame = {"type": "res", "id": request["id"], "ok": ok}
            frame["payload" if ok else "error"] = responses[method] if ok else {"message": "Synthetic unavailable source"}
            ws.send(json.dumps(frame))
        ws.on_message(reply)
        ws.send(json.dumps({"type": "event", "event": "connect.challenge", "payload": {}}))

    await context.route("**/*", serve)
    await context.route_web_socket("**/*", socket)
    page = await context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        await page.goto("http://127.0.0.1:17124/market", wait_until="networkidle")
        await page.get_by_role("tab", name="Signals", exact=True).click()
        await page.get_by_role("tab", name="Briefing", exact=True).click()
        await page.reload(wait_until="networkidle")
        assert "market.dashboard.get" in requests and "market.brief.get" in requests
        assert not SCAN_METHODS.intersection(requests), (scenario, requests)
        await page.get_by_role("button", name="Refresh data", exact=True).click()
        await page.wait_for_timeout(100)
        assert requests.count("market.refresh") == 1
        await page.get_by_role("button", name="Sweep again" if brief else "Run sweep", exact=True).click()
        await page.wait_for_timeout(100)
        assert requests.count("market.brief.run") == 1
        assert not errors, errors
        print(f"PASS {scenario}: mount/navigation/reload read-only; explicit scan controls work")
    finally:
        await context.close()


async def main():
    assert (DIST / "index.html").is_file(), "Build the frontend first"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for scenario in ("empty", "stale", "offline"):
                await verify(browser, scenario)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
