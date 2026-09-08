"""Admission/publication validates the captured revision against local cache only."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json

from ..alert_candles import completed_candles
from ..alert_rules import supported_symbol
from ..chart_prices import candle_hash
from ..price_history import split_fingerprint


def publication_evidence(chart_store, record: dict, runtime, now: datetime) -> dict:
    observation = chart_store.observation(record['observationId'], record['sessionKey'])
    instrument = observation['instrument']
    symbol = instrument['symbol']
    if instrument['assetClass'] not in {'equity', 'etf'} or not supported_symbol(symbol):
        raise ValueError('Forecasts currently require a US-listed equity or ETF with supported exchange sessions')
    if observation['settings'].get('comparisonMode') or observation['settings'].get('includeAccountContext'):
        raise ValueError('Use a single-price chart with account context excluded to register a forecast')
    with chart_store.connect() as db:
        row = db.execute('SELECT r.body FROM resources r JOIN observation_resources o ON r.id=o.resource_id '
                         'WHERE o.observation_id=? AND o.resource_key=?', (record['observationId'], 'candles:D')).fetchone()
    if row is None:
        raise ValueError('Capture daily candle evidence before registering a forecast')
    resource = json.loads(row['body'])
    provenance = resource['metadata'].get('priceProvenance')
    if resource['status'] != 'loaded' or not provenance:
        raise ValueError('Refresh the chart to capture loaded candles with cache completion provenance')
    if provenance.get('basis') != 'split_adjusted' or provenance.get('calendar') != 'XNYS' or provenance.get('symbol') != symbol:
        raise ValueError('Captured candles have an unsupported price basis or exchange calendar')
    if provenance.get('completionStatus') != 'ready' or provenance.get('candleHash') != candle_hash(resource['rows']):
        raise ValueError('Captured candle revision is stale or differs from its provenance; refresh the chart')
    history = runtime.prices.load(symbol)
    if history is None:
        raise ValueError('Cached daily history is unavailable; refresh the chart before forecasting')
    if provenance.get('splitFingerprint') != split_fingerprint(history.splits) or provenance.get('splits') != [list(action) for action in history.splits]:
        raise ValueError('The split history changed after capture; refresh the chart before forecasting')
    completed = completed_candles(history, 'daily', now)
    if completed.status != 'ready':
        raise ValueError(completed.error or 'The latest completed daily candle is not available; refresh the chart')
    latest = completed.bars[-1]
    if provenance.get('completedThrough') != latest.t:
        raise ValueError('A newer daily session completed after capture; capture the chart again')
    captured = [row for row in resource['rows'] if row['t'] <= latest.t]
    by_time = {bar.t: asdict(bar) for bar in completed.bars}
    if not captured or captured[-1]['t'] != latest.t or any(row != by_time.get(row['t']) for row in captured):
        raise ValueError('Captured completed candles differ from the cached revision; refresh the chart')
    return {'provenance': provenance, 'referenceClose': captured[-1]['c'],
            'evidenceCutoff': completed.close_times[latest.t],
            'evidence': {'observationId': record['observationId'], 'resourceKey': 'candles:D',
                         'completedRowsHash': candle_hash(captured), 'completedThrough': latest.t}}
