"""Forecast catch-up, concurrent projection integrity, ledger cohorts and host shutdown."""
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from test_market_forecast_runtime import forecast_runtime, finish
from copenet.core.market.forecasts.evaluator import evaluate_forecast
from copenet.core.market.forecasts.tracking import evaluate_cached, on_forecast_prices
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight


def subsequent_history():
    from copenet.core.market.alert_candles import _calendar
    bars = []
    for day in _calendar(2025, 2027).schedule.loc['2026-01-02':'2026-02-27'].index:
        day = day.date()
        values = (100, 132, 98, 130)
        if day == date(2026, 1, 2):
            values = (99, 103, 98, 101)
        elif day == date(2026, 1, 5):
            values = (100, 105, 95, 103)
        elif day == date(2026, 1, 6):
            values = (103, 104, 89, 94)
        bars.append(MarketBar(t=utc_midnight(day), o=values[0], h=values[1], l=values[2], c=values[3], v=1000))
    return PriceHistory('SYN', bars, [], [], '2026-02-28T12:00:00+00:00')


def later_clock(monkeypatch):
    from copenet.core.market.forecasts import tracking
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 2, 28, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(tracking, 'datetime', FixedClock)
    return FixedClock.now()


@pytest.mark.asyncio
async def test_scan_callback_catches_up_only_bound_forecasts_with_exact_idempotent_results(forecast_runtime, monkeypatch):
    orch, provider, _, service, request, _ = forecast_runtime
    record = await finish(service, await service.request(request))
    service.store.set_tracking(record['forecastId'], 'focused-scan')
    service.runtime.prices._write(subsequent_history())
    later_clock(monkeypatch)
    count = len(provider.messages)
    assert await on_forecast_prices(orch, 'other-scan', ['SYN']) == []
    assert await on_forecast_prices(orch, 'focused-scan', ['OTHER']) == []
    output = await on_forecast_prices(orch, 'focused-scan', ['SYN', 'VOO'])
    assert output[0]['state'] == 'stopped' and output[0]['health'] == 'ready'
    record = service.store.get(record['forecastId'])
    assert record['evaluation']['plannedRiskR'] == -1
    assert record['evaluation']['horizons']['8w']['members']['ta']['outcome'] == 'correct'
    assert [event['type'] for event in record['events']] == ['entry', 'stop']
    for event in record['events']:
        proof = service.store.evidence(record['forecastId'], event['evidenceId'])
        assert any(bar['date'] == event['date'] for bar in proof['bars'])
    assert await on_forecast_prices(orch, 'focused-scan', ['SYN']) == output
    assert service.store.get(record['forecastId']) == record
    assert len(provider.messages) == count


@pytest.mark.asyncio
async def test_concurrent_evaluation_retries_current_revision_and_never_rewinds_stop(forecast_runtime, monkeypatch):
    _, _, _, service, request, _ = forecast_runtime
    record = await finish(service, await service.request(request))
    now = later_clock(monkeypatch)
    full = subsequent_history()
    old = replace(full, bars=full.bars[:2], updated_at='2026-01-05T22:00:00+00:00')
    reads = iter([old, full])
    monkeypatch.setattr(service.runtime.prices, 'load', lambda symbol: next(reads))
    original_update = service.store.update_evaluation
    winner = evaluate_forecast(record, full, now)
    raced = False
    def update(identifier, evaluation, evidence, *, expected_revision):
        nonlocal raced
        if not raced:
            raced = True
            original_update(identifier, winner, {'source': winner['source'], 'bars': winner['consumedBars']},
                            expected_revision=expected_revision)
        return original_update(identifier, evaluation, evidence, expected_revision=expected_revision)
    monkeypatch.setattr(service.store, 'update_evaluation', update)
    result = evaluate_cached(service.store, service.runtime, [record], now=now)[0]
    assert raced and result['evaluation']['state'] == 'stopped'
    assert result['evaluation']['plannedRiskR'] == -1
    assert [event['type'] for event in result['events']] == ['entry', 'stop']
    # An old client clock and stale record may observe, but cannot rewrite later results.
    earlier = evaluate_cached(service.store, service.runtime, [record], now=datetime(2026, 1, 5, tzinfo=timezone.utc))[0]
    assert earlier == result


