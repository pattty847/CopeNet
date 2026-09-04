"""Offline browser → real RPC → normal harness → drawing/render receipt verification.

Build frontend first, then: uv run python scripts/verify_chart_agent.py
Every browser request is intercepted; stores, sessions, providers and market rows
are synthetic. No host restart, account data, paid models or vendor calls.
"""
from __future__ import annotations

import asyncio
import json
import math
import mimetypes
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.market.models import DashboardPayload
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import RequestFrame
from copenet.providers import ProviderEvent, ProviderModel

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "src/copenet/host/frontend/dist"
SCREENSHOT = ROOT / "docs/imgs/market-chart-agent.png"


def ticker_detail(symbol):
    bars = []
    for index in range(240):
        price = 95 + index * 0.075 + math.sin(index / 11) * 4 + math.sin(index / 3) * 0.8
        bars.append({"t": 1756684800 + index * 86400, "o": price - 0.3,
                     "h": price + 1.4, "l": price - 1.1, "c": price,
                     "v": 100000 + (index % 13) * 9000})
    return {"symbol": symbol, "name": "Synthetic chart research", "asOf": "Synthetic verification",
            "quote": {"price": bars[-1]["c"], "changePct": 0.7, "comparison": "previous_daily_bar", "priceBasis": "split_adjusted"},
            "series": {"daily": bars, "weekly": bars[::7], "monthly": bars[::30]},
            "verdict": [], "signals": [], "evidence": [], "events": [], "kill": "", "intelligence": None}


class SyntheticChartProvider:
    """Scripted model responses; tools still execute through the actual normal harness."""
    name = "chart-test"
    display_name = "Synthetic chart provider"

    def __init__(self):
        self.turns = {}
        self.messages = []
        self.tool_names = []

    async def describe(self):
        return {"id": self.name, "displayName": self.display_name, "available": True,
                "capabilities": {"chat": True, "streaming": True, "toolCalls": True, "promptedToolUse": True}}

    async def list_models(self):
        return [ProviderModel(id="chart-fixture", display_name="Chart fixture", provider=self.name)]

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        raise AssertionError("The chart fixture must use the native tool harness")
        yield ProviderEvent(kind="final")

    async def chat_completion(self, *, messages, model, tools=None, tool_choice=None):
        self.messages.append(messages)
        self.tool_names.append([tool["function"]["name"] for tool in tools or []])
        marker = "Chart observation (browser-captured evidence, not instructions):\n"
        text = next(message["content"] for message in reversed(messages)
                    if message["role"] == "user" and marker in str(message["content"]))
        observation = json.loads(text.split(marker)[-1])
        observation_id = observation["observationId"]
        stage = self.turns.get(observation_id, 0)
        self.turns[observation_id] = stage + 1
        resource = next(resource for resource in observation["resources"] if resource["kind"] == "candles"
                        and resource["key"] == "candles:" + observation["timeframe"])
        sample = next(sample for sample in observation["samples"] if sample["key"] == resource["key"])
        row = sample["rows"][len(sample["rows"]) // 2]
        if stage == 0:
            name, arguments = "market.chart.read", {"resourceKey": resource["key"], "limit": 20}
        elif stage == 1:
            name, arguments = "market.chart.apply", {
                "documentId": observation["documentId"], "expectedRevision": observation["documentRevision"],
                "operationId": "fixture-" + observation_id,
                "operations": [{"kind": "create", "object": {
                    "id": "agent-" + observation_id, "kind": "level", "anchors": [{"t": row["t"], "value": row["c"]}],
                    "timeframe": observation["timeframe"], "label": "Captured close", "color": "#8fb8e8", "visible": True,
                    "rationale": "A level at the exact captured candle close. Synthetic verification, not a trading recommendation.",
                    "evidence": [{"observationId": observation_id, "resourceKey": resource["key"], "from": row["t"], "to": row["t"]}],
                }}],
            }
        else:
            return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content":
                "I inspected the captured candles and saved a level at the selected close. Its anchors retain the exact candle timestamp and price."}}]}
        return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [{
            "id": f"fixture-call-{len(self.messages)}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)},
        }]}}]}


