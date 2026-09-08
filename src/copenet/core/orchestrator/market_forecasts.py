"""Manual forecast lifecycle over isolated ordinary harness runs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from copenet.core.coordination.lane_runner import LaneTurnSpec, create_lane_sessions, run_lane_turn
from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.market.forecasts.models import ForecastRequest
from copenet.core.market.forecasts.attribution import input_attribution, run_attribution
from copenet.core.market.forecasts.store import ForecastStore
from copenet.core.market.forecasts.evidence import publication_evidence
from copenet.core.market.forecasts.tracking import all_forecasts, evaluate_cached, validate_tracking
from copenet.core.market.runtime import resolve_market_runtime
from .requests import MarketContextRequest


def forecast_prompt(record, lane):
    shared = (f"Record one {lane} forecast for {record['instrument']['symbol']} from this frozen chart. "
              f"Forecast horizon is 56 calendar days from publication; score direction at 28 and 56 days. "
              f"Entry expires after {record['entryExpirySessions']} eligible exchange sessions. "
              "Read exact captured candles/indicators as needed. Use market.forecast.submit once and then briefly explain. "
              "This is a prospective paper experiment, with no real order placement. ")
    if lane == 'directional':
        return shared + ("Submit kind=directional with direction bullish, bearish, neutral or abstain and a thesis. "
                         "Give a plain directional assessment. Do not design an entry, protective stop, or profit targets. "
                         "Abstain when the evidence cannot support a call.")
    return shared + ("Submit kind=setup with direction long/short, a technical thesis, entry {kind:limit/stop,price}, "
                     "protective stop, 1–3 ordered targets {price,fraction} summing to 1, optional explanatory zones "
                     "{label,lower,upper}, and captured evidence references. Prices must match the captured split-only basis. "
                     "Use kind=no_setup and thesis when no defensible setup exists. Do not force a trade. "
                     "Simulation begins at the first exchange open strictly after publication. Intrabar sequencing that "
                     "changes the outcome is ambiguous; target fractions are of the original unit, stop stays fixed, "
                     "remaining position exits at the horizon. Gross planned-risk R excludes execution costs.")


class ForecastService:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.charts = get_chart_store(orchestrator)
        self.store = ForecastStore(self.charts)
        self.runtime = resolve_market_runtime(orchestrator)
        self.tasks: dict[str, asyncio.Task] = {}
        self.emit_event = None
        # A prior host may have stopped after a provider side effect. Never auto-rerun it.
        for record in all_forecasts(self.store):
            if record['status'] in ('requested', 'generating'):
                self.store.fail(record['requestId'], 'Host stopped before publication; request was not retried')

    async def request(self, raw, *, tracking=None):
        observation = self.charts.observation(raw['observationId'], raw['sessionKey'])
        request = ForecastRequest.model_validate({**raw, 'instrument': observation['instrument']}).model_dump()
        # Idempotency check precedes freshness and tracking mutations.
        try:
            existing = self.store.get(request['requestId'])
        except ValueError:
            existing = None
        if existing:
            return self.store.admit(request)
        parent = self.orchestrator._session_store.get(request['sessionKey'])
        if parent is None or parent.archived or parent.session_type == 'forecast_lane':
            raise ValueError('Select an active chart session before recording a forecast')
        if parent.in_flight_run_id:
            raise ValueError('Wait for the current chart answer before recording a forecast')
        if request['provider'] not in self.orchestrator._providers:
            raise ValueError('The selected forecast provider is unavailable')
        from copenet.core.market.scans.service import resolve_scan_service
        scans = resolve_scan_service(self.orchestrator)
        scan = validate_tracking(scans, request['instrument']['symbol'],
                                 scan_id=request['trackingScanId'], proposal=tracking)
        # Validate before model cost. Publication repeats this against the same captured rows.
        publication_evidence(self.charts, {**request, 'timeframe': observation['timeframe']},
                             self.runtime, datetime.now(timezone.utc))
        record = self.store.admit(request)
        try:
            if tracking:
                saved = scans.store.save(scan)
                record = self.store.set_tracking(request['requestId'], saved['id'])
            task = asyncio.create_task(self._run(record), name=f"forecast-{request['requestId']}")
            self.tasks[request['requestId']] = task
            task.add_done_callback(lambda _: self.tasks.pop(request['requestId'], None))
            background = getattr(self.orchestrator, '_background_tasks', None)
            if background is not None:
                background.add(task)
                task.add_done_callback(background.discard)
        except Exception as exc:
            self.store.fail(request['requestId'], str(exc))
            raise
        return record

    async def _run(self, record):
        identifier = record['requestId']
        try:
            names = ('ta', 'directional') if record['paired'] else ('ta',)
            participants = create_lane_sessions(
                self.orchestrator, parent_key=f"forecast-{identifier}", session_type='forecast_lane',
                title_prefix=f"{record['instrument']['symbol']} forecast",
                participant_specs={name: {'provider': record['provider'], 'model': record['model'], 'personaPrivacyTier': 'off'} for name in names},
                workspace_root=None,
            )
            specs = []
            for lane, participant in participants.items():
                session_key = participant['laneSessionKey']
                observation = self.store.clone_observation(identifier, lane, session_key)
                self.store.bind_lane(identifier, lane, session_key, f'forecast-{identifier}-{lane}', observation['observationId'],
                                     {'provider': record['provider'], 'model': record['model'], 'detail': record['detail']})
                specs.append((lane, LaneTurnSpec(
                    session_key=session_key, provider=record['provider'], model=record['model'],
                    prompt=forecast_prompt(record, lane), persona_privacy_tier='off', emit_event=self.emit_event,
                    idempotency_key=f"forecast-{identifier}-{lane}",
                    market_context=MarketContextRequest(observation_id=observation['observationId'],
                        document_id=record['documentId'], view_id=observation['viewId'], detail=record['detail'], access='read'),
                )))
            await asyncio.gather(*(self._lane(identifier, lane, spec) for lane, spec in specs))
            record = self.store.get(identifier)
            if record['status'] == 'cancelled':
                return
            published = datetime.now(timezone.utc)
            proof = publication_evidence(self.charts, record, self.runtime, published)
            self.store.publish(identifier, published_at=published.isoformat(),
                               reference_close=proof['referenceClose'], provenance=proof['provenance'],
                               evidence_cutoff=proof['evidenceCutoff'], evidence=proof['evidence'])
            evaluate_cached(self.store, self.runtime, [self.store.get(identifier)])
        except asyncio.CancelledError:
            self._abort_lanes(identifier)
            self.store.cancel(identifier)
            raise
        except Exception as exc:
            self.store.fail(identifier, str(exc))
        finally:
            await self.notify(identifier)

    async def notify(self, identifier):
        if self.emit_event:
            try:
                record = self.store.get(identifier)
                await self.emit_event('market.forecast.updated', {'forecastId': identifier, 'revision': record['revision']})
            except Exception:
                pass  # A disconnected observer does not change durable forecast outcomes.

    async def _lane(self, identifier, lane, spec):
        try:
            self.store.set_attribution(identifier, lane, input_attribution(self.charts, self.store.get(identifier), lane, spec.prompt))
            await run_lane_turn(self.orchestrator, spec)
            member = self.store.get(identifier)['members'][lane]
            if not member.get('result'):
                self.store.lane_failed(identifier, lane, 'Model finished without a valid forecast submission')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.store.lane_failed(identifier, lane, str(exc))
        finally:
            run = self.orchestrator._run_store.get(spec.session_key, spec.idempotency_key)
            self.store.set_attribution(identifier, lane, run_attribution(run))

    def _abort_lanes(self, identifier):
        for member in self.store.get(identifier)['members'].values():
            self.orchestrator.abort(member['sessionKey'], member['runId'])

    def cancel(self, identifier):
        record = self.store.cancel(identifier)
        self._abort_lanes(identifier)
        if task := self.tasks.get(identifier):
            task.cancel()
        return record

    async def shutdown(self):
        tasks = list(self.tasks.items())
        for identifier, task in tasks:
            self.store.fail(identifier, 'Host stopped during generation; forecast was not retried')
            self._abort_lanes(identifier)
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

    def get(self, identifier):
        return self._tracking(evaluate_cached(self.store, self.runtime, [self.store.get(identifier)]))[0]

    def list(self, *, document_id=None, symbol=None, limit=100, offset=0):
        return self._tracking(evaluate_cached(self.store, self.runtime, self.store.list(document_id, symbol, limit, offset)))

    def _tracking(self, records):
        from copenet.core.market.scans.service import resolve_scan_service
        from copenet.core.market.forecasts.tracking import tracking_state
        scans = resolve_scan_service(self.orchestrator)
        return [tracking_state(scans, record) for record in records]


def resolve_forecast_service(orchestrator):
    service = getattr(orchestrator, '_market_forecast_service', None)
    if service is None:
        service = ForecastService(orchestrator)
        orchestrator._market_forecast_service = service
    return service
