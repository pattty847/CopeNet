"""Canonical price/indicator alert RPCs; configuration never fetches vendor data."""
from __future__ import annotations

import asyncio
from copenet.core.market.alerts import resolve_alert_store
from copenet.core.market.alert_engine import evaluate_scan_alerts
from copenet.core.market.alert_evaluator import evaluator_catalogue
from copenet.core.market.alert_state import project_alert_state
from copenet.core.market.runtime import resolve_market_runtime
from copenet.core.market.scans.service import resolve_scan_service
from copenet.core.market.scans.resolver import resolve_scope
from copenet.core.messaging.market_delivery import cancel_market_rule_deliveries
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


async def _send(request_id, send_json, payload):
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


def _rules(orchestrator, params):
    runtime = resolve_market_runtime(orchestrator)
    symbol = (params or {}).get('symbol')
    scans = {scan['id']: scan for scan in resolve_scan_service(orchestrator).store.definitions()}
    watchlists = runtime.watchlists.scan_lists()
    return [project_alert_state(rule, scans, watchlists) for rule in resolve_alert_store(runtime).list(symbol=symbol)]


async def handle_market_alerts_list(request_id, params, send_json, orchestrator):
    await _send(request_id, send_json, {'alerts': await asyncio.to_thread(_rules, orchestrator, params)})


async def handle_market_alerts_create(request_id, params, send_json, orchestrator):
    await handle_market_alerts_save(request_id, params, send_json, orchestrator)


async def handle_market_alerts_save(request_id, params, send_json, orchestrator):
    raw = (params or {}).get('rule')
    if not isinstance(raw, dict):
        raise ValueError('rule is required')
    runtime = resolve_market_runtime(orchestrator)
    service = resolve_scan_service(orchestrator)
    scan = service.store.get(raw.get('scanId', 'morning'))
    scope = resolve_scope(scan, runtime.watchlists.scan_lists())
    if scope['issues']:
        raise ValueError('Fix the linked scan first: ' + '; '.join(scope['issues']))
    if 'prices' not in scan['sources'] or str(raw.get('symbol', '')).upper().strip() not in scope['resolvedSymbols']:
        raise ValueError('Add this symbol to a scan with Prices enabled, then link that scan to the alert')
    rule = await asyncio.to_thread(resolve_alert_store(runtime).save, raw)
    if raw.get('alertId'):
        await asyncio.to_thread(cancel_market_rule_deliveries, runtime.store.root_dir, rule.alertId)
    await asyncio.to_thread(evaluate_scan_alerts, runtime, rule.scanId, [rule.symbol], alert_ids=[rule.alertId])
    await _send(request_id, send_json, {'alerts': await asyncio.to_thread(_rules, orchestrator, None)})


async def handle_market_alerts_cancel(request_id, params, send_json, orchestrator):
    alert_id = (params or {}).get('alertId')
    if not isinstance(alert_id, str) or not alert_id:
        raise ValueError('alertId is required')
    runtime = resolve_market_runtime(orchestrator)
    await asyncio.to_thread(resolve_alert_store(runtime).cancel, alert_id)
    await asyncio.to_thread(cancel_market_rule_deliveries, runtime.store.root_dir, alert_id)
    await _send(request_id, send_json, {'alerts': await asyncio.to_thread(_rules, orchestrator, params)})


async def handle_market_alerts_catalogue(request_id, params, send_json, orchestrator):
    await _send(request_id, send_json, await asyncio.to_thread(evaluator_catalogue))


async def handle_market_alerts_state(request_id, params, send_json, orchestrator):
    store = resolve_alert_store(resolve_market_runtime(orchestrator))
    rules, events, catalogue = await asyncio.gather(asyncio.to_thread(_rules, orchestrator, params),
        asyncio.to_thread(store.events), asyncio.to_thread(evaluator_catalogue))
    await _send(request_id, send_json, {'alerts': rules, 'events': events, 'catalogue': catalogue})
