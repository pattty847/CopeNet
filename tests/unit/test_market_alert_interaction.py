"""Interaction observations must not masquerade as continuous ticks or completed candles."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from copenet.core.market.alerts import AlertStore
from copenet.core.market.alert_engine import evaluate_scan_alerts
from copenet.core.market.alert_evaluator import evaluator_request
from copenet.core.market.alert_rehearsal import rehearse_rule
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def history(rows, fetched):
    return PriceHistory('TEST', [MarketBar(utc_midnight(datetime.fromisoformat(day).date()), *values, 100)
        for day, values in rows], [], [], fetched)


def rule(**extra):
    return {'symbol': 'TEST', 'timeframe': 'daily', 'scanId': 'morning', 'triggerMode': 'interaction',
        'direction': 'below', 'left': {'kind': 'price', 'field': 'low'}, 'right': {'kind': 'constant', 'value': 100}, **extra}


def host(tmp_path, current):
    return SimpleNamespace(store=SimpleNamespace(root_dir=tmp_path), prices=SimpleNamespace(load=lambda symbol: current[0]))


def evaluate(runtime, current):
    return evaluate_scan_alerts(runtime, 'morning', ['TEST'], now=stamp(current[0].updated_at))


def test_first_interaction_deduplicates_then_close_reports_failed_confirmation(tmp_path):
    store = AlertStore(tmp_path)
    store.save(rule(includeChart=True))
    rows = [('2026-01-05', (110, 110, 110, 110))]
    current = [history(rows, '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current)
    assert evaluate(runtime, current) == []
    rows.append(('2026-01-06', (110, 112, 100, 105)))
    current[0] = history(rows, '2026-01-06T15:00:00+00:00')
    events = evaluate(runtime, current)
    assert [event['phase'] for event in events] == ['interaction']
    assert events[0]['leftValue'] == 100  # Equality counts as interaction.
    assert events[0]['reference'] == 'previous_completed'
    assert events[0]['chartSnapshot']['bars'][-1]['c'] == 105
    assert store.list()[0].status == 'waiting_confirmation' and store.list()[0].enabled
    assert evaluate(runtime, current) == []
    current[0] = replace(current[0], updated_at='2026-01-06T22:00:00+00:00')
    followup = evaluate(runtime, current)[0]
    assert followup['phase'] == 'not_confirmed'
    assert followup['interactionEventId'] == events[0]['eventId']
    assert followup['leftValue'] == 105
    assert not store.list()[0].enabled
    assert len(store.events()) == 2


def test_arming_suppresses_touch_already_in_forming_candle(tmp_path):
    AlertStore(tmp_path).save(rule())
    current = [history([('2026-01-05', (110,110,110,110)), ('2026-01-06', (110,112,95,102))], '2026-01-06T15:00:00+00:00')]
    runtime = host(tmp_path, current)
    assert evaluate(runtime, current) == []
    current[0] = replace(current[0], updated_at='2026-01-06T22:00:00+00:00')
    assert evaluate(runtime, current) == []
    assert AlertStore(tmp_path).list()[0].enabled


def test_weekly_reference_is_previous_completed_signal_and_confirm_waits_for_friday(tmp_path):
    AlertStore(tmp_path).save(rule(timeframe='weekly', includeChart=True,
        right={'kind': 'indicator', 'indicatorId': 'sma', 'output': 'value', 'config': {'period': 1}}))
    rows = [(f'2026-01-{day:02d}', (100,100,100,100)) for day in range(5,10)]
    current = [history(rows, '2026-01-09T22:00:00+00:00')]
    runtime = host(tmp_path, current)
    evaluate(runtime, current)
    rows += [('2026-01-12', (110,112,105,110))]
    current[0] = history(rows, '2026-01-12T22:00:00+00:00')
    assert evaluate(runtime, current) == []
    rows += [('2026-01-13', (110,115,99,109))]
    current[0] = history(rows, '2026-01-13T16:00:00+00:00')
    event = evaluate(runtime, current)[0]
    assert event['phase'] == 'interaction' and event['rightValue'] == 100
    assert event['candleCloseAt'] == '2026-01-16T21:00:00+00:00'
    current[0] = replace(current[0], updated_at='2026-01-13T22:00:00+00:00')
    assert evaluate(runtime, current) == []
    rows += [(f'2026-01-{day}', (109,109,98,99)) for day in range(14,17)]
    current[0] = history(rows, '2026-01-16T22:00:00+00:00')
    assert evaluate(runtime, current)[0]['phase'] == 'confirmed'


def test_confirmation_uses_custom_indicator_condition(tmp_path):
    AlertStore(tmp_path).save(rule(confirmation={
        'left': {'kind': 'indicator', 'indicatorId': 'sma', 'config': {'period': 1}, 'output': 'value'},
        'right': {'kind': 'indicator', 'indicatorId': 'sma', 'config': {'period': 2}, 'output': 'value'}, 'direction': 'below'}))
    rows = [('2026-01-05', (110,110,110,110))]
    current = [history(rows, '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current); evaluate(runtime, current)
    rows += [('2026-01-06', (110,110,99,105))]
    current[0] = history(rows, '2026-01-06T15:00:00+00:00'); evaluate(runtime, current)
    current[0] = replace(current[0], updated_at='2026-01-06T22:00:00+00:00')
    event = evaluate(runtime, current)[0]
    assert event['phase'] == 'confirmed' and event['leftValue'] == 105 and event['rightValue'] == 107.5
    assert 'chartSnapshot' not in event


def test_pending_followup_survives_preclose_cache_but_not_missed_period(tmp_path):
    store = AlertStore(tmp_path); store.save(rule())
    rows = [('2026-01-05', (110,110,110,110))]
    current = [history(rows, '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current); evaluate(runtime, current)
    rows += [('2026-01-06', (110,110,99,99))]
    current[0] = history(rows, '2026-01-06T15:00:00+00:00'); evaluate(runtime, current)
    assert evaluate_scan_alerts(runtime, 'morning', ['TEST'], now=stamp('2026-01-06T22:00:00')) == []
    assert store.list()[0].status == 'stale'
    rows += [('2026-01-07', (99,99,98,98))]
    current[0] = history(rows, '2026-01-07T22:00:00+00:00')
    assert evaluate(runtime, current) == []
    assert store.list()[0].status == 'rebaselined'
    assert len(store.events()) == 1


def test_stale_forming_tail_never_triggers_current_period(tmp_path):
    AlertStore(tmp_path).save(rule())
    current = [history([('2026-01-05', (110,110,110,110))], '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current); evaluate(runtime, current)
    assert evaluate_scan_alerts(runtime, 'morning', ['TEST'], now=stamp('2026-01-06T15:00:00')) == []
    assert 'refresh' in AlertStore(tmp_path).list()[0].error


def test_rehearsal_does_not_mutate_rules_or_events(tmp_path):
    store = AlertStore(tmp_path); saved = store.save(rule())
    rows = [('2026-01-05', (110,110,110,110)), ('2026-01-06', (110,112,99,105)), ('2026-01-07', (105,105,98,98))]
    data = history(rows, '2026-01-07T22:00:00+00:00')
    result = rehearse_rule(saved, data, now=stamp(data.updated_at))
    assert result['matchCount'] == 1 and result['matches'][0]['phase'] == 'not_confirmed'
    assert store.list() == [saved] and store.events() == []
    assert 'intraperiod' in result['note']


@pytest.mark.parametrize(('field', 'expected'), [('open',101), ('high',120), ('low',90), ('close',105)])
def test_price_field_uses_exact_ohlc_value(field, expected):
    result = evaluator_request({'action':'evaluate', 'timeframe':'daily', 'bars':[dict(t=1,o=101,h=120,l=90,c=105,v=1)],
        'left':{'kind':'price','field':field}, 'right':{'kind':'constant','value':100}})
    assert result['points'][0]['left'] == expected


def test_monitor_validation_rejects_unsupported_price_and_confirmation(tmp_path):
    for changes in [{'left': {'kind':'price','field':'volume'}}, {'includeChart': 'yes'},
                    {'confirmation': {'direction':'touch'}}, {'left': {'kind':'constant','value':100}}]:
        with pytest.raises(ValueError): AlertStore(tmp_path).save(rule(**changes))


def test_close_field_can_reset_intraperiod_without_duplicate_heads_up(tmp_path):
    store = AlertStore(tmp_path); store.save(rule(left={'kind':'price','field':'close'}, oneShot=False))
    rows = [('2026-01-05', (110,110,110,110))]
    current = [history(rows, '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current); evaluate(runtime, current)
    for hour, value in [(15,99), (16,105), (17,98)]:
        current[0] = history(rows + [('2026-01-06', (110,110,98,value))], f'2026-01-06T{hour}:00:00+00:00')
        events = evaluate(runtime, current)
        assert len(events) == (1 if hour == 15 else 0)
    assert len(store.events()) == 1


def test_pending_confirmation_drops_on_split_instead_of_reusing_wrong_price_basis(tmp_path):
    store = AlertStore(tmp_path); store.save(rule())
    rows = [('2026-01-05', (110,110,110,110))]
    current = [history(rows, '2026-01-05T22:00:00+00:00')]
    runtime = host(tmp_path, current); evaluate(runtime, current)
    rows += [('2026-01-06', (110,110,99,99))]
    current[0] = history(rows, '2026-01-06T15:00:00+00:00'); evaluate(runtime, current)
    current[0] = replace(current[0], splits=[('2026-01-06', 2)], updated_at='2026-01-06T22:00:00+00:00')
    assert evaluate(runtime, current) == []
    assert store.list()[0].status == 'rebaselined'
    assert store.list()[0].baseline['pending'] is None


@pytest.mark.asyncio
async def test_rehearsal_rpc_needs_no_linked_scan_and_never_persists_rule(tmp_path):
    from copenet.core.market.store import MarketStore
    from copenet.host.rpc_market_alerts import handle_market_alerts_rehearse
    sent = []
    async def send(payload): sent.append(payload)
    await handle_market_alerts_rehearse('rehearse', {'rule': rule(scanId='')}, send, SimpleNamespace(market_store=MarketStore(tmp_path)))
    assert sent[-1]['payload']['status'] == 'missing_history'
    assert AlertStore(tmp_path).list() == []
