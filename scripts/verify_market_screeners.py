"""Offline browser → real screener RPC → temporary storage; synthetic evidence only.

Run after npm run build: uv run python scripts/verify_market_screeners.py
"""
import asyncio
import json
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urlparse
from playwright.async_api import async_playwright, expect

from copenet.core.market.models import DashboardPayload
from copenet.core.market.scans.screeners.service import ScreenerService
from copenet.core.market.watchlist_store import WatchlistStore
from copenet.host.rpc_routes import RPC_ROUTES
from copenet.host.rpc_route_context import RpcContext
from copenet.host.rpc_schema import RequestFrame

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'src/copenet/host/frontend/dist'


def fixture():
    rows = []
    for index, (symbol, name, sector) in enumerate([
        ('DEMO', 'Demonstration Systems', 'Technology services'),
        ('TEST', 'Synthetic Industries', 'Producer manufacturing'),
        ('EXAMPLE', 'Example Consumer Group', 'Consumer services'),
    ]):
        rows.append({'id': f'NYSE:{symbol}', 'symbol': symbol, 'exchange': 'NYSE', 'name': name, 'sector': sector,
                     'type': 'stock', 'subtype': 'common', 'price': 100., 'marketCap': (20 + index * 8) * 1e9,
                     'averageVolume': 1e6, 'relativeVolume': 2. + index, 'change': -3. if index == 0 else 3.,
                     'rsi': 50., 'sma50': 99., 'sma200': 90., 'high52': 106., 'bandUpper': 103. + index,
                     'bandLower': 97., 'monthReturn': 4., 'updateMode': 'delayed_streaming_900'})
    return {'rows': rows, 'received': len(rows), 'invalid': 0, 'truncated': False}


