from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest

from copenet.core.market.alerts import AlertStore, delivery_rule_active
from copenet.core.market.alert_engine import evaluate_scan_alerts
from copenet.core.market.alert_candles import completed_candles
from copenet.core.market.alert_evaluator import evaluator_request
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def history(rows, fetched):
    return PriceHistory('TEST', [MarketBar(utc_midnight(datetime.fromisoformat(day).date()), value, value, value, value, 100) for day, value in rows], [], [], fetched)


def rule(**extra):
    return {'symbol': 'TEST', 'timeframe': 'daily', 'scanId': 'morning', 'direction': 'above',
        'left': {'kind': 'price'}, 'right': {'kind': 'constant', 'value': 105}, **extra}


def runtime(tmp_path, current):
    return SimpleNamespace(store=SimpleNamespace(root_dir=tmp_path), prices=SimpleNamespace(load=lambda symbol: current[0]))


def test_crossing_baselines_then_triggers_once_without_fetching(tmp_path):
    store = AlertStore(tmp_path)
    saved = store.save(rule())
    current = [history([('2026-01-05', 100)], '2026-01-05T22:00:00+00:00')]
    host = runtime(tmp_path, current)
    assert evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp('2026-01-05T22:00:00')) == []
    current[0] = history([('2026-01-05', 100), ('2026-01-06', 110)], '2026-01-06T22:00:00+00:00')
    events = evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp('2026-01-06T22:00:00'))
    assert events[0]['leftValue'] == 110
    assert events[0]['alertId'] == saved.alertId
    assert AlertStore(tmp_path).list()[0].status == 'triggered'
    assert delivery_rule_active(tmp_path, saved.alertId, 1)
    assert evaluate_scan_alerts(runtime(tmp_path, current), 'morning', ['TEST'], now=stamp('2026-01-06T22:00:00')) == []
    assert len(store.events()) == 1


def test_repeating_rule_requires_new_crossing(tmp_path):
    store = AlertStore(tmp_path)
    store.save(rule(oneShot=False))
    current = [None]
    host = runtime(tmp_path, current)
    rows, events = [], []
    for day, value in [(5, 100), (6, 110), (7, 115), (8, 99), (9, 108)]:
        rows.append((f'2026-01-{day:02d}', value))
        current[0] = history(rows, f'2026-01-{day:02d}T22:00:00+00:00')
        events += evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
    assert len(events) == 2
    assert len({event['eventId'] for event in events}) == 2


@pytest.mark.parametrize(('direction', 'values'), [('above', [100, 105, 110]), ('below', [110, 105, 100])])
def test_constant_threshold_touch_is_not_crossing_but_leaving_equality_is(tmp_path, direction, values):
    AlertStore(tmp_path).save(rule(direction=direction, oneShot=False))
    current = [None]
    host = runtime(tmp_path, current)
    rows = []
    for day, value in zip([5, 6, 7], values):
        rows.append((f'2026-01-{day:02d}', value))
        current[0] = history(rows, f'2026-01-{day:02d}T22:00:00+00:00')
        emitted = evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
        assert len(emitted) == (1 if day == 7 else 0)


@pytest.mark.parametrize(('direction', 'values'), [('above', [100, 100, 110]), ('below', [100, 100, 90])])
def test_indicator_output_crosses_from_equal_computed_operands(tmp_path, direction, values):
    # SMA(1) vs SMA(2) supplies two changing outputs rather than a fixed threshold.
    AlertStore(tmp_path).save(rule(direction=direction, oneShot=False,
        left={'kind': 'indicator', 'indicatorId': 'sma', 'config': {'period': 1}, 'output': 'value'},
        right={'kind': 'indicator', 'indicatorId': 'sma', 'config': {'period': 2}, 'output': 'value'}))
    current = [None]
    host = runtime(tmp_path, current)
    rows = []
    for day, value in zip([5, 6, 7], values):
        rows.append((f'2026-01-{day:02d}', value))
        current[0] = history(rows, f'2026-01-{day:02d}T22:00:00+00:00')
        emitted = evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
        assert len(emitted) == (1 if day == 7 else 0)


