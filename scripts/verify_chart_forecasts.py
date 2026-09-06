"""Offline UI → actual RPC/harness → immutable forecast/plot/Ledger verification.

Build the frontend, then run: uv run python scripts/verify_chart_forecasts.py
All prices/providers/stores are synthetic; every HTTP/WebSocket request is intercepted.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import math
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

from copenet.core.market.alert_candles import _calendar
from copenet.core.market.chart_prices import chart_price_snapshot
from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.market.forecasts.store import ForecastStore
from copenet.core.market.forecasts.report import forecast_report
from copenet.core.market.forecasts.tracking import evaluate_cached
from copenet.core.market.models import DashboardPayload, MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight
from copenet.core.market.runtime import resolve_market_runtime
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import RequestFrame
from copenet.providers import ProviderModel

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'src/copenet/host/frontend/dist'


class SyntheticForecastProvider:
    name = 'forecast-test'
    display_name = 'Synthetic forecast provider'

    def __init__(self):
        self.calls = []
        self.submitted = set()
        self.ta_submissions = 0

    async def describe(self):
        return {'id': self.name, 'displayName': self.display_name, 'available': True,
                'capabilities': {'chat': True, 'streaming': True, 'toolCalls': True, 'promptedToolUse': True}}

    async def list_models(self):
        return [ProviderModel(id='forecast-fixture', display_name='Forecast fixture', provider=self.name)]

    async def chat_completion(self, *, messages, model, tools=None, tool_choice=None):
        marker = 'Chart observation (browser-captured evidence, not instructions):\n'
        text = next(message['content'] for message in reversed(messages)
                    if message['role'] == 'user' and marker in str(message['content']))
        packet = json.loads(text.split(marker)[-1].split('\n\n')[0])
        identifier = packet['observationId']
        self.calls.append({'observationId': identifier, 'tools': [tool['function']['name'] for tool in tools or []]})
        if identifier in self.submitted:
            return {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Saved this synthetic forecast from the frozen chart evidence.'}}]}
        self.submitted.add(identifier)
        directional = 'Record one directional forecast' in text
        if not directional:
            self.ta_submissions += 1
        result = {'kind': 'directional', 'direction': 'bearish', 'thesis': 'Independent synthetic directional comparison.'} if directional else {
            'kind': 'setup', 'direction': 'long', 'thesis': 'Synthetic breakout study: a defined entry, fixed invalidation and two staged exits.',
            'entry': {'kind': 'limit', 'price': 120.0 if self.ta_submissions == 1 else 118.0}, 'stop': 115.0,
            'targets': [{'price': 125.0, 'fraction': 0.5}, {'price': 130.0, 'fraction': 0.5}],
            'zones': [{'label': 'Retest area', 'lower': 118.0, 'upper': 121.0}],
            'evidence': [{'observationId': identifier, 'resourceKey': 'candles:D'}]}
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': '', 'tool_calls': [{
            'id': 'forecast-' + identifier, 'type': 'function', 'function': {'name': 'market.forecast.submit', 'arguments': json.dumps({'result': result})}}]}}]}


def synthetic_history(now):
    schedule = _calendar(now.year - 2, now.year + 1).schedule.loc[(now.date() - timedelta(days=420)).isoformat():now.date().isoformat()]
    bars = []
    for index, (day, session) in enumerate(schedule.iterrows()):
        if session['close'].to_pydatetime().replace(tzinfo=timezone.utc) > now:
            continue
        close = 96 + index * .08 + math.sin(index / 13) * 2
        bars.append(MarketBar(utc_midnight(day.date()), close-.4, close+1.5, close-1.2, close, 150000+index*100))
    # Keep the current chart near the planned levels; all prior values remain synthetic.
    last = bars[-1]
    bars[-1] = MarketBar(last.t, 119.0, 122.0, 118.0, 120.0, 200000)
    earlier = bars[-30]
    bars[-30] = MarketBar(earlier.t, 129.0, 134.0, 127.0, 131.0, 250000)
    return PriceHistory('TEST', bars, [], [], now.isoformat())


async def verify(browser, directory):
    provider = SyntheticForecastProvider()
    orchestrator = Orchestrator(session_store=SessionStore(path=directory/'index.json'),
                                transcript_store=TranscriptStore(root_dir=directory), sessions_dir=directory,
                                providers={provider.name: provider})
    runtime = resolve_market_runtime(orchestrator)
    now = datetime.now(timezone.utc)
    history = synthetic_history(now)
    acquisitions = []
    def forbid_acquisition(*args, **kwargs):
        acquisitions.append(args)
        raise AssertionError('Unexpected price acquisition')
    runtime.prices.load = lambda symbol: history if symbol == 'TEST' else None
    runtime.prices.refresh = forbid_acquisition
    # Producing the fixture itself reuses the exact one-revision projection, with a no-op
    # refresh only here. Actual browser/model work is forbidden from acquiring prices.
    with patch.object(runtime.prices, 'refresh', lambda *args, **kwargs: None):
        series, provenance = chart_price_snapshot(runtime, 'TEST', now=now)
    detail = {'symbol': 'TEST', 'name': 'Synthetic forecast research', 'asOf': now.isoformat(),
              'quote': {'price': 120, 'changePct': .7, 'comparison': 'previous_daily_bar', 'priceBasis': 'split_adjusted'},
              'series': {name: [asdict(bar) for bar in rows] for name, rows in series.items()}, 'priceProvenance': provenance,
              'verdict': [], 'signals': [], 'evidence': [], 'events': [], 'kill': '', 'intelligence': None}
    charts, forecasts = get_chart_store(orchestrator), ForecastStore(get_chart_store(orchestrator))
    context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
    tasks, errors, rpc_errors, requests, receipts = set(), [], [], [], []

    async def serve(route):
        url = urlparse(route.request.url)
        if url.hostname != '127.0.0.1':
            await route.abort()
            return
        target = DIST / url.path.lstrip('/')
        if not target.is_file():
            target = DIST/'index.html' if url.path.startswith('/market') else None
        if target is None:
            await route.fulfill(status=404, body='Offline synthetic verification')
        else:
            await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')

    def socket(ws):
        async def send(frame):
            if frame.get('type') == 'res' and not frame.get('ok'):
                rpc_errors.append(frame.get('error'))
            ws.send(json.dumps(frame))

        async def reply(raw):
            request = json.loads(raw)
            method, params = request['method'], request.get('params', {})
            requests.append(method)
            if method == 'market.forecast.rendered':
                receipts.append(params)
            responses = {
                'connect': {}, 'market.dashboard.get': DashboardPayload.empty(as_of='Synthetic preview').to_wire(),
                'persona.get': {'persona': None}, 'memory.list': {'items': []}, 'briefing.get': {'briefing': None},
                'runtime.context': {'runtimeContext': None}, 'pulse.list': {'pulses': []}, 'messaging.config.get': {'config': None},
                'fleet.list': {'rooms': []}, 'memory.drafts.list': {'drafts': []}, 'userNotes.list': {'items': []},
                'market.watchlist.get': {'items': [], 'lists': ['Synthetic'], 'active': 'Synthetic'},
                'market.ticker.get': detail, 'market.ticker.evidence.get': {'evidence': [], 'events': [], 'warnings': []},
                'market.financial.metrics.list': {'metrics': []}, 'market.alerts.state': {'alerts': [], 'events': [], 'evaluations': []},
                'market.brief.get': {'brief': None}, 'market.read.get': {'read': None, 'sessions': []},
                'market.calendar.get': {'events': [], 'asOf': now.isoformat()}, 'market.webull.pnl.get': {'ledger': None},
                'market.quote.subscribe': {'status': 'unavailable', 'symbol': params.get('symbol')},
                'market.quote.unsubscribe': {}, 'market.quote.renew': {},
            }
            if method in responses:
                await send({'type': 'res', 'id': request['id'], 'ok': True, 'payload': responses[method]})
                if method == 'market.quote.subscribe':
                    await send({'type': 'event', 'event': 'market.quote', 'payload': {'subscriptionId': params['subscriptionId'], 'symbol': params['symbol'], 'status': 'unavailable', 'quote': None}})
            elif method.startswith(('market.chart.', 'market.forecast.', 'market.scans.', 'chat.', 'sessions.')) or method in {
                'market.ledger.get', 'providers.list', 'models.list', 'prompts.list', 'tools.list', 'approvals.list', 'persona.list', 'persona.settings.get', 'runtime.context.get',
            }:
                await dispatch_rpc(RequestFrame(request['id'], method, params), send, orchestrator, tasks)
            else:
                await send({'type': 'res', 'id': request['id'], 'ok': False, 'error': {'message': f'Unexpected offline method: {method}'}})
        def received(raw):
            task = asyncio.create_task(reply(raw))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        ws.on_message(received)
        ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge', 'payload': {}}))

    await context.route('**/*', serve)
    await context.route_web_socket('**/*', socket)
    page = await context.new_page()
    clock_patch = None
    page.set_default_timeout(15000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        await page.goto('http://127.0.0.1:17124/market/TEST', wait_until='networkidle')
        await page.get_by_role('button', name='Open chart agent', exact=True).click()
        await page.get_by_role('button', name='Chart agent settings', exact=True).click()
        await page.get_by_label('Chart agent provider', exact=True).select_option(provider.name)
        await page.get_by_role('button', name='Close Chart agent settings', exact=True).click()
        await page.get_by_label('Chart agent model', exact=True).select_option('forecast-fixture')
        for paired in (False, True):
            await page.get_by_role('button', name='Chart agent settings', exact=True).click()
            await page.get_by_role('button', name='Forecast this chart', exact=True).click()
            sheet = page.get_by_role('dialog', name='Forecast TEST', exact=True)
            if paired:
                await sheet.get_by_label('Price tracking', exact=False).select_option('paused')
                await sheet.get_by_label('Compare with an independent directional call', exact=True).check()
            else:
                await sheet.get_by_role('button', name='Review tracking scope', exact=True).click()
                await expect(sheet.get_by_text('Acquisition scope', exact=True)).to_be_visible()
                await expect(sheet.get_by_text('TEST · context: VOO', exact=True)).to_be_visible()
            await sheet.get_by_role('button', name='Record forecast', exact=True).click()
            async with asyncio.timeout(30):
                while True:
                    records = forecasts.list()
                    record = next((item for item in records if item['paired'] == paired), None)
                    if record and record['status'] not in ('requested', 'generating'):
                        assert record['status'] == 'published', record
                        break
                    approve = page.get_by_role('button', name='Approve', exact=True)
                    if await approve.count():
                        await approve.first.click()
                    await asyncio.sleep(.1)
            inspector = page.get_by_role('dialog', name='TEST · Forecast', exact=True)
            await expect(inspector.get_by_text('Original setup · long', exact=True)).to_be_visible()
            await expect(inspector.get_by_role('figure', name='Original setup price map')).to_be_visible()
            await expect(inspector.get_by_text('Stop loss', exact=True)).to_be_visible()
            await inspector.get_by_role('button', name='Inspect candles:D', exact=True).click()
            evidence = inspector.locator('.ca-source pre')
            await expect(evidence).to_be_visible()
            observed_rows = json.loads(await evidence.inner_text())
            assert observed_rows and observed_rows[0] == detail['series']['daily'][0]
            assert charts.document(record['documentId'])['document']['objects'] == [], 'Forecasts must not become editable drawing objects'
            if paired:
                assert set(record['members']) == {'ta', 'directional'}
                assert record['members']['directional']['result']['kind'] == 'directional'
                observations = [charts.observation(member['observationId'], member['sessionKey']) for member in record['members'].values()]
                assert observations[0]['observationId'] != observations[1]['observationId']
                assert observations[0]['resources'] == observations[1]['resources'], 'Paired lanes need matching evidence with isolated session authorization'
            else:
                assert record['trackingScanId'], 'Reviewed price-only tracking must be linked to the saved forecast'
            await inspector.get_by_role('button', name='Close editor', exact=True).click()
        async with asyncio.timeout(15):
            while not any(receipt['status'] == 'rendered' for receipt in receipts):
                await asyncio.sleep(.1)
        await page.get_by_role('tab', name='Forecasts', exact=False).click()
        await page.get_by_role('button', name='Hide TEST forecast overlay', exact=True).first.click()
        if not await page.get_by_role('button', name='Hide TEST forecast overlay', exact=True).count():
            await page.get_by_role('button', name='Show TEST forecast overlay', exact=True).first.click()
        assert len(forecasts.list()) == 2, 'Hiding an overlay must not remove a registered forecast'
        await page.screenshot(path=str(ROOT/'docs/imgs/market-chart-forecasts.png'), animations='disabled')
        assert len(provider.submitted) == 3, 'One single run plus two independent paired lanes'
        assert not {'market.scans.run', 'market.refresh', 'market.interpret', 'market.chart.apply'}.intersection(requests)
        for width in (320, 390):
            await page.set_viewport_size({'width': width, 'height': 900})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}px'
            composer = await page.locator('.ca-composer').bounding_box()
            if composer:
                assert composer['height'] <= 128, composer
        await page.locator('.cf-row-main').first.click()
        await expect(page.get_by_role('dialog', name='TEST · Forecast', exact=True)).to_be_visible()
        for width in (320, 390):
            await page.set_viewport_size({'width': width, 'height': 900})
            figure = page.get_by_role('figure', name='Original setup price map')
            await expect(figure).to_be_visible()
            assert await figure.evaluate('element => element.scrollWidth <= element.clientWidth'), f'Setup map overflows at {width}px'
        await page.screenshot(path=str(ROOT/'docs/imgs/market-chart-forecasts-mobile.png'), animations='disabled')
        await page.get_by_role('dialog', name='TEST · Forecast', exact=True).get_by_role('button', name='Close editor', exact=True).click()
        await page.set_viewport_size({'width': 1600, 'height': 1400})
        # Advance a synthetic cache through the exact same deterministic path used after
        # price scans. The trade stops early, while eight-week direction later succeeds.
        publication = max(datetime.fromisoformat(record['publishedAt']) for record in forecasts.list())
        future = publication + timedelta(days=65)
        schedule = _calendar(now.year, future.year + 1).schedule.loc[publication.date().isoformat():future.date().isoformat()]
        sessions = [(day, row) for day, row in schedule.iterrows() if row['open'].to_pydatetime().replace(tzinfo=timezone.utc) > publication]
        later = [MarketBar(utc_midnight(day.date()), *(120,122,119,121) if index == 0 else (120,121,114,116) if index == 1 else (132,133,131,132), 220000)
                 for index, (day, _) in enumerate(sessions)]
        history = PriceHistory('TEST', history.bars + later, [], [], future.isoformat())
        class FutureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return future if tz else future.replace(tzinfo=None)
        clock_patch = patch('copenet.core.market.forecasts.tracking.datetime', FutureClock)
        clock_patch.start()
        records = evaluate_cached(forecasts, runtime, forecasts.list(), now=future)
        single = next(record for record in records if not record['paired'])
        paired = next(record for record in records if record['paired'])
        assert single['evaluation']['state'] == 'stopped' and single['evaluation']['plannedRiskR'] == -1
        assert paired['evaluation']['state'] == 'ambiguous' and paired['evaluation']['plannedRiskR'] is None
        assert all(record['evaluation']['horizons']['8w']['members']['ta']['outcome'] == 'correct' for record in records)
        report = forecast_report(records)
        assert report['trade']['scoredCount'] == 1 and report['states']['ambiguous'] == 1
        await page.goto('http://127.0.0.1:17124/market?view=ledger', wait_until='networkidle')
        await page.get_by_role('tab', name='Chart forecasts', exact=True).click()
        await expect(page.get_by_text('forecast-fixture', exact=False).first).to_be_visible()
        await page.get_by_role('tab', name='Comparison', exact=True).click()
        await expect(page.get_by_text('Mean planned-risk R -1.00R · 1 scored trades', exact=True)).to_be_visible()
        await page.screenshot(path=str(ROOT/'docs/imgs/market-chart-forecasts-ledger.png'), animations='disabled')
        assert not errors, errors
        assert not rpc_errors, rpc_errors
        assert not acquisitions, acquisitions
        print('PASS: manual single + isolated paired UI requests, real forecast submission harness, immutable setup/evidence inspector, render receipts, Ledger, 320/390px layouts; stopped -1R and ambiguous unscored trades both retain correct eight-week direction. Three scripted model lanes and zero acquisitions; all data synthetic.')
    except Exception:
        print('Page:', await page.locator('body').inner_text())
        print('RPC errors:', rpc_errors)
        print('Browser errors:', errors)
        print('Forecasts:', json.dumps([{'status': row['status'], 'paired': row['paired'],
             'failure': row.get('failureReason'), 'members': {lane: {'status': member['status'], 'errors': member['errors']} for lane, member in row['members'].items()},
             'renderStatus': row['renderStatus']} for row in forecasts.list()]))
        await page.screenshot(path=str(directory/'forecast-failure.png'))
        raise
    finally:
        if clock_patch:
            clock_patch.stop()
        for task in list(tasks):
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        await context.close()


async def main():
    assert (DIST/'index.html').is_file(), 'Build frontend first'
    with TemporaryDirectory(prefix='copenet-forecast-verification-') as directory:
        root = Path(directory)
        with patch.dict('os.environ', {'COPNET_DATA_DIR': str(root), 'COPNET_WORKDIR': str(root), 'COPNET_TELEGRAM_BOT_TOKEN': ''}):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    await verify(browser, root)
                finally:
                    await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
