"""Synthetic manual forecast requests exercise the ordinary harness and frozen evidence."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
import re

import pytest

from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.market.forecasts.store import ForecastStore
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore


class ForecastProvider:
    name = 'forecast-test'
    display_name = 'Synthetic forecast provider'

    def __init__(self):
        self.messages = []
        self.tool_names = []
        self.fail_role = None
        self.block = False
        self.read_first = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def describe(self):
        return {'id': self.name, 'available': True, 'capabilities': {'chat': True, 'streaming': True,
                                                                  'toolCalls': True, 'promptedToolUse': True}}

    async def list_models(self):
        return []

    async def chat_completion(self, *, messages, model, tools=None, tool_choice=None):
        self.messages.append(messages)
        self.tool_names.append([tool['function']['name'] for tool in tools or []])
        self.started.set()
        if self.block:
            await self.release.wait()
        if any(message['role'] == 'tool' and message.get('tool_call_id') == 'submit-forecast' for message in messages):
            return {'model': 'resolved-synthetic', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'Submitted synthetic forecast.'}}]}
        text = '\n'.join(str(message.get('content', '')) for message in messages)
        observation_id = re.search(r'"observationId":"([^"]+)"', text).group(1)
        plain = 'Record one directional forecast' in text
        if self.fail_role == ('directional' if plain else 'ta'):
            raise RuntimeError('Synthetic provider failure')
        result = {'kind': 'directional', 'direction': 'bullish', 'thesis': 'PLAIN_ONLY_SENTINEL'} if plain else {
            'kind': 'setup', 'direction': 'long', 'thesis': 'TA_ONLY_SENTINEL',
            'entry': {'kind': 'limit', 'price': 100}, 'stop': 90,
            'targets': [{'price': 120, 'fraction': 1}],
            'evidence': [{'observationId': observation_id, 'resourceKey': 'candles:D'}]}
        if self.read_first and not any(message['role'] == 'tool' for message in messages):
            return {'model': 'resolved-synthetic', 'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
                'tool_calls': [{'id': 'read-exact', 'type': 'function', 'function': {'name': 'market.chart.read',
                    'arguments': json.dumps({'resourceKey': 'candles:D', 'limit': 1})}}]}}]}
        return {'model': 'resolved-synthetic', 'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': '',
            'tool_calls': [{'id': 'submit-forecast', 'type': 'function', 'function': {
                'name': 'market.forecast.submit', 'arguments': json.dumps({'result': result})}}]}}]}


@pytest.fixture
def forecast_runtime(tmp_path, monkeypatch):
    provider = ForecastProvider()
    orchestrator = Orchestrator(session_store=SessionStore(path=tmp_path / 'index.json'),
                               transcript_store=TranscriptStore(root_dir=tmp_path), sessions_dir=tmp_path,
                               providers={provider.name: provider})
    chart = get_chart_store(orchestrator)
    instrument = {'instrumentId': 'yahoo:SYN', 'symbol': 'SYN', 'assetClass': 'equity', 'source': 'yahoo', 'currency': 'USD'}
    document = chart.workspace('forecast-test', instrument)['document']
    bar = MarketBar(t=utc_midnight(date(2026, 1, 2)), o=99, h=103, l=98, c=101, v=1000)
    history = PriceHistory('SYN', [bar], [], [], '2026-01-02T22:00:00+00:00')
    from copenet.core.market.runtime import resolve_market_runtime
    from copenet.core.market.chart_prices import candle_hash
    from copenet.core.orchestrator import market_forecasts
    from copenet.core.market.forecasts import tracking
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 3, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(market_forecasts, 'datetime', FixedClock)
    monkeypatch.setattr(tracking, 'datetime', FixedClock)
    runtime = resolve_market_runtime(orchestrator)
    runtime.prices._write(history)
    def forbid_fetch(*args, **kwargs):
        raise AssertionError('Manual forecast must not fetch price data')
    monkeypatch.setattr(runtime.prices, 'refresh', forbid_fetch)
    orchestrator._session_store.create_session(session_key='origin', provider=provider.name, model='synthetic')
    rows = [asdict(bar)]
    provenance = {'symbol': 'SYN', 'basis': 'split_adjusted', 'calendar': 'XNYS', 'splits': [], 'splitFingerprint': '',
                  'updatedAt': history.updated_at, 'candleHash': candle_hash(rows), 'completionStatus': 'ready',
                  'completedThrough': bar.t, 'completedCloseAt': '2026-01-02T21:00:00+00:00'}
    capture = {'schemaVersion': 1, 'viewId': 'synthetic-view', 'viewRevision': 1, 'instrument': instrument,
               'timeframe': 'D', 'range': '3M', 'viewport': {'from': bar.t, 'to': bar.t}, 'selection': None,
               'settings': {'includeAccountContext': False}, 'documentId': document['documentId'],
               'documentRevision': 0, 'resources': [{'key': 'candles:D', 'kind': 'candles', 'label': 'Daily',
                   'status': 'loaded', 'rows': rows, 'metadata': {'priceProvenance': provenance}}]}
    observation = chart.capture('origin', 'capture', capture)
    request = {'requestId': 'manual-forecast', 'sessionKey': 'origin', 'observationId': observation['observationId'],
               'documentId': document['documentId'], 'provider': provider.name, 'model': 'synthetic', 'detail': 'balanced'}
    service = market_forecasts.resolve_forecast_service(orchestrator)
    return orchestrator, provider, chart, service, request, capture


async def finish(service, record):
    task = service.tasks.get(record['requestId'])
    if task:
        await asyncio.wait_for(task, timeout=10)
    return service.store.get(record['requestId'])


@pytest.mark.asyncio
async def test_manual_forecast_admits_submits_publishes_once_without_acquisition(forecast_runtime):
    orch, provider, chart, service, request, _ = forecast_runtime
    initial = await service.request(request)
    assert initial['status'] == 'requested'
    record = await finish(service, initial)
    assert record['status'] == 'published', json.dumps(record)
    assert record['members']['ta']['result']['entry']['price'] == 100
    assert record['referenceClose'] == 101
    assert record['publishedAt'] == '2026-01-03T12:00:00+00:00'
    calls = len(provider.messages)
    assert (await service.request(request))['forecastId'] == record['forecastId']
    assert len(provider.messages) == calls
    assert all(set(names) == {'market.chart.context', 'market.chart.read', 'market.forecast.submit', 'market.forecast.read'}
               for names in provider.tool_names)
    assert service.get(record['forecastId'])['evaluation']['state'] == 'waiting_entry'
    assert service.list()[0]['forecastId'] == record['forecastId']
    assert len(provider.messages) == calls
    assert chart.document(record['documentId'])['document']['objects'] == []
    assert not orch.history(session_key='origin')


@pytest.mark.asyncio
async def test_paired_lanes_share_evidence_with_no_history_persona_or_peer_leakage(forecast_runtime, monkeypatch):
    orch, provider, chart, service, request, _ = forecast_runtime
    from copenet.core.persona.service import PersonaPromptContext
    monkeypatch.setattr(orch._persona_service, 'build_prompt_context', lambda **kwargs:
                        PersonaPromptContext('default', 'off', 'PRIVATE_PERSONA_SENTINEL'))
    initial = await service.request({**request, 'paired': True})
    record = await finish(service, initial)
    assert record['status'] == 'published', json.dumps(record)
    assert record['pairComplete']
    members = record['members']
    assert members['ta']['sessionKey'] != members['directional']['sessionKey']
    observations = [chart.observation(member['observationId'], member['sessionKey']) for member in members.values()]
    assert observations[0]['resources'] == observations[1]['resources']
    assert observations[0]['capturedAt'] == observations[1]['capturedAt']
    for messages in provider.messages:
        serialized = json.dumps(messages)
        plain = 'Record one directional forecast' in serialized
        assert 'PRIVATE_PERSONA_SENTINEL' not in serialized
        assert ('TA_ONLY_SENTINEL' if plain else 'PLAIN_ONLY_SENTINEL') not in serialized
    for member in members.values():
        assert orch._session_store.get(member['sessionKey']).persona_privacy_tier == 'off'
        other = members['directional'] if member is members['ta'] else members['ta']
        with pytest.raises(ValueError, match='session'):
            chart.observation(other['observationId'], member['sessionKey'])


@pytest.mark.asyncio
async def test_failed_pair_keeps_valid_member_and_cannot_retry_hidden_call(forecast_runtime):
    _, provider, _, service, request, _ = forecast_runtime
    provider.fail_role = 'directional'
    record = await finish(service, await service.request({**request, 'paired': True}))
    assert record['status'] == 'published', json.dumps(record)
    assert not record['pairComplete']
    assert record['members']['ta']['result']['kind'] == 'setup'
    assert record['members']['directional']['status'] == 'failed'
    count = len(provider.messages)
    await service.request({**request, 'paired': True})
    assert len(provider.messages) == count


@pytest.mark.asyncio
async def test_stop_cancels_every_lane_and_reconnect_never_regenerates(forecast_runtime):
    orch, provider, _, service, request, _ = forecast_runtime
    provider.block = True
    initial = await service.request({**request, 'paired': True})
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    task = service.tasks[initial['requestId']]
    cancelled = service.cancel(initial['requestId'])
    provider.release.set()
    await asyncio.gather(task, return_exceptions=True)
    assert cancelled['status'] == 'cancelled'
    assert not orch._active_run_by_session
    count = len(provider.messages)
    assert (await service.request({**request, 'paired': True}))['status'] == 'cancelled'
    assert len(provider.messages) == count


@pytest.mark.asyncio
async def test_unadmitted_chart_chat_cannot_gain_forecast_tool(forecast_runtime):
    orch, provider, _, service, request, capture = forecast_runtime
    from copenet.core.orchestrator.requests import ChatSendRequest, MarketContextRequest
    events = []
    async def emit(event):
        events.append(event)
    await orch.send_chat(ChatSendRequest(session_key='origin', provider=provider.name, model='synthetic',
        message='Please register a trade', idempotency_key='ordinary-chat',
        market_context=MarketContextRequest(request['observationId'], request['documentId'], capture['viewId'])), emit)
    assert 'market.forecast.submit' not in provider.tool_names[0]
    assert service.store.list() == []
    run = orch._run_store.get('origin', 'ordinary-chat')
    assert any(not step['ok'] for step in run.tool_steps)


@pytest.mark.asyncio
async def test_hidden_lane_cannot_be_retargeted_by_an_ordinary_chat_run(forecast_runtime):
    orch, provider, _, service, request, capture = forecast_runtime
    from copenet.core.orchestrator.requests import ChatSendRequest, MarketContextRequest
    provider.block = True
    initial = await service.request(request)
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    member = service.store.get(initial['requestId'])['members']['ta']
    events = []
    async def emit(event):
        events.append(event)
    with pytest.raises(ValueError, match='another run'):
        await orch.send_chat(ChatSendRequest(session_key=member['sessionKey'], provider=provider.name, model='synthetic',
            message='Change the forecast task', idempotency_key='imitation',
            market_context=MarketContextRequest(member['observationId'], request['documentId'], capture['viewId'])), emit)
    provider.release.set()
    record = await finish(service, initial)
    assert record['status'] == 'published'
    assert not events


@pytest.mark.asyncio
async def test_tracking_scope_token_failure_happens_before_admission_or_provider(forecast_runtime):
    orch, provider, _, service, request, _ = forecast_runtime
    from copenet.core.market.scans.service import resolve_scan_service
    from copenet.core.market.scans.definitions import validate_scan
    scans = resolve_scan_service(orch)
    scan = validate_scan({'name': 'Synthetic forecast prices', 'symbols': ['SYN'], 'sources': ['prices'],
                          'includeUniverse': False, 'publishBrief': False, 'interpret': False})
    proposal = {'scan': scan, 'scopeToken': 'stale-token'}
    with pytest.raises(ValueError, match='preview'):
        await service.request(request, tracking=proposal)
    assert not service.store.list()
    assert not provider.messages


@pytest.mark.asyncio
@pytest.mark.parametrize('decision', ['approved', 'rejected'])
async def test_external_chart_text_keeps_exact_forecast_approval_gate(forecast_runtime, decision):
    orch, provider, chart, service, request, capture = forecast_runtime
    from copenet.core.tools.barricade import reset_session_security
    for lane in ('ta', 'directional'):
        reset_session_security(f"forecast-{request['requestId']}-lane-{lane}")
    capture['resources'].append({'key': 'panel:research', 'kind': 'panel', 'label': 'Research', 'status': 'loaded',
                                 'rows': [{'text': 'Synthetic external research excerpt'}], 'metadata': {}})
    observation = chart.capture('origin', 'with-external-text', capture)
    request = {**request, 'observationId': observation['observationId']}
    approvals = []
    async def decide(name, payload):
        if name == 'approval.pending':
            approval = payload['approval']
            approvals.append(approval)
            orch.decide_approval(approval_id=approval['approvalId'], decision=decision)
    service.emit_event = decide
    record = await finish(service, await service.request(request))
    assert len(approvals) == 1
    assert approvals[0]['proposedAction']['payload']['result']['entry']['price'] == 100
    assert record['status'] == ('published' if decision == 'approved' else 'failed')
    for lane in ('ta', 'directional'):
        reset_session_security(f"forecast-{request['requestId']}-lane-{lane}")


@pytest.mark.asyncio
async def test_host_restart_retains_interrupted_attempt_without_redispatch(forecast_runtime):
    orch, provider, chart, service, request, _ = forecast_runtime
    from copenet.core.orchestrator.market_forecasts import ForecastService
    observation = chart.observation(request['observationId'], request['sessionKey'])
    service.store.admit({**request, 'instrument': observation['instrument']})
    restarted = ForecastService(orch)
    record = await restarted.request(request)
    assert record['status'] == 'failed'
    assert 'not retried' in record['failureReason']
    assert not restarted.tasks and not provider.messages


@pytest.mark.asyncio
async def test_invalid_captured_revision_blocks_before_any_model_cost(forecast_runtime):
    _, provider, chart, service, request, capture = forecast_runtime
    capture['resources'][0]['rows'][0]['c'] = 999
    observation = chart.capture('origin', 'changed-candle', capture)
    with pytest.raises(ValueError, match='revision'):
        await service.request({**request, 'observationId': observation['observationId']})
    assert not service.store.list()
    assert not provider.messages


@pytest.mark.asyncio
async def test_forecast_attribution_freezes_reported_model_reads_and_comparable_input_hash(forecast_runtime):
    _, provider, _, service, request, _ = forecast_runtime
    provider.read_first = True
    record = await finish(service, await service.request({**request, 'paired': True}))
    assert record['status'] == 'published', json.dumps(record)
    ta = record['members']['ta']['attribution']
    plain = record['members']['directional']['attribution']
    assert ta['evidenceManifestHash'] == plain['evidenceManifestHash']
    assert ta['initialPresentationHash'] != plain['initialPresentationHash']
    assert ta['promptHash'] != plain['promptHash']
    assert ta['promptVersion'] == plain['promptVersion'] == 'chart-forecast-1'
    assert ta['requestedModel'] == 'synthetic'
    assert ta['model'] == 'resolved-synthetic' and ta['modelSource'] == 'run_record'
    assert ta['reportedUsage'] is None and ta['usageStatus'] == 'unavailable'
    assert ta['readCallCount'] == plain['readCallCount'] == 1
    assert ta['reads'][0]['arguments'] == {'resourceKey': 'candles:D', 'limit': 1}
    assert record['evidenceCutoff'] == '2026-01-02T21:00:00+00:00'
    assert record['publicationEvidence']['completedThrough'] == 1767312000
    with pytest.raises(ValueError, match='immutable'):
        service.store.set_attribution(record['forecastId'], 'ta', {'model': 'different-model'})