@pytest.mark.parametrize('change', ['split', 'revision', 'missed'])
def test_changed_history_or_missing_observation_rebaselines_without_trigger(tmp_path, change):
    AlertStore(tmp_path).save(rule())
    current = [history([('2026-01-05', 100)], '2026-01-05T22:00:00+00:00')]
    host = runtime(tmp_path, current)
    evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
    rows = [('2026-01-05', 99 if change == 'revision' else 100), ('2026-01-06', 110)]
    if change == 'missed': rows.append(('2026-01-07', 120))
    current[0] = history(rows, rows[-1][0] + 'T22:00:00+00:00')
    if change == 'split': current[0] = replace(current[0], splits=[('2026-01-06', 2)])
    assert evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at)) == []
    assert AlertStore(tmp_path).list()[0].status == 'rebaselined'


def test_forming_and_preclose_cached_candles_never_complete_later():
    data = history([('2026-01-05', 100), ('2026-01-06', 110)], '2026-01-06T14:45:00+00:00')
    morning = completed_candles(data, 'daily', stamp('2026-01-06T14:45:00'))
    assert morning.status == 'ready' and morning.bars[-1].c == 100
    evening = completed_candles(data, 'daily', stamp('2026-01-06T22:00:00'))
    assert evening.status == 'stale'


def test_holiday_week_ends_thursday_and_early_close_is_respected():
    data = history([(f'2026-04-{day:02d}', 100) for day in [1, 2]], '2026-04-02T21:00:00+00:00')
    # Include Monday/Tuesday so the full holiday week is present.
    data = replace(data, bars=history([('2026-03-30', 100), ('2026-03-31', 100)], data.updated_at).bars + data.bars)
    result = completed_candles(data, 'weekly', stamp('2026-04-02T21:00:00'))
    assert result.status == 'ready'
    assert result.close_times[result.bars[-1].t] == '2026-04-02T20:00:00+00:00'
    early = history([('2026-11-27', 100)], '2026-11-27T18:01:00+00:00')
    result = completed_candles(early, 'daily', stamp(early.updated_at))
    assert result.status == 'ready' and result.close_times[result.bars[-1].t].endswith('18:00:00+00:00')


def test_monthly_period_requires_all_sessions_and_final_close():
    from copenet.core.market.alert_candles import _calendar
    sessions = _calendar(2025, 2027).sessions_in_range('2026-01-01', '2026-01-31')
    rows = [(session.date().isoformat(), 100) for session in sessions]
    data = history(rows, '2026-01-30T22:00:00+00:00')
    result = completed_candles(data, 'monthly', stamp(data.updated_at))
    assert result.status == 'ready'
    assert len(result.bars) == 1
    assert completed_candles(replace(data, bars=data.bars[:-1]), 'monthly', stamp(data.updated_at)).status == 'data_gap'


def test_partial_initial_period_seeds_same_chart_math_but_cannot_trigger():
    from copenet.core.market.price_history import resample_bars
    rows = [('2026-01-07', 100), ('2026-01-08', 102), ('2026-01-09', 101)]
    data = history(rows, '2026-01-09T22:00:00+00:00')
    result = completed_candles(data, 'weekly', stamp(data.updated_at))
    assert result.status == 'warming_up'
    rows += [(f'2026-01-{day}', 110 + day) for day in range(12, 17)]
    data = history(rows, '2026-01-16T22:00:00+00:00')
    result = completed_candles(data, 'weekly', stamp(data.updated_at))
    assert result.status == 'ready'
    assert result.bars == resample_bars(data.bars, 'weekly')


def test_old_price_rules_migrate_once_without_trusting_intraday_reference(tmp_path):
    root = tmp_path / 'alerts'; root.mkdir()
    (root / 'rules.json').write_text(json.dumps({'alerts': [{'alert_id': 'prior', 'symbol': 'TEST', 'status': 'active', 'direction': 'above', 'threshold': 105, 'created_at': '2026-01-01T00:00:00+00:00'}]}))
    saved = AlertStore(tmp_path).list()[0]
    assert saved.status == 'baseline_pending' and saved.baseline is None
    assert json.loads((root / 'rules.json').read_text())['version'] == 2
    assert AlertStore(tmp_path).list()[0] == saved


def test_migrated_crypto_rule_is_paused_instead_of_using_equity_sessions():
    from copenet.core.market.alert_rules import migrate_price_rule
    migrated = migrate_price_rule({'alert_id': 'prior', 'symbol': 'BTCUSD', 'status': 'active',
        'direction': 'above', 'threshold': 105, 'created_at': '2026-01-01T00:00:00+00:00'})
    assert not migrated.enabled and migrated.status == 'paused'
    assert 'calendar' in migrated.error


