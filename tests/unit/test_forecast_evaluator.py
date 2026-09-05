"""Synthetic forward paths; no prices from an operator account or provider."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from copenet.core.market.alert_candles import _calendar
from copenet.core.market.forecasts.candles import forecast_candles
from copenet.core.market.forecasts.evaluator import evaluate_forecast
from copenet.core.market.forecasts.report import forecast_report
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import utc_midnight


def instant(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def forecast(**changes):
    result = {'forecastId': 'synthetic-forecast', 'status': 'published', 'publishedAt': '2024-01-02T21:01:00+00:00',
              'referenceClose': 100, 'instrument': {'symbol': 'TEST'}, 'entryExpirySessions': 10,
              'paired': False, 'provenance': {'basis': 'split_adjusted', 'calendar': 'XNYS', 'splits': [], 'splitFingerprint': ''},
              'members': {'ta': {'result': {'kind': 'setup', 'direction': 'long', 'entry': {'kind': 'limit', 'price': 100},
                                         'stop': 95, 'targets': [{'price': 110, 'fraction': 1.0}]}}}}
    result.update(changes)
    return result


def history(rows=None, *, until='2024-02-29', fetched='2024-03-01T22:00:00+00:00', splits=None):
    schedule = _calendar(2024, 2025).schedule.loc['2024-01-02':until]
    bars = [MarketBar(utc_midnight(day.date()), *(rows or {}).get(day.date().isoformat(), (100, 101, 99, 100)), 1000)
            for day, _ in schedule.iterrows()]
    return PriceHistory('TEST', bars, splits or [], [], fetched)


def evaluate(rows=None, **options):
    return evaluate_forecast(options.pop('forecast', forecast()), history(rows, **options), instant('2024-03-01T22:00:00'))


@pytest.mark.parametrize('short', [False, True])
def test_stop_out_remains_loss_when_eight_week_direction_recovers(short):
    item = forecast()
    rows = {'2024-01-04': (100, 101, 94, 96), '2024-02-27': (120, 121, 119, 120)}
    if short:
        setup = item['members']['ta']['result']
        setup.update(direction='short', stop=105, targets=[{'price': 90, 'fraction': 1.0}])
        rows = {day: (200-o, 200-l, 200-h, 200-c) for day, (o,h,l,c) in rows.items()}
    result = evaluate(rows, forecast=item)
    assert result['state'] == 'stopped'
    assert result['plannedRiskR'] == -1
    assert result['horizons']['8w']['members']['ta']['outcome'] == 'correct'
    assert result['horizons']['8w']['endpointDate'] == '2024-02-27'


@pytest.mark.parametrize('entry_kind,bar', [('limit', (102, 111, 99, 105)), ('stop', (98, 111, 97, 105))])
def test_intrabar_entry_plus_exit_is_explicitly_ambiguous(entry_kind, bar):
    item = forecast()
    item['members']['ta']['result']['entry']['kind'] = entry_kind
    result = evaluate({'2024-01-03': bar}, forecast=item)
    assert result['state'] == 'ambiguous'
    assert result['plannedRiskR'] is None
    assert result['events'][-1]['reason'] == 'intrabar_entry_exit'


def test_opening_gap_stop_precedes_later_recovery():
    result = evaluate({'2024-01-04': (90, 120, 89, 115)})
    assert result['state'] == 'stopped'
    assert result['plannedRiskR'] == -2
    assert result['events'][-1]['price'] == 90


@pytest.mark.parametrize('entry_kind,opening', [('limit', 94), ('stop', 111)])
def test_opening_entry_beyond_setup_does_not_invent_round_trip(entry_kind, opening):
    item = forecast()
    item['members']['ta']['result']['entry']['kind'] = entry_kind
    result = evaluate({'2024-01-03': (opening, opening+1, opening-1, opening)}, forecast=item)
    assert result['state'] == 'gapped_past_setup'
    assert result['entryPrice'] is None
    assert result['plannedRiskR'] is None


def test_multiple_targets_fill_original_fractions_in_order():
    item = forecast()
    item['members']['ta']['result']['targets'] = [{'price': 105, 'fraction': .25}, {'price': 110, 'fraction': .75}]
    result = evaluate({'2024-01-04': (100, 111, 99, 110)}, forecast=item)
    assert result['state'] == 'target_complete'
    assert result['plannedRiskR'] == 1.75
    assert [event['fraction'] for event in result['events'] if event['type'] == 'target'] == [.25, .75]


def test_partial_opening_target_then_intrabar_stop_is_known_order():
    item = forecast()
    item['members']['ta']['result']['targets'] = [{'price': 105, 'fraction': .5}, {'price': 110, 'fraction': .5}]
    result = evaluate({'2024-01-04': (106, 107, 94, 95)}, forecast=item)
    assert result['state'] == 'stopped'
    assert result['plannedRiskR'] == 0
    assert [event['type'] for event in result['events']] == ['entry', 'target', 'stop']


def test_carried_stop_and_unfilled_target_is_ambiguous():
    result = evaluate({'2024-01-04': (100, 111, 94, 100)})
    assert result['state'] == 'ambiguous'
    assert result['events'][-1]['reason'] == 'carried_position_stop_target'


def test_expiry_counts_exchange_sessions_and_includes_final_session():
    item = forecast()
    item['members']['ta']['result']['entry']['price'] = 98
    result = evaluate(forecast=item)
    assert result['state'] == 'expired_unfilled'
    assert result['events'][-1]['date'] == '2024-01-17'  # MLK holiday excluded.
    filled = evaluate({'2024-01-17': (98, 99, 97, 98)}, forecast=item)
    assert filled['entryDate'] == '2024-01-17'


def test_deadline_closes_remaining_partial_at_dated_endpoint_on_late_check():
    item = forecast()
    item['members']['ta']['result']['targets'] = [{'price': 105, 'fraction': .5}, {'price': 120, 'fraction': .5}]
    result = evaluate({'2024-01-04': (105, 106, 99, 105), '2024-02-27': (108, 109, 107, 108), '2024-02-29': (150, 151, 149, 150)}, forecast=item)
    assert result['state'] == 'deadline_exit'
    assert result['exitDate'] == '2024-02-27'
    assert result['plannedRiskR'] == pytest.approx(1.3)
    assert result['horizons']['8w']['endpointClose'] == 108


@pytest.mark.parametrize('published,expected', [('2024-01-03T15:00:00+00:00', '2024-01-04'), ('2024-01-13T12:00:00+00:00', '2024-01-16'), ('2024-01-03T14:30:00+00:00', '2024-01-04')])
def test_activation_requires_a_strictly_future_exchange_open(published, expected):
    item = forecast(publishedAt=published)
    result = evaluate_forecast(item, history(), instant('2024-03-01T22:00:00'))
    assert result['activationDate'] == expected
    assert result['entryDate'] == expected


def test_missing_session_stops_at_gap_and_preserves_earlier_events():
    raw = history({'2024-01-04': (100, 101, 94, 95)})
    raw.bars[:] = [bar for bar in raw.bars if datetime.fromtimestamp(bar.t, timezone.utc).date().isoformat() != '2024-01-05']
    result = evaluate_forecast(forecast(), raw, instant('2024-03-01T22:00:00'))
    assert result['health'] == 'data_gap'
    assert result['state'] == 'stopped'
    assert result['horizons']['8w']['status'] == 'pending'
    assert result['consumedBars'][-1]['date'] == '2024-01-04'


def test_fetch_before_close_never_completes_candle():
    result = evaluate(until='2024-01-04', fetched='2024-01-04T20:59:00+00:00')
    assert result['health'] == 'stale'
    assert result['consumedBars'][-1]['date'] == '2024-01-03'


def test_split_rebase_preserves_frozen_levels_and_consumed_history():
    item = forecast()
    original = history(until='2024-01-05', fetched='2024-01-05T22:00:00+00:00')
    item['evaluation'] = evaluate_forecast(item, original, instant('2024-01-05T22:00:00'))
    raw = history(splits=[('2024-01-08', 2.0)])
    raw.bars[:] = [MarketBar(bar.t, bar.o/2, bar.h/2, bar.l/2, bar.c/2, bar.v) for bar in raw.bars]
    result = evaluate_forecast(item, raw, instant('2024-03-01T22:00:00'))
    assert result['health'] == 'ready'
    assert result['entryPrice'] == 100
    assert result['source']['publicationBasisFactor'] == 2
    assert result['events'][0]['recordedAt'] == item['evaluation']['events'][0]['recordedAt']


def test_revised_consumed_history_retains_original_evaluation():
    item = forecast()
    item['evaluation'] = evaluate_forecast(item, history(), instant('2024-03-01T22:00:00'))
    raw = history({'2024-01-03': (100, 101, 90, 100)})
    result = evaluate_forecast(item, raw, instant('2024-03-02T22:00:00'))
    assert result['health'] == 'revision_review'
    assert result['state'] == item['evaluation']['state']
    assert result['consumedBars'] == item['evaluation']['consumedBars']
    assert result['events'][-1]['type'] == 'revision_notice'


def test_reordered_and_duplicate_identical_bars_are_idempotent():
    item, raw = forecast(), history()
    expected = evaluate_forecast(item, raw, instant('2024-03-01T22:00:00'))
    raw.bars[:] = list(reversed(raw.bars)) + [raw.bars[0]]
    assert evaluate_forecast(item, raw, instant('2024-03-01T22:00:00')) == expected


def test_out_of_scope_instrument_is_never_scored():
    item = forecast(instrument={'symbol': 'OTHER'})
    assert evaluate(forecast=item)['health'] == 'unsupported'


def test_early_close_is_completed_at_exchange_close():
    item = forecast(publishedAt='2024-11-27T22:00:00+00:00')
    raw = PriceHistory('TEST', [MarketBar(utc_midnight(datetime(2024, 11, 29).date()), 100, 101, 99, 100, 1000)], [], [], '2024-11-29T18:01:00+00:00')
    result = evaluate_forecast(item, raw, instant('2024-11-29T18:01:00'))
    assert result['entryDate'] == '2024-11-29'
    assert result['health'] == 'ready'
    assert result['consumedBars'][0]['sessionClose'] == '2024-11-29T18:00:00+00:00'


def test_reports_keep_all_attempts_and_trade_scores_separate_from_pairs():
    item = forecast(paired=True)
    item['members']['directional'] = {'result': {'kind': 'directional', 'direction': 'bearish'}}
    item['evaluation'] = evaluate({'2024-01-04': (100, 101, 94, 96), '2024-02-27': (120, 121, 119, 120)}, forecast=item)
    failed = forecast(status='failed', members={})
    report = forecast_report([item, failed])
    assert report['attemptCount'] == 2
    assert report['trade']['meanPlannedRiskR'] == -1
    assert report['direction']['8w']['accuracy'] == 1
    assert report['paired']['8w']['correctnessDelta'] == 1
    assert report['states']['failed'] == 1


@pytest.mark.parametrize('kind', ['limit', 'stop'])
def test_short_entries_and_targets_mirror_long(kind):
    long = forecast()
    long['members']['ta']['result']['entry']['kind'] = kind
    short = deepcopy(long)
    short['members']['ta']['result'].update(direction='short', stop=105, targets=[{'price': 90, 'fraction': 1.0}])
    long_rows = {'2024-01-03': (100, 101, 99, 100), '2024-01-04': (105, 111, 104, 110)}
    short_rows = {day: (200-o, 200-l, 200-h, 200-c) for day, (o,h,l,c) in long_rows.items()}
    long_result, short_result = evaluate(long_rows, forecast=long), evaluate(short_rows, forecast=short)
    assert long_result['state'] == short_result['state'] == 'target_complete'
    assert long_result['plannedRiskR'] == short_result['plannedRiskR'] == 2


def test_missing_deadline_never_uses_an_older_close():
    raw = history()
    raw.bars[:] = [bar for bar in raw.bars if datetime.fromtimestamp(bar.t, timezone.utc).date().isoformat() != '2024-02-27']
    result = evaluate_forecast(forecast(), raw, instant('2024-03-01T22:00:00'))
    assert result['health'] == 'data_gap'
    assert result['state'] == 'active'
    assert result['horizons']['8w']['endpointClose'] is None
    assert result['horizons']['4w']['status'] == 'resolved'


def test_revision_review_does_not_silently_resume_when_cache_changes_back():
    item = forecast()
    item['evaluation'] = evaluate_forecast(item, history(), instant('2024-03-01T22:00:00'))
    item['evaluation'] = evaluate_forecast(item, history({'2024-01-03': (100, 101, 90, 100)}), instant('2024-03-02T22:00:00'))
    result = evaluate_forecast(item, history(), instant('2024-03-03T22:00:00'))
    assert result['health'] == 'revision_review'
    assert result['reason']


def test_gap_entry_uses_actual_price_but_original_planned_risk():
    result = evaluate({'2024-01-03': (98, 101, 97, 100), '2024-01-04': (100, 111, 99, 110)})
    assert result['entryPrice'] == 98
    assert result['plannedRiskR'] == pytest.approx(2.4)


def test_failed_ta_member_is_missing_not_a_model_abstention():
    item = forecast(paired=True, members={'ta': {'status': 'failed'}, 'directional': {'result': {'kind': 'directional', 'direction': 'bullish'}}})
    item['evaluation'] = evaluate(forecast=item)
    assert item['evaluation']['state'] == 'unavailable'
    assert 'ta' not in item['evaluation']['horizons']['8w']['members']
    report = forecast_report([item])
    assert report['direction']['8w']['counts'] == {'missing': 1}
    assert report['paired']['8w']['pairedCount'] == 0


def test_split_rounding_preserves_exact_previously_consumed_event_prices():
    item = forecast()
    original = history({'2024-01-03': (99.7, 101, 99, 100)})
    item['evaluation'] = evaluate_forecast(item, original, instant('2024-01-04T22:00:00'))
    split = history({'2024-01-03': (99.7, 101, 99, 100)}, splits=[('2024-02-01', 3.0)])
    split.bars[:] = [MarketBar(bar.t, bar.o / 3, bar.h / 3, bar.l / 3, bar.c / 3, bar.v) for bar in split.bars]
    replay = evaluate_forecast(item, split, instant('2024-03-01T22:00:00'))
    assert replay['health'] == 'ready'
    assert replay['events'][0] == item['evaluation']['events'][0]
    assert replay['consumedBars'][:2] == item['evaluation']['consumedBars']