async def verify(browser, root):
    watchlists = WatchlistStore(root / 'watchlist.json')
    calls, methods, errors, tasks = [], [], [], set()
    failure = False
    def fetch(config):
        calls.append(config)
        if failure:
            raise ValueError('Synthetic vendor failure; previous snapshot retained')
        return fixture()
    service = ScreenerService(root, watchlists, fetch=fetch)
    orchestrator = SimpleNamespace(_market_screeners=service)
    context = await browser.new_context(viewport={'width': 1440, 'height': 1080})
    async def serve(route):
        url = urlparse(route.request.url)
        if url.hostname != '127.0.0.1':
            await route.abort()
            return
        target = DIST / url.path.lstrip('/')
        if not target.is_file():
            target = DIST / 'index.html' if url.path.startswith('/market') else None
        if target is None:
            await route.fulfill(status=404, body='Offline verification')
            return
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')
    def socket(ws):
        async def reply(raw):
            request = json.loads(raw)
            method = request['method']; methods.append(method)
            async def send(frame):
                ws.send(json.dumps(frame))
            try:
                if method.startswith('market.screeners.'):
                    await RPC_ROUTES[method].invoke(RpcContext(RequestFrame(request['id'], method, request.get('params')), send, orchestrator, tasks, send))
                    return
                if method == 'market.watchlist.list.select':
                    watchlists.select_list(request['params']['name'])
                state = watchlists.state()
                responses = {
                    'connect': {}, 'market.dashboard.get': DashboardPayload.empty(as_of='Synthetic demonstration').to_wire(),
                    'market.brief.get': {'brief': None}, 'market.read.get': {'read': None, 'sessions': []},
                    'market.watchlist.get': {'items': [], 'lists': state['lists'], 'active': state['active']},
                    'market.watchlist.list.select': {'items': [], 'lists': state['lists'], 'active': state['active']},
                }
                if method not in responses:
                    raise ValueError('Not required by isolated screeners verification')
                await send({'type': 'res', 'id': request['id'], 'ok': True, 'payload': responses[method]})
            except Exception as exc:
                await send({'type': 'res', 'id': request['id'], 'ok': False, 'error': {'message': str(exc)}})
        def received(raw):
            task = asyncio.create_task(reply(raw)); tasks.add(task); task.add_done_callback(tasks.discard)
        ws.on_message(received)
        ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge', 'payload': {}}))
    await context.route('**/*', serve)
    await context.route_web_socket('**/*', socket)
    page = await context.new_page()
    page.set_default_timeout(10000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        await page.goto('http://127.0.0.1:17124/market?view=screeners', wait_until='networkidle')
        await expect(page.get_by_role('button', name='Review & run all five')).to_be_enabled()
        assert not calls
        await page.get_by_role('button', name='Review & run all five').click()
        await page.get_by_role('button', name='Run screeners', exact=True).wait_for()
        assert not calls
        await page.get_by_label('Min market cap ($B)').fill('12')
        assert await page.get_by_role('button', name='Run screeners', exact=True).count() == 0
        await page.get_by_role('button', name='Review & run all five').click()
        await page.get_by_role('button', name='Run screeners', exact=True).click()
        await page.get_by_role('button', name='DEMO ↗', exact=True).wait_for()
        assert len(calls) == 1 and calls[0].minCap == 12e9
        await page.locator('.scr-table summary').first.click()
        await expect(page.locator('.scr-table details').first).to_have_attribute('open', '')
        await page.locator('.scr-table summary').first.click()
        await page.get_by_label('Select DEMO', exact=True).check()
        await page.get_by_label('New research list').fill('Synthetic research')
        await page.get_by_role('button', name='Create watchlist', exact=True).click()
        await page.get_by_text('Created “Synthetic research”', exact=False).wait_for()
        assert next(item for item in watchlists.scan_lists() if item['name'] == 'Synthetic research')['entries'] == [{'symbol': 'DEMO', 'name': 'Demonstration Systems'}]
        assert watchlists.state()['active'] == 'Default'
        assert watchlists.state()['roles']['Synthetic research'] == 'context'
        async with page.expect_download() as download_info:
            await page.get_by_role('button', name='Export evidence JSON').click()
        downloaded = await (await download_info.value).path()
        exported = json.loads(Path(downloaded).read_text())
        assert exported['observations'] and exported['selectedSymbols'] == ['DEMO']
        await page.get_by_role('button', name='Clear', exact=True).click()
        await page.locator('.mw-section').evaluate('(element) => element.scrollTop = 0')
        await page.screenshot(path=str(ROOT / 'docs/imgs/market-screeners.png'))
        await page.get_by_label('Find in results').fill('no such name')
        await page.get_by_text('No results match this search.').wait_for()
        await page.get_by_label('Find in results').fill('')
        await page.get_by_role('button', name='03 Oversold large caps Bullish 0').click()
        await page.get_by_text('No companies match this setup', exact=False).wait_for()
        await page.reload(wait_until='networkidle')
        await page.get_by_text('No companies match this setup', exact=False).wait_for()
        assert len(calls) == 1
        await page.get_by_role('button', name='01 Compression Either 3').click()
        failure = True
        await page.get_by_role('button', name='Review & run all five').click()
        await page.get_by_role('button', name='Run screeners', exact=True).click()
        await page.get_by_role('alert').filter(has_text='Synthetic vendor failure').wait_for()
        await page.get_by_role('button', name='DEMO ↗', exact=True).wait_for()
        assert len(calls) == 2
        await page.set_viewport_size({'width': 390, 'height': 844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
        await page.get_by_role('button', name='DEMO ↗', exact=True).click()
        assert '/market/DEMO' in page.url
        assert not errors, errors
        assert not {'market.refresh', 'market.brief.run', 'market.interpret', 'market.scans.run'}.intersection(methods)
        print('PASS: real RPC preview/run, changed-scope invalidation, persisted evidence, create-only handoff, JSON export, search/empty/error, reload, ticker navigation, mobile geometry; no external requests')
    except Exception:
        await page.screenshot(path=str(root / 'failure.png'))
        print((await page.locator('.scr').inner_text())[:5000] if await page.locator('.scr').count() else await page.locator('body').inner_text())
        raise
    finally:
        if tasks: await asyncio.gather(*tasks)
        await context.close()


async def main():
    with TemporaryDirectory(prefix='copenet-screeners-') as directory:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try: await verify(browser, Path(directory))
            finally: await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