def test_rule_edit_resets_baseline_and_revokes_old_delivery(tmp_path):
    store = AlertStore(tmp_path)
    saved = store.save(rule())
    revised = store.save({**saved.to_wire(), 'oneShot': False})
    assert revised.revision == 2 and revised.baseline is None
    assert not delivery_rule_active(tmp_path, saved.alertId, 1)
    with pytest.raises(ValueError, match='changed elsewhere'): store.save(saved.to_wire())
    store.cancel(saved.alertId)
    assert not delivery_rule_active(tmp_path, saved.alertId, 3)


def test_append_before_state_save_retry_deduplicates_evidence(tmp_path, monkeypatch):
    store = AlertStore(tmp_path)
    store.save(rule())
    current = [history([('2026-01-05', 100)], '2026-01-05T22:00:00+00:00')]
    host = runtime(tmp_path, current)
    evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
    current[0] = history([('2026-01-05', 100), ('2026-01-06', 110)], '2026-01-06T22:00:00+00:00')
    original = host._alert_store._save
    monkeypatch.setattr(host._alert_store, '_save', lambda *args: (_ for _ in ()).throw(OSError('interrupted save')))
    with pytest.raises(OSError): evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
    monkeypatch.setattr(host._alert_store, '_save', original)
    # A vendor correction before retry must not rewrite the already-durable evidence.
    current[0] = history([('2026-01-05', 100), ('2026-01-06', 111)], '2026-01-06T22:00:00+00:00')
    emitted = evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at))
    assert emitted[0]['leftValue'] == 110
    assert len(store.events()) == 1


def test_linked_scan_health_is_projected_without_mutating_rule(tmp_path):
    from copenet.core.market.alert_state import project_alert_state
    from copenet.core.market.scans.definitions import default_scan
    saved = AlertStore(tmp_path).save(rule())
    scan = {**default_scan([]), 'symbols': ['TEST']}
    assert project_alert_state(saved, {}, [])['status'] == 'scan_missing'
    assert project_alert_state(saved, {'morning': {**scan, 'enabled': False}}, [])['status'] == 'scan_paused'
    assert project_alert_state(saved, {'morning': {**scan, 'symbols': []}}, [])['status'] == 'scan_scope_changed'
    assert project_alert_state(saved, {'morning': {**scan, 'watchlists': ['Removed']}}, [])['status'] == 'scan_blocked'
    assert AlertStore(tmp_path).list()[0] == saved


def test_evaluator_uses_registry_validation_and_reports_warmup():
    result = evaluator_request({'action': 'evaluate', 'bars': [dict(t=1,o=1,h=1,l=1,c=1,v=1)], 'timeframe': 'daily',
        'left': {'kind': 'indicator', 'indicatorId': 'rsi', 'output': 'rsi', 'config': {'period': 14}}, 'right': {'kind': 'constant', 'value': 30}})
    assert result['points'][0]['left'] is None
    with pytest.raises(ValueError, match='Invalid indicator setting'):
        evaluator_request({'action': 'validate', 'left': {'kind': 'indicator', 'indicatorId': 'rsi', 'output': 'rsi', 'config': {'period': -1}}, 'right': {'kind': 'price'}})


@pytest.mark.parametrize('symbol', ['VOO', 'SPY', 'QQQ', 'XLK', 'AAPL', 'BRK.B'])
def test_us_equities_and_etfs_are_eligible_regardless_of_aliases(tmp_path, symbol, monkeypatch):
    from copenet.core.market.universe import SYMBOL_MAP
    monkeypatch.setitem(SYMBOL_MAP, symbol, symbol)
    assert AlertStore(tmp_path).save(rule(symbol=symbol)).symbol == symbol


@pytest.mark.parametrize('symbol', ['BTCUSD', 'ETHUSD', 'BTC-USD', 'TNX', 'VIX', 'DXY', 'SOX', 'VOD.L'])
def test_non_equity_session_instruments_are_not_evaluated_on_us_equity_calendar(tmp_path, symbol):
    with pytest.raises(ValueError, match='US-listed'):
        AlertStore(tmp_path).save(rule(symbol=symbol))


