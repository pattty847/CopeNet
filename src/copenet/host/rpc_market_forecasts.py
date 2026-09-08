"""Typed operator forecast requests; no chat prose confers registration authority."""
from __future__ import annotations

import asyncio
from typing import Literal
from pydantic import Field

from copenet.core.market.chart_workspace.models import Contract
from copenet.core.market.forecasts.models import Identifier
from copenet.core.market.forecasts.chart import forecast_chart
from copenet.core.market.forecasts.tracking import validate_tracking
from copenet.core.market.scans.service import resolve_scan_service
from copenet.core.orchestrator.market_forecasts import resolve_forecast_service
from .rpc_schema import ResponseFrame, make_response_frame


class TrackingProposal(Contract):
    scan: dict
    scopeToken: str = Field(min_length=64, max_length=64)


class Start(Contract):
    requestId: Identifier
    sessionKey: Identifier
    observationId: Identifier
    documentId: Identifier
    provider: Identifier
    model: Identifier
    detail: Literal['quick', 'balanced', 'deep'] = 'balanced'
    paired: bool = False
    entryExpirySessions: int = Field(default=10, ge=1, le=40)
    trackingScanId: Identifier | None = None
    tracking: TrackingProposal | None = None


class Get(Contract):
    forecastId: Identifier
    evidenceId: Identifier | None = None
    includeChart: bool = False


class ForecastId(Contract):
    forecastId: Identifier


class List(Contract):
    documentId: Identifier | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class Amendment(Contract):
    amendmentId: Identifier
    changes: dict
    rationale: str = Field(min_length=1, max_length=4000)


class Amend(ForecastId):
    expectedRevision: int = Field(ge=0)
    amendment: Amendment


class Tracking(ForecastId):
    scanId: Identifier | None


class Rendered(ForecastId):
    viewId: Identifier
    revision: int = Field(ge=0)
    status: Literal['rendered', 'hidden', 'failed']
    reason: str | None = Field(default=None, max_length=2000)


async def _reply(identifier, send, payload):
    await send(make_response_frame(ResponseFrame(id=identifier, ok=True, payload=payload)))


async def request_forecast(identifier, params, send, orchestrator, *, broadcast=None):
    args = Start.model_validate(params or {})
    raw = args.model_dump(exclude={'tracking'})
    service = resolve_forecast_service(orchestrator)
    async def emit_event(event, payload):
        await (broadcast or send)({'type': 'event', 'event': event, 'payload': payload})
    service.emit_event = emit_event
    forecast = await service.request(
        raw, tracking=args.tracking.model_dump() if args.tracking else None)
    await _reply(identifier, send, {'forecast': forecast})


async def get_forecast(identifier, params, send, orchestrator):
    args = Get.model_validate(params or {})
    service = resolve_forecast_service(orchestrator)
    if args.evidenceId:
        await _reply(identifier, send, {'evidence': service.store.evidence(args.forecastId, args.evidenceId)})
    else:
        record = await asyncio.to_thread(service.get, args.forecastId)
        payload = {'forecast': record}
        if args.includeChart:
            payload['chart'] = await asyncio.to_thread(forecast_chart, service.charts, record)
        await _reply(identifier, send, payload)


async def list_forecasts(identifier, params, send, orchestrator):
    args = List.model_validate(params or {})
    service = resolve_forecast_service(orchestrator)
    records = await asyncio.to_thread(service.list, document_id=args.documentId, symbol=args.symbol,
                                      limit=args.limit, offset=args.offset)
    await _reply(identifier, send, {'forecasts': records, 'offset': args.offset,
                                  'nextOffset': args.offset + len(records) if len(records) == args.limit else None})


async def cancel_forecast(identifier, params, send, orchestrator):
    args = ForecastId.model_validate(params or {})
    await _reply(identifier, send, {'forecast': resolve_forecast_service(orchestrator).cancel(args.forecastId)})


async def amend_forecast(identifier, params, send, orchestrator):
    args = Amend.model_validate(params or {})
    amendment = args.amendment
    store = resolve_forecast_service(orchestrator).store
    record = store.amend(args.forecastId, amendment.amendmentId, amendment.changes, amendment.rationale,
                         {'kind': 'operator'}, expected_revision=args.expectedRevision)
    await _reply(identifier, send, {'forecast': record})


async def update_tracking(identifier, params, send, orchestrator):
    args = Tracking.model_validate(params or {})
    service = resolve_forecast_service(orchestrator)
    record = service.store.get(args.forecastId)
    validate_tracking(resolve_scan_service(orchestrator), record['instrument']['symbol'], scan_id=args.scanId)
    await _reply(identifier, send, {'forecast': service.store.set_tracking(args.forecastId, args.scanId)})


async def rendered_forecast(identifier, params, send, orchestrator):
    args = Rendered.model_validate(params or {})
    record = resolve_forecast_service(orchestrator).store.rendered(args.forecastId, args.model_dump(exclude={'forecastId'}, exclude_none=True))
    await _reply(identifier, send, {'forecast': record})


MARKET_FORECAST_HANDLERS = {
    'market.forecast.request': request_forecast, 'market.forecast.get': get_forecast,
    'market.forecast.list': list_forecasts, 'market.forecast.cancel': cancel_forecast,
    'market.forecast.amend': amend_forecast, 'market.forecast.tracking.update': update_tracking,
    'market.forecast.rendered': rendered_forecast,
}
