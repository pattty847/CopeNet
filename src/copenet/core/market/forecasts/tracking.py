"""Explicit focused scan admission and cached-only forecast evaluation."""
from __future__ import annotations

from datetime import datetime, timezone

from .evaluator import evaluate_forecast
from .store import ForecastRevisionConflict


def validate_tracking(service, symbol, *, scan_id=None, proposal=None):
    if scan_id and proposal:
        raise ValueError('Choose an existing tracking scan or a reviewed proposal')
    if not scan_id and proposal is None:
        return None
    from ..scans.definitions import validate_scan
    scan = service.store.get(scan_id) if scan_id else validate_scan(proposal['scan'])
    plan = service.preview(scan)
    if (scan['includeUniverse'] or scan['watchlists'] or scan['sources'] != ['prices']
            or scan['publishBrief'] or scan['interpret'] or symbol not in plan['resolvedSymbols']):
        raise ValueError('Forecast tracking needs an explicit, price-only scan containing this ticker')
    if plan['issues']:
        raise ValueError('; '.join(plan['issues']))
    if proposal is not None and proposal['scopeToken'] != plan['scopeToken']:
        raise ValueError('Tracking scan changed after preview; review its current scope')
    return scan


def all_forecasts(store):
    offset = 0
    while True:
        batch = store.list(limit=500, offset=offset)
        yield from batch
        if len(batch) < 500:
            return
        offset += len(batch)


def tracking_state(service, record):
    from ..scans.definitions import next_run_at
    from ..sentinel import sentinel_enabled
    if not record['trackingScanId']:
        return {**record, 'tracking': {'status': 'paused', 'nextRunAt': None}}
    try:
        scan = service.store.get(record['trackingScanId'])
        validate_tracking(service, record['instrument']['symbol'], scan_id=scan['id'])
    except ValueError:
        return {**record, 'tracking': {'status': 'unavailable', 'nextRunAt': None}}
    status = 'paused' if not scan['enabled'] else 'scheduled' if sentinel_enabled() else 'host_disabled'
    upcoming = next_run_at(scan, datetime.now(timezone.utc)) if status == 'scheduled' else None
    return {**record, 'tracking': {'status': status, 'nextRunAt': upcoming.isoformat() if upcoming else None}}


def _evaluate_one(store, runtime, identifier, now):
    for _ in range(3):
        # Both the prior projection and cache are reloaded after a concurrent write.
        record = store.get(identifier)
        if not record['publishedAt']:
            return record
        previous = record.get('evaluation') or {}
        if previous.get('evaluatedAt') and datetime.fromisoformat(previous['evaluatedAt']) > now:
            return record
        symbol = record['instrument']['symbol']
        history = runtime.prices.load(symbol)
        if history is None:
            evaluation = {**previous, 'health': 'missing_history',
                          'reason': 'Cached price history is unavailable; original outcomes retained',
                          'state': previous.get('state', 'waiting_entry'), 'evaluatedAt': now.isoformat()}
            evidence = {'symbol': symbol, 'missingHistory': True}
        else:
            evaluation = evaluate_forecast(record, history, now)
            evidence = {'source': evaluation['source'], 'bars': evaluation['consumedBars']}
        if {k: v for k, v in evaluation.items() if k != 'evaluatedAt'} == {k: v for k, v in previous.items() if k != 'evaluatedAt'}:
            return store.get(identifier)
        try:
            return store.update_evaluation(identifier, evaluation, evidence, expected_revision=record['revision'])
        except ForecastRevisionConflict:
            continue
    # Contention must never let an older computation replace a later proven outcome.
    return store.get(identifier)


def evaluate_cached(store, runtime, records, *, now=None):
    now = now or datetime.now(timezone.utc)
    return [_evaluate_one(store, runtime, record['forecastId'], now) for record in records]


async def on_forecast_prices(orchestrator, scan_id, symbols):
    import asyncio
    from copenet.core.orchestrator.market_forecasts import resolve_forecast_service
    service = resolve_forecast_service(orchestrator)
    records = [r for r in all_forecasts(service.store)
               if r['trackingScanId'] == scan_id and r['instrument']['symbol'] in symbols]
    evaluated = await asyncio.to_thread(evaluate_cached, service.store, service.runtime, records)
    return [{'forecastId': record['forecastId'], 'revision': record['revision'],
             'state': (record.get('evaluation') or {}).get('state'),
             'health': (record.get('evaluation') or {}).get('health')} for record in evaluated]
