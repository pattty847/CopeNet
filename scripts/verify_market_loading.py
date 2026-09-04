"""Offline loading-state regression and sanitized product screenshots.

Run after npm run build: uv run python scripts/verify_market_loading.py
All network traffic is intercepted. No host, credentials, scans or real holdings.
"""

import asyncio
import json
import mimetypes
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

from copenet.core.market.models import DashboardPayload
from verify_ticker_live_quote import detail

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "src/copenet/host/frontend/dist"
FORBIDDEN = {"market.refresh", "market.brief.run", "market.scans.run", "market.interpret"}


async def verify(browser, width):
    context = await browser.new_context(viewport={"width": width, "height": 900})
    requests, errors, pending = [], [], []
    held = {"market.dashboard.get", "market.brief.get", "market.read.get"}
    failed = set()
    dashboard = DashboardPayload.empty(as_of="Synthetic saved snapshot").to_wire()
    mobile_previews = Path(tempfile.mkdtemp(prefix="copenet-loading-")) if width == 390 else None
    brief = {
        "briefDate": "2000-01-03", "generatedAt": "2000-01-03T15:00:00Z",
        "headline": "Synthetic saved briefing", "newEvidence": [], "signalFlips": [],
        "rrgShifts": [], "movers": [], "firstSweep": False,
    }

    async def serve(route):
        url = urlparse(route.request.url)
        if url.hostname != "127.0.0.1":
            await route.abort()
            return
        target = DIST / url.path.lstrip("/")
        if not target.is_file():
            if url.path.startswith("/market"):
                target = DIST / "index.html"
            else:
                await route.fulfill(status=404, body="Isolated preview")
                return
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or "application/octet-stream")

    def respond(ws, request):
        method = request["method"]
        responses = {
            "connect": {}, "market.dashboard.get": dashboard,
            "market.brief.get": {"brief": brief},
            "market.watchlist.get": {"items": [], "lists": ["Synthetic"], "active": "Synthetic"},
            "market.read.get": {"read": None, "sessions": []},
            "market.ticker.get": detail(request.get("params", {}).get("symbol", "TEST")),
            "market.ticker.evidence.get": {"evidence": [], "events": [], "warnings": []},
            "market.financial.metrics.list": {"metrics": []},
            "market.alerts.state": {"alerts": [], "events": [], "evaluations": []},
        }
        ok = method in responses and method not in failed
        ws.send(json.dumps({"type": "res", "id": request["id"], "ok": ok,
                            "payload" if ok else "error": responses[method] if ok else {"message": "Synthetic unavailable source"}}))

    def release(method):
        held.discard(method)
        for item in list(pending):
            if item[1]["method"] == method:
                respond(*item)
                pending.remove(item)

    def socket(ws):
        def reply(raw):
            request = json.loads(raw)
            requests.append(request["method"])
            if request["method"] in held:
                pending.append((ws, request))
            else:
                respond(ws, request)
        ws.on_message(reply)
        ws.send(json.dumps({"type": "event", "event": "connect.challenge", "payload": {}}))

    await context.route("**/*", serve)
    await context.route_web_socket("**/*", socket)
    await context.add_init_script("""localStorage.setItem('mm-mw-layout-signals', JSON.stringify({
        order: ['trend', 'softBottoming', 'accumulation'], hidden: ['accumulation'], width: {trend: 'full'}
    }));""")
    page = await context.new_page()
    page.set_default_timeout(10000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        await page.clock.install()
        await page.goto("http://127.0.0.1:17124/market", wait_until="networkidle")
        loading = page.get_by_role("status").filter(has_text="Loading market workspace")
        await expect(loading).to_be_visible()
        await expect(page.get_by_text("No saved briefing yet.", exact=True)).to_have_count(0)
        if width == 1440:
            await page.screenshot(path=str(ROOT / "docs/imgs/market-workspace-loading.png"))
        elif mobile_previews:
            await page.screenshot(path=str(mobile_previews / "market.png"))
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await page.emulate_media(reduced_motion="reduce")
        assert await page.locator('.workspace-loading[aria-busy="true"]').first.evaluate(
            "el => getComputedStyle(el, '::after').animationName") == "none"

        # Tabs remain usable during acquisition; saved desktop panel choices also
        # apply to the outlines. Mobile deliberately uses the fixed layout.
        await page.get_by_role("tab", name="Signals", exact=True).click()
        panel_ids = await page.locator('.mw-grid > [data-panel]').evaluate_all("els => els.map(el => el.dataset.panel)")
        assert panel_ids == (["softBottoming", "accumulation", "trend"] if width == 390 else ["trend", "softBottoming"]), panel_ids
        await page.get_by_role("tab", name="Briefing", exact=True).click()
        release("market.dashboard.get")
        await expect(loading).to_be_visible()
        release("market.brief.get")
        await expect(loading).to_be_visible()
        release("market.read.get")
        await expect(loading).to_have_count(0)
        await expect(page.get_by_text("Synthetic saved briefing", exact=True)).to_be_visible()

        # A background failure retains the actual saved snapshot and briefing.
        failed.add("market.dashboard.get")
        await page.clock.fast_forward(30001)
        await expect(page.get_by_role("alert").filter(has_text="Refresh unavailable")).to_be_visible()
        await expect(page.get_by_text("Synthetic saved briefing", exact=True)).to_be_visible()
        await expect(loading).to_have_count(0)
        failed.clear()
        await page.get_by_role("button", name="Retry", exact=True).click()
        await expect(page.locator('.workspace-load-error')).to_have_count(0)

        # First-load failure is not an eternal skeleton; keyboard retry accepts
        # a valid empty dashboard and null brief without substituting samples.
        failed.update({"market.dashboard.get", "market.brief.get"})
        await page.reload(wait_until="networkidle")
        await expect(page.get_by_text("Market snapshot unavailable", exact=True)).to_be_visible()
        await expect(loading).to_have_count(0)
        brief = None
        failed.clear()
        await page.get_by_role("button", name="Retry", exact=True).focus()
        await page.keyboard.press("Enter")
        await expect(page.get_by_text("No saved briefing yet.", exact=True)).to_be_visible()
        await expect(page.get_by_text("Synthetic saved snapshot", exact=True)).to_be_visible()
        await expect(page.locator('.mw-bar__stat b')).to_have_text(['—', '—'])
        await expect(page.get_by_text("No saved regime yet.", exact=True)).to_be_visible()

        # Ticker loading keeps its real back navigation and never opens a quote
        # subscription before the detail is ready.
        held.add("market.ticker.get")
        await page.goto("http://127.0.0.1:17124/market/TEST", wait_until="networkidle")
        ticker_loading = page.get_by_role("status").filter(has_text="Loading TEST workspace")
        await expect(ticker_loading).to_be_visible()
        await expect(page.get_by_role("button", name="Back to Market", exact=True)).to_be_visible()
        assert "market.quote.subscribe" not in requests
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if width == 1440:
            await page.screenshot(path=str(ROOT / "docs/imgs/ticker-workspace-loading.png"))
        elif mobile_previews:
            await page.screenshot(path=str(mobile_previews / "ticker.png"))
        failed.add("market.ticker.get")
        release("market.ticker.get")
        await expect(page.get_by_role("alert").filter(has_text="Could not load TEST")).to_be_visible()
        await expect(ticker_loading).to_have_count(0)
        failed.clear()
        await page.get_by_role("button", name="Retry", exact=True).click()
        await expect(page.locator('.tw-livequote')).to_be_visible()
        await page.get_by_role("button", name="Back to Market", exact=True).click()
        await expect(page.get_by_role("tab", name="Briefing", exact=True)).to_be_visible()
        assert not FORBIDDEN.intersection(requests), requests
        assert not errors, errors
        print(f"PASS {width}px: staged load, saved layout, empty, failure, retry, retained refresh, reduced motion, ticker, no scans")
        if mobile_previews:
            print(f"Mobile previews: {mobile_previews}")
    finally:
        await context.close()


async def main():
    assert (DIST / "index.html").is_file(), "Build the frontend first"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for width in (1440, 1100, 390):
                await verify(browser, width)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
