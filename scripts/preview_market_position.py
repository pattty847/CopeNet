"""Isolated browser preview of the built product with synthetic positions and monitors.

Run after npm run build: uv run python scripts/preview_market_position.py
Open http://127.0.0.1:17125/market/TEST. No credentials, broker reads, or delivery.
This preview accepts read methods only. All numbers are invented fixture values.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from copenet.core.market.models import DashboardPayload, MarketBar
from copenet.core.market.price_history import resample_bars
from copenet.core.market.alert_evaluator import evaluator_catalogue
from copenet.core.market.alert_rules import validate_rule
from copenet.core.market.alert_rehearsal import rehearse_rule
from copenet.core.market.price_cache import PriceHistory

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'src/copenet/host/frontend/dist'
app = FastAPI()
STAMP = '2026-09-14T14:30:00Z'


def candles():
    rows = []
    day = datetime(2025, 1, 2, tzinfo=timezone.utc)
    for index in range(621):
        current = day + timedelta(days=index)
        if current.weekday() >= 5:
            continue
        close = 80 + index * .07 + 8 * math.sin(index / 35)
        opened = close + 1.5 * math.cos(index / 7)
        rows.append(MarketBar(t=int(current.timestamp()), o=opened, h=max(opened, close) + 1.8,
                              l=min(opened, close) - 1.6, c=close, v=200000 + index * 100))
    return rows


def payload(symbol):
    from dataclasses import asdict
    bars = candles()
    return {'symbol': symbol, 'name': 'Synthetic position preview', 'asOf': STAMP,
            'quote': {'price': bars[-1].c, 'changePct': .8, 'comparison': 'previous_daily_bar', 'priceBasis': 'split_adjusted'},
            'series': {grain: [asdict(row) for row in resample_bars(bars, grain)] for grain in ('daily', 'weekly', 'monthly')},
            'verdict': [], 'signals': [], 'evidence': [], 'events': [], 'kill': '', 'intelligence': None}


def position(symbol):
    held = {'symbol': symbol, 'quantity': 25, 'avg_cost': 95.5, 'last_price': 119.2,
            'market_value': 2980, 'unrealized_pl': 592.5, 'unrealized_pl_pct': 24.82,
            'allocation_pct': 6.4, 'price_source': 'webull', 'synced_at': STAMP,
            'currency': 'USD', 'warnings': []} if symbol == 'TEST' else None
    fills = [{'id': f'example-{index}', 'side': side, 'quantity': quantity, 'price': price,
              'filledAt': f'{day}T15:00:00Z', 'sessionDate': day, 'priceSource': 'fill'}
             for index, (day, side, quantity, price) in enumerate([
                 ('2025-06-03', 'BUY', 10, 88.1), ('2025-09-12', 'BUY', 20, 99.2), ('2026-05-05', 'SELL', 5, 114.3)])]
    return {'symbol': symbol, 'position': held, 'syncedAt': STAMP, 'fillsSyncedAt': STAMP,
            'fills': fills if held else [], 'fillCount': len(fills) if held else 0, 'warnings': [],
            'historyNote': 'Synthetic filled-order records at original trade prices. Not historical position valuation.'}


def responses(symbol):
    scan = {'id': 'synthetic-scan', 'revision': 1, 'name': 'Daily review', 'enabled': True,
            'includeUniverse': False, 'symbols': ['TEST'], 'watchlists': [], 'excludeSymbols': [],
            'sources': ['prices'], 'times': ['10:00', '16:15'], 'days': [0, 1, 2, 3, 4], 'timezone': 'America/New_York',
            'publishBrief': False, 'interpret': False, 'resolvedSymbols': ['TEST'], 'contextSymbols': [],
            'nextRunAt': '2026-09-14T20:15:00Z', 'issues': [], 'lastRun': None}
    rule = {'alertId': 'synthetic-monitor', 'revision': 1, 'symbol': 'TEST', 'timeframe': 'weekly',
            'scanId': scan['id'], 'enabled': True, 'oneShot': False, 'direction': 'below',
            'left': {'kind': 'price', 'field': 'low'},
            'right': {'kind': 'indicator', 'indicatorId': 'supertrend', 'config': {'atrPeriod': 10, 'multiplier': 3}, 'output': 'value'},
            'destinationIds': [], 'telegramAuthorized': False, 'includeChart': False, 'includePosition': False,
            'triggerMode': 'interaction', 'confirmation': None, 'status': 'waiting_interaction',
            'lastEvaluatedAt': STAMP, 'lastCandleAt': '2026-09-11T20:00:00Z', 'error': None}
    return {
        'connect': {}, 'market.ticker.get': payload(symbol), 'market.position.get': position(symbol),
        'market.dashboard.get': DashboardPayload.empty(as_of='Synthetic preview').to_wire(),
        'market.watchlist.get': {'items': [], 'lists': ['Synthetic'], 'active': 'Synthetic'},
        'market.brief.get': {'brief': None}, 'market.read.get': {'read': None, 'sessions': []},
        'market.ticker.evidence.get': {'evidence': [], 'events': [], 'warnings': []},
        'market.financial.metrics.list': {'metrics': []}, 'market.alerts.state': {'alerts': [rule], 'events': []},
        'market.alerts.list': {'alerts': [rule] if symbol == 'TEST' else []},
        'market.alerts.catalogue': evaluator_catalogue(),
        'market.scans.get': {'scans': [scan], 'runs': [], 'watchlists': [], 'sources': [], 'nextRunAt': scan['nextRunAt'], 'schedulerEnabled': False},
        'market.notifications.get': {'transportConfigured': False, 'destinations': [], 'deliveries': []},
    }


@app.websocket('/ws')
async def socket(ws: WebSocket):
    await ws.accept()
    await ws.send_json({'type': 'event', 'event': 'connect.challenge', 'payload': {}})
    try:
        while True:
            request = await ws.receive_json()
            params = request.get('params', {})
            items = responses(params.get('symbol', 'TEST'))
            method = request['method']
            if method == 'market.alerts.rehearse':
                rule = validate_rule(params['rule'])
                history = PriceHistory('TEST', candles(), [], [], STAMP)
                items[method] = rehearse_rule(rule, history, now=datetime.fromisoformat(STAMP.replace('Z', '+00:00')))
            ok = method in items
            await ws.send_json({'type': 'res', 'id': request['id'], 'ok': ok,
                               'payload' if ok else 'error': items[method] if ok else {'message': 'Unavailable in isolated preview'}})
    except WebSocketDisconnect:
        pass


@app.get('/{path:path}')
async def static(path: str):
    target = (DIST / path).resolve()
    if not target.is_relative_to(DIST) or not target.is_file():
        target = DIST / 'index.html'
    return FileResponse(target)


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=17125, log_level='warning')