def test_daily_recursive_indicator_matches_current_chart_2600_window_including_forming_tail(tmp_path):
    from dataclasses import asdict
    from math import sin
    from copenet.core.market.alert_candles import _calendar
    from copenet.core.market.alert_engine import _evaluate
    from copenet.core.market.price_history import chart_history_window
    sessions = _calendar(2010, 2027).sessions_in_range('2010-01-04', '2026-01-06')[-3001:]
    rows = [(session.date().isoformat(), 200 + 20 * sin(index / 25)) for index, session in enumerate(sessions)]
    data = history(rows, '2026-01-06T14:45:00+00:00')
    saved = AlertStore(tmp_path).save(rule(left={'kind': 'indicator', 'indicatorId': 'ema', 'output': 'value', 'config': {'period': 200}}))
    chart = chart_history_window(data.bars, 'daily')
    expected = evaluator_request({'action': 'evaluate', 'timeframe': 'daily', 'bars': [asdict(bar) for bar in chart], 'left': saved.left, 'right': saved.right})['points'][-2]
    actual, event = _evaluate(saved, data, stamp(data.updated_at))
    assert actual.observation['t'] == expected['t']
    assert actual.observation['left'] == expected['left']
    assert event is None


def test_crossing_uses_current_chart_previous_point_not_an_old_window_seed(tmp_path, monkeypatch):
    from copenet.core.market.alert_engine import _evaluate
    data = history([('2026-01-05', 100)], '2026-01-05T22:00:00+00:00')
    saved = AlertStore(tmp_path).save(rule())
    baseline, _ = _evaluate(saved, data, stamp(data.updated_at))
    data = history([('2026-01-05', 100), ('2026-01-06', 110)], '2026-01-06T22:00:00+00:00')
    monkeypatch.setattr('copenet.core.market.alert_engine.evaluator_request', lambda request: {'points': [
        {'t': data.bars[0].t, 'left': 106, 'right': 105}, {'t': data.bars[1].t, 'left': 110, 'right': 105}]})
    _, event = _evaluate(baseline, data, stamp(data.updated_at))
    assert event is None


def test_missing_history_and_runtime_failures_are_visible(tmp_path, monkeypatch):
    AlertStore(tmp_path).save(rule())
    current = [None]
    host = runtime(tmp_path, current)
    evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp('2026-01-05T22:00:00'))
    assert AlertStore(tmp_path).list()[0].status == 'missing_history'
    current[0] = history([('2026-01-05', 100)], '2026-01-05T22:00:00+00:00')
    monkeypatch.setattr('copenet.core.market.alert_engine.evaluator_request', lambda *args: (_ for _ in ()).throw(ValueError('Node missing')))
    assert evaluate_scan_alerts(host, 'morning', ['TEST'], now=stamp(current[0].updated_at)) == []
    assert AlertStore(tmp_path).list()[0].error == 'Node missing'


def test_completed_daily_close_follows_dst():
    for day, hour in [('2026-03-06', 21), ('2026-03-09', 20)]:
        data = history([(day, 100)], day + 'T22:00:00+00:00')
        result = completed_candles(data, 'daily', stamp(data.updated_at))
        assert datetime.fromisoformat(result.close_times[result.bars[-1].t]).hour == hour


@pytest.mark.asyncio
async def test_alert_rpc_saves_canonical_rule_without_fetch_and_rejects_wrong_scope(tmp_path):
    from copenet.core.market.store import MarketStore
    from copenet.host import rpc_market_alerts
    orchestrator = SimpleNamespace(market_store=MarketStore(tmp_path))
    sent = []
    async def send(payload): sent.append(payload)
    await rpc_market_alerts.handle_market_alerts_create('create', {'rule': rule(symbol='VOO')}, send, orchestrator)
    saved = sent[-1]['payload']['alerts'][0]
    assert saved['status'] == 'missing_history'
    assert saved['left'] == {'kind': 'price'}
    with pytest.raises(ValueError, match='Add this symbol'):
        await rpc_market_alerts.handle_market_alerts_save('bad', {'rule': rule(symbol='ZZZZTEST')}, send, orchestrator)
    await rpc_market_alerts.handle_market_alerts_cancel('cancel', {'alertId': saved['alertId']}, send, orchestrator)
    assert sent[-1]['payload']['alerts'][0]['status'] == 'cancelled'