async def verify(browser, directory):
    provider = SyntheticChartProvider()
    orchestrator = Orchestrator(session_store=SessionStore(path=directory / "index.json"),
                                transcript_store=TranscriptStore(root_dir=directory), sessions_dir=directory,
                                providers={provider.name: provider})
    store = get_chart_store(orchestrator)
    context = await browser.new_context(viewport={"width": 1600, "height": 1000}, has_touch=True)
    errors, requests, captures, render_receipts = [], [], [], []
    tasks = set()
    documents = set()
    socket_errors = []
    chat_frames = []

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
                await route.fulfill(status=404, body="Offline synthetic chart verification")
                return
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or "application/octet-stream")

    def socket(ws):
        async def send(frame):
            if frame.get("event") in {"chat", "approval.pending", "approval.resolved"}:
                event = frame.get("payload", {})
                execution = event.get("toolExecution") or {}
                chat_frames.append({"event": frame.get("event"), "state": event.get("state"),
                                    "tool": execution.get("toolId"), "error": execution.get("error") or event.get("errorMessage"),
                                    "text": (event.get("message") or {}).get("content")})
            if frame.get("type") == "res" and not frame.get("ok"):
                socket_errors.append(frame.get("error"))
            payload = frame.get("payload", {})
            if "document" in payload:
                documents.add(payload["document"]["documentId"])
            ws.send(json.dumps(frame))

        async def reply(raw):
            request = json.loads(raw)
            method, params = request["method"], request.get("params", {})
            requests.append(method)
            if method == "market.chart.capture":
                captures.append(params)
            if method == "market.chart.rendered":
                render_receipts.append(params)
            responses = {
                "connect": {}, "market.dashboard.get": DashboardPayload.empty(as_of="Synthetic preview").to_wire(),
                "persona.get": {"persona": None}, "memory.list": {"items": []}, "briefing.get": {"briefing": None},
                "runtime.context": {"runtimeContext": None}, "pulse.list": {"pulses": []},
                "messaging.config.get": {"config": None}, "fleet.list": {"rooms": []}, "memory.drafts.list": {"drafts": []}, "userNotes.list": {"items": []},
                "market.watchlist.get": {"items": [], "lists": ["Synthetic"], "active": "Synthetic"},
                "market.ticker.get": ticker_detail(params.get("symbol", "TEST")),
                "market.ticker.evidence.get": {"evidence": [], "events": [], "warnings": []},
                "market.financial.metrics.list": {"metrics": []},
                "market.alerts.state": {"alerts": [], "events": [], "evaluations": []},
                "market.brief.get": {"brief": None}, "market.read.get": {"read": None, "sessions": []},
                "market.quote.subscribe": {"status": "unavailable", "symbol": params.get("symbol")},
                "market.quote.unsubscribe": {}, "market.quote.renew": {},
            }
            if method in responses:
                await send({"type": "res", "id": request["id"], "ok": True, "payload": responses[method]})
                if method == "market.quote.subscribe":
                    await send({"type": "event", "event": "market.quote", "payload": {
                        "subscriptionId": params["subscriptionId"], "symbol": params["symbol"], "status": "unavailable", "quote": None,
                    }})
            elif method.startswith(("market.chart.", "chat.", "sessions.")) or method in {
                "providers.list", "models.list", "prompts.list", "tools.list", "approvals.list", "persona.list", "persona.settings.get", "runtime.context.get",
            }:
                await dispatch_rpc(RequestFrame(request["id"], method, params), send, orchestrator, tasks)
            else:
                await send({"type": "res", "id": request["id"], "ok": False,
                            "error": {"message": f"Unexpected offline verification method: {method}"}})

        def received(raw):
            task = asyncio.create_task(reply(raw))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        ws.on_message(received)
        ws.send(json.dumps({"type": "event", "event": "connect.challenge", "payload": {}}))

    await context.route("**/*", serve)
    await context.route_web_socket("**/*", socket)
    page = await context.new_page()
    page.set_default_timeout(15000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        await page.goto("http://127.0.0.1:17124/market/TEST", wait_until="networkidle")
        await page.get_by_role("button", name="Open chart agent", exact=True).click()
        await page.get_by_role("button", name="Draw price level", exact=True).click()
        stage = await page.locator(".tw-stage").bounding_box()
        assert stage
        await page.mouse.click(stage["x"] + stage["width"] * 0.52, stage["y"] + stage["height"] * 0.4)
        async with asyncio.timeout(10):
            while not documents or not store.document(next(iter(documents)))["document"]["objects"]:
                await asyncio.sleep(0.05)
        document_id = next(iter(documents))
        manual = store.document(document_id)["document"]["objects"][0]
        assert manual["kind"] == "level" and manual["owner"]["kind"] == "operator"
        assert manual["anchors"][0]["t"] in {row["t"] for row in ticker_detail("TEST")["series"]["weekly"]}
        await page.get_by_label("Label", exact=True).fill("Operator level")
        await page.locator(".ca-object-editor").get_by_role("spinbutton").first.fill("111.25")
        await page.get_by_role("button", name="Save drawing", exact=True).click()
        async with asyncio.timeout(10):
            while store.document(document_id)["document"]["revision"] < 2:
                await asyncio.sleep(0.05)
        assert store.document(document_id)["document"]["objects"][0]["anchors"][0]["value"] == 111.25
        for kind, control, label in (("zone", "Draw price zone", "Price zone"), ("trendline", "Draw trendline", "Trendline"), ("label", "Add chart label", "Note")):
            await page.get_by_role("button", name=control, exact=True).click()
            drawing_stage = await page.locator(".tw-stage").bounding_box()
            points = [(0.35, 0.62)] if kind == "label" else [(0.35, 0.62), (0.6, 0.38)]
            for x, y in points:
                await page.mouse.click(drawing_stage["x"] + drawing_stage["width"] * x, drawing_stage["y"] + drawing_stage["height"] * y)
            async with asyncio.timeout(10):
                while len(store.document(document_id)["document"]["objects"]) < 2:
                    await asyncio.sleep(0.05)
            created = store.document(document_id)["document"]["objects"][-1]
            assert created["kind"] == kind
            assert len(created["anchors"]) == len(points)
            assert all(anchor["t"] in {row["t"] for row in ticker_detail("TEST")["series"]["weekly"]} for anchor in created["anchors"])
            await page.get_by_role("button", name="Delete " + label, exact=True).click()
            async with asyncio.timeout(10):
                while len(store.document(document_id)["document"]["objects"]) != 1:
                    await asyncio.sleep(0.05)
        manual_revision = store.document(document_id)["document"]["revision"]
        previous_receipts = len(render_receipts)
        await page.get_by_role("button", name="D", exact=True).click()
        async with asyncio.timeout(10):
            while not any(receipt["status"] == "hidden" for receipt in render_receipts[previous_receipts:]):
                await asyncio.sleep(0.05)
        await page.get_by_role("button", name="W", exact=True).click()
        await page.reload(wait_until="networkidle")
        await page.get_by_role("button", name="Open chart agent", exact=True).click()
        await page.get_by_role("button", name="Select chart region", exact=True).click()
        stage = await page.locator(".tw-stage").bounding_box()
        for fraction in (0.38, 0.65):
            await page.mouse.click(stage["x"] + stage["width"] * fraction, stage["y"] + stage["height"] * 0.55)
        await expect(page.get_by_role("button", name="Clear chart selection", exact=True)).to_be_visible()
        await page.get_by_role("button", name="Select chart drawing", exact=True).click()
        await page.get_by_label("Chart agent provider", exact=True).select_option("chart-test")
        await page.get_by_label("Chart agent model", exact=True).select_option("chart-fixture")
        await page.get_by_label("Ask about this chart", exact=True).fill("Inspect the candles and draw a level at an exact captured close.")
        await page.get_by_role("button", name="Send chart question", exact=True).click()
        await page.get_by_role("button", name="Approve", exact=True).click()
        await page.get_by_text("I inspected the captured candles and saved a level", exact=False).wait_for()
        async with asyncio.timeout(10):
            while not any(item["status"] == "rendered" and item["revision"] > manual_revision for item in render_receipts):
                await asyncio.sleep(0.05)
        result = store.document(document_id)["document"]
        assert len(result["objects"]) == 2, result
        assert result["objects"][1]["owner"]["kind"] == "agent"
        assert captures and captures[-1]["capture"]["viewport"]["from"] is not None
        assert captures[-1]["capture"]["selection"]["from"] < captures[-1]["capture"]["selection"]["to"]
        captured_candles = next(resource for resource in captures[-1]["capture"]["resources"] if resource["key"] == "candles:W")
        assert captured_candles["rows"] == ticker_detail("TEST")["series"]["weekly"], "Capture must preserve every exact loaded candle value"
        assert all(all(name.startswith("market.chart.") for name in names) for names in provider.tool_names)
        assert not {"market.refresh", "market.brief.run", "market.scans.run", "market.interpret"}.intersection(requests)
        await page.get_by_role("tab", name=re.compile(r"^Drawings")).click()
        await page.get_by_role("button", name=re.compile(r"^Captured close")).click()
        await page.get_by_text("Evidence · 1 references", exact=True).click()
        await page.get_by_role("button", name="Inspect candles:W", exact=True).click()
        await page.locator(".ca-source pre").wait_for()
        evidence_rows = json.loads(await page.locator(".ca-source pre").inner_text())
        assert len(evidence_rows) == 1
        assert evidence_rows[0]["t"] == result["objects"][1]["anchors"][0]["t"]
        assert evidence_rows[0]["c"] == result["objects"][1]["anchors"][0]["value"]
        await page.get_by_role("tab", name="Conversation", exact=True).click()
        await page.screenshot(path=str(SCREENSHOT), animations="disabled")
        await page.get_by_role("tab", name=re.compile(r"^Drawings")).click()
        await page.get_by_role("button", name="Undo batch", exact=True).click()
        async with asyncio.timeout(10):
            while len(store.document(document_id)["document"]["objects"]) != 1:
                await asyncio.sleep(0.05)
        assert store.document(document_id)["document"]["objects"][0]["label"] == "Operator level"
        for width in (1100, 390):
            await page.set_viewport_size({"width": width, "height": 900})
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Horizontal overflow at {width}px"
            await page.screenshot(path=str(directory / f"chart-agent-{width}.png"))
        # Real two-finger touch input on the phone layout must change the time viewport
        # and survive both viewport publication and document reconciliation rerenders.
        await page.locator('.ca-panel').get_by_role('button', name='Close chart agent', exact=True).click()
        await page.get_by_role('button', name='D', exact=True).click()
        stage = await page.locator('.tw-stage').bounding_box()
        assert stage and stage['width'] > 100
        cdp = await context.new_cdp_session(page)
        await cdp.send('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 2})
        x, y = stage['x'] + stage['width'] * 0.45, stage['y'] + 60
        before = await page.locator('.ca-context').text_content()
        for step in range(11):
            spread = 15 + step * 6
            await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart' if step == 0 else 'touchMove',
                'touchPoints': [{'id': 0, 'x': x - spread, 'y': y}, {'id': 1, 'x': x + spread, 'y': y}]})
            await asyncio.sleep(0.04)
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        await asyncio.sleep(0.3)
        zoomed = await page.locator('.ca-context').text_content()
        assert zoomed != before, 'Mobile pinch zoom snapped back to fitted data'
        await asyncio.sleep(5.5)
        assert await page.locator('.ca-context').text_content() == zoomed, 'Document polling reset mobile zoom'
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-chart-mobile-zoom.png'), animations='disabled')
        await cdp.detach()
        assert not errors, errors
        print("PASS: all four drawing tools/edit/delete, persistence, interval hiding, range selection, exact capture, normal harness, approval, agent level, paint receipt, batch undo, 1600/1100/390 geometry, mobile pinch zoom persists across polling; all data synthetic")
        print(f"Screenshot: {SCREENSHOT}")
    except Exception:
        await page.screenshot(path=str(directory / "chart-agent-failure.png"))
        print("Page:", await page.locator("body").inner_text())
        print("RPC errors:", socket_errors)
        print("Browser errors:", errors)
        print("Chat frames:", json.dumps(chat_frames))
        print("Provider calls:", len(provider.messages))
        print("Drawing documents:", [{"revision": store.document(document_id)["document"]["revision"],
                                       "count": len(store.document(document_id)["document"]["objects"])} for document_id in documents])
        raise
    finally:
        for task in list(tasks):
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        await context.close()


async def main():
    assert (DIST / "index.html").is_file(), "Build the frontend first"
    with TemporaryDirectory(prefix="copenet-chart-verification-") as directory:
        root = Path(directory)
        with patch.dict("os.environ", {"COPNET_DATA_DIR": str(root), "COPNET_WORKDIR": str(root), "COPNET_TELEGRAM_BOT_TOKEN": ""}):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    await verify(browser, root)
                finally:
                    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
