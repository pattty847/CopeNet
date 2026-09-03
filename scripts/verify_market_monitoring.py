"""Offline UI → real RPC → isolated-store verification; no network/vendor credentials.

Build frontend first, then: uv run python scripts/verify_market_monitoring.py
Screenshots use synthetic state only, under docs/imgs/market-scans-alerts*.png.
"""
import asyncio
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urlparse
from unittest.mock import patch

from playwright.async_api import async_playwright
from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore
from copenet.core.market.scans.service import ScanService
from copenet.core.market.models import DashboardPayload
from copenet.core.messaging.store import MessagingConfigRecord
from copenet.host.rpc_market_monitoring import MARKET_MONITORING_HANDLERS

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'src/copenet/host/frontend/dist'


class SyntheticSources:
    def __init__(self):
        self.calls = []
        self.cache = {}

    def cached(self, source, symbol, now):
        return self.cache.get((source, symbol))

    async def acquire(self, source, symbol):
        self.calls.append((source, symbol))
        result = {'updatedAt': datetime.now(timezone.utc).isoformat(), 'payload': {'evidence': []}}
        self.cache[source, symbol] = result
        return result


async def verify(browser, root):
    runtime = MarketRuntime(store=MarketStore(root))
    runtime.watchlists.add('TEST')
    sources = SyntheticSources()
    service = ScanService(runtime, sources=sources, pace=0)
    service.store.save({'name': 'Core research', 'symbols': ['TEST', 'DEMO'], 'sources': ['prices'], 'times': ['09:45', '16:15'], 'days': [0, 1, 2, 3, 4]})
    orchestrator = SimpleNamespace(_market_runtime=runtime, _market_scan_service=service, _messaging_store=SimpleNamespace(load=lambda: MessagingConfigRecord()))
    context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
    methods, errors = [], []
    tasks = set()

    async def serve(route):
        path = urlparse(route.request.url)
        if path.hostname != '127.0.0.1':
            await route.abort()
            return
        target = DIST / path.path.lstrip('/')
        if not target.is_file():
            if path.path.startswith('/market'):
                target = DIST / 'index.html'
            else:
                await route.fulfill(status=404, body='offline verification')
                return
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')

    def socket(ws):
        async def reply(raw):
            request = json.loads(raw)
            method = request['method']
            methods.append(method)
            async def send(frame):
                ws.send(json.dumps(frame))
            try:
                if method in MARKET_MONITORING_HANDLERS:
                    assert method not in {'market.notifications.test', 'market.notifications.action'}, 'Unexpected delivery action'
                    await MARKET_MONITORING_HANDLERS[method](request['id'], request.get('params'), send, orchestrator)
                    return
                responses = {
                    'connect': {}, 'market.dashboard.get': DashboardPayload.empty(as_of='Synthetic preview').to_wire(),
                    'market.brief.get': {'brief': None},
                    'market.watchlist.get': {'items': [], 'lists': ['Default'], 'active': 'Default'},
                    'market.read.get': {'read': None, 'sessions': []},
                }
                if method not in responses:
                    raise ValueError('Source not needed by this isolated verification')
                await send({'type': 'res', 'id': request['id'], 'ok': True, 'payload': responses[method]})
            except Exception as exc:
                await send({'type': 'res', 'id': request['id'], 'ok': False, 'error': {'message': str(exc)}})
        def received(raw):
            task = asyncio.create_task(reply(raw))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        ws.on_message(received)
        ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge', 'payload': {}}))

    await context.route('**/*', serve)
    await context.route_web_socket('**/*', socket)
    page = await context.new_page()
    page.set_default_timeout(10000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        await page.goto('http://127.0.0.1:17124/market?view=scans', wait_until='networkidle')
        await page.get_by_role('button', name='Core research', exact=True).wait_for()
        assert not sources.calls
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-scans-alerts.png'))
        await page.get_by_role('button', name='+ New scan', exact=True).click()
        await page.get_by_label('Name', exact=True).fill('Filings only')
        await page.get_by_label('Add symbols', exact=True).fill('TEST')
        await page.get_by_label('Prices & technical screens', exact=True).uncheck()
        await page.get_by_label('SEC · Form 4, 8-K & 144', exact=True).check()
        await page.get_by_label('Times · 24-hour', exact=True).fill('09:45, 14:15')
        await page.get_by_role('button', name='Preview exact scope & cache work').click()
        await page.get_by_text('Why each asset is included', exact=True).wait_for()
        assert not sources.calls
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-scans-editor.png'))
        await page.get_by_role('button', name='Save scan', exact=True).click()
        await page.get_by_role('button', name='Filings only', exact=True).wait_for()
        row = page.locator('article').filter(has=page.get_by_role('button', name='Filings only', exact=True))
        await row.get_by_role('button', name='Run now…', exact=True).click()
        assert not sources.calls
        await page.get_by_role('button', name='Run this scan', exact=True).click()
        await page.get_by_text('Scan started. Follow its progress in Activity.', exact=True).wait_for()
        assert sources.calls == [('sec', 'TEST')], sources.calls
        await page.get_by_role('button', name='Activity', exact=True).click()
        await page.get_by_role('button', name='Inspect results', exact=True).click()
        await page.get_by_text('TEST · sec · acquired', exact=True).wait_for()
        await page.keyboard.press('Escape')
        await page.get_by_role('button', name='Alerts · 0', exact=True).click()
        await page.get_by_role('button', name='+ New alert', exact=True).click()
        await page.get_by_label('Symbol', exact=True).fill('TEST')
        await page.get_by_label('Timeframe', exact=True).select_option('weekly')
        await page.get_by_label('Evaluate after scan', exact=True).select_option(label='Core research')
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-alert-editor.png'))
        await page.get_by_role('button', name='Arm alert', exact=True).click()
        await page.get_by_text('missing history', exact=True).wait_for()
        await page.get_by_role('button', name='Pause', exact=True).click()
        await page.get_by_text('paused', exact=True).wait_for()
        await page.get_by_role('button', name='Re-arm', exact=True).click()
        await page.get_by_text('missing history', exact=True).wait_for()
        assert sources.calls == [('sec', 'TEST')]
        await page.reload(wait_until='networkidle')
        await page.get_by_text('missing history', exact=True).wait_for()
        assert 'panel=alerts' in page.url
        await page.get_by_role('button', name='Edit', exact=True).click()
        await page.get_by_label('Threshold', exact=True).fill('65')
        await page.keyboard.press('Escape')
        assert await page.locator('dialog[open]').count() == 0
        assert await page.evaluate("document.activeElement.textContent") == 'Edit'
        await page.get_by_role('button', name='Scans · 3', exact=True).click()
        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-scans-mobile.png'))
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflow'
        await page.get_by_role('button', name='+ New scan', exact=True).click()
        assert await page.evaluate("document.querySelector('dialog').getBoundingClientRect().width <= innerWidth")
        await page.get_by_label('Name', exact=True).fill('Mobile draft')
        await page.get_by_role('button', name='Save scan', exact=True).scroll_into_view_if_needed()
        assert await page.evaluate("document.querySelector('dialog').scrollTop > 0"), 'Editor must own one vertical scroll'
        await page.keyboard.press('Escape')
        await page.set_viewport_size({'width': 1100, 'height': 850})
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-scans-compact.png'))
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        assert 'market.refresh' not in methods and 'market.brief.run' not in methods
        print('PASS: real RPC CRUD, scope preview, isolated SEC run, weekly rule, reload, keyboard, 1440/1100/390 geometry; no external requests')
    except Exception:
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-monitoring-failure.png'))
        print(await page.locator('dialog').inner_text() if await page.locator('dialog').count() else await page.locator('.mm-monitor').inner_text(), flush=True)
        raise
    finally:
        await asyncio.gather(*tasks)
        await context.close()


async def main():
    with TemporaryDirectory(prefix='copenet-monitoring-') as directory, patch.dict('os.environ', {'COPNET_TELEGRAM_BOT_TOKEN': '', 'COPNET_MARKET_SENTINEL': '1'}):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                await verify(browser, Path(directory))
            finally:
                await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