@pytest.mark.asyncio
async def test_ledger_filters_keep_cohorts_dates_and_attempt_counts_explicit(forecast_runtime, monkeypatch):
    _, provider, _, service, request, _ = forecast_runtime
    from copenet.core.market.forecasts.ledger import ledger_forecasts
    record = await finish(service, await service.request(request))
    service.runtime.prices._write(subsequent_history())
    later_clock(monkeypatch)
    count = len(provider.messages)
    report = ledger_forecasts(service, {'forecastProvider': provider.name, 'forecastModel': 'synthetic',
                                         'forecastFrom': '2026-01-03', 'forecastTo': '2026-01-03'})
    assert report['attemptCount'] == 1
    assert report['trade']['meanPlannedRiskR'] == -1
    assert report['direction']['8w']['accuracy'] == 1
    assert report['cohorts'] == {'providers': [provider.name], 'models': ['synthetic']}
    assert ledger_forecasts(service, {'forecastModel': 'different'})['attemptCount'] == 0
    assert ledger_forecasts(service, {'forecastFrom': '2026-01-04'})['attemptCount'] == 0
    with pytest.raises(ValueError, match='ordered'):
        ledger_forecasts(service, {'forecastFrom': '2026-02-01', 'forecastTo': '2026-01-01'})
    with pytest.raises(ValueError):
        ledger_forecasts(service, {'forecastProvider': 7})
    assert len(provider.messages) == count


@pytest.mark.asyncio
async def test_host_shutdown_cancels_hidden_runs_and_preserves_interrupted_attempt(forecast_runtime):
    import asyncio
    orch, provider, _, service, request, _ = forecast_runtime
    provider.block = True
    initial = await service.request({**request, 'paired': True})
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    await asyncio.wait_for(service.shutdown(), timeout=5)
    record = service.store.get(initial['forecastId'])
    assert record['status'] == 'failed'
    assert 'Host stopped' in record['failureReason']
    assert not service.tasks and not orch._active_run_by_session
    count = len(provider.messages)
    await service.request({**request, 'paired': True})
    assert len(provider.messages) == count


@pytest.mark.asyncio
async def test_price_scan_persists_forecast_results_separately_from_alert_events(forecast_runtime, monkeypatch):
    orch, _, _, forecast_service, request, _ = forecast_runtime
    from test_market_scans import Sources
    from copenet.core.market.scans.service import ScanService
    from copenet.core.market import alert_engine
    record = await finish(forecast_service, await forecast_service.request(request))
    forecast_service.runtime.prices._write(subsequent_history())
    later_clock(monkeypatch)
    async def callback(scan_id, symbols):
        return await on_forecast_prices(orch, scan_id, symbols)
    scan_service = ScanService(forecast_service.runtime, sources=Sources(), forecast_prices=callback, pace=0)
    monkeypatch.setattr(scan_service, '_screens', lambda run: None)
    monkeypatch.setattr(alert_engine, 'evaluate_scan_alerts', lambda *args: [])
    scan = scan_service.store.save({'name': 'Synthetic tracker', 'symbols': ['SYN'], 'sources': ['prices']})
    forecast_service.store.set_tracking(record['forecastId'], scan['id'])
    preview = scan_service.preview(scan)
    run = await scan_service.run(scan['id'], expected_scope_token=preview['scopeToken'])
    assert run['forecastResults'][0]['forecastId'] == record['forecastId']
    assert run['forecastResults'][0]['state'] == 'stopped'
    assert run['triggerEvents'] == []
    assert scan_service.store.runs(1)[0]['forecastResults'] == run['forecastResults']
