"""Synthetic checks for execution timing, censoring and historical feature isolation."""
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import pytest

from scripts.soft_bottoming.outcomes import measure_outcome
from scripts.soft_bottoming import experiment
from scripts.soft_bottoming.report import summarize


def daily_frame():
    dates = pd.bdate_range('2024-01-01', '2024-09-01')
    return pd.DataFrame({'date': dates, 'open': 100., 'high': 110., 'low': 90.,
                         'close': 105., 'volume': 1000})


def test_entry_uses_next_week_open_and_excludes_signal_week():
    f = daily_frame()
    f.loc[f.date < '2024-01-08', ['close','low','high']] = [900., 1., 1000.]
    outcome = measure_outcome(f, daily_frame(), pd.Timestamp('2024-01-01'), 4, pd.Timestamp('2024-09-01'))
    assert outcome['entry_date'] == '2024-01-08'
    assert outcome['exit_date'] == '2024-02-02'
    assert outcome['return_pct'] == pytest.approx(5)
    assert outcome['mae_pct'] == pytest.approx(-10)
    assert outcome['excess_pct'] == pytest.approx(0)


def test_unfinished_outcome_is_pending_and_missing_session_is_not_a_loss():
    f = daily_frame()
    assert measure_outcome(f, f, pd.Timestamp('2024-08-05'), 26, pd.Timestamp('2024-09-01')) == {'status':'pending'}
    missing = f[f.date != '2024-01-10']
    assert measure_outcome(missing, f, pd.Timestamp('2024-01-01'), 4, pd.Timestamp('2024-09-01')) == {'status':'missing_sessions'}


def test_drawdown_tracks_peak_to_trough_and_recovery_is_after_a_loss():
    f = daily_frame()
    f.loc[f.date == '2024-01-08', 'close'] = 120
    f.loc[f.date == '2024-01-09', 'close'] = 80
    f.loc[f.date == '2024-01-10', 'close'] = 101
    x = measure_outcome(f, daily_frame(), pd.Timestamp('2024-01-01'), 4, pd.Timestamp('2024-09-01'))
    assert x['max_drawdown_pct'] == pytest.approx(-100/3)
    assert x['recovery_days'] == 2


def test_replay_passes_only_historical_prefix_and_deduplicates_active_weeks(tmp_path, monkeypatch):
    weeks = pd.date_range('2023-01-02', periods=52, freq='W-MON')
    f = pd.DataFrame({'date': weeks, 'open':100., 'high':110., 'low':90., 'close':100., 'volume':1000})
    calls = []
    def compute(stock, bench, **kwargs):
        date = stock.date.iloc[-1]
        assert bench.date.max() <= date
        assert len(stock) == list(weeks).index(date)+1
        calls.append(date)
        active = date in set(weeks[44:46]) | {weeks[48]}
        return SimpleNamespace(soft_bottoming=active, to_dict=lambda: {'soft_bottoming':active})
    monkeypatch.setattr(experiment, 'compute_features', compute)
    monkeypatch.setattr(experiment, 'measure_outcome', lambda *a: {'status':'pending'})
    rows = experiment.replay({'TEST':f,'VOO':f}, {'TEST':f,'VOO':f}, ['TEST'], weeks[44], weeks[-1]+pd.Timedelta(days=3), tmp_path)
    assert calls[0] == weeks[43]
    assert [r['signal_week'] for r in rows if r['episode']] == [str(weeks[44].date()),str(weeks[48].date())]
    assert calls[-1] == weeks[-2]  # current partial week never reaches the extractor


def test_common_cohort_does_not_mix_pending_long_horizons():
    def outcome(value):
        return {'status':'complete','entry_date':'2023-01-09','exit_date':'2023-07-07','return_pct':value,'excess_pct':value,'mae_pct':-10.,
                'max_drawdown_pct':-10.,'annualized_vol_pct':20.,'went_underwater':True,'recovery_days':3}
    row = {'symbol':'TEST','episode':True,'signal_week':'2023-01-02','regime':'above_40w',
           'features': {'soft_bottoming':True}, 'outcomes':{str(h):outcome(h) for h in (4,12,26)}}
    recent = {**row,'signal_week':'2024-07-01','outcomes':{'4':outcome(100),'12':{'status':'pending'},'26':{'status':'pending'}}}
    s = summarize([row,recent])
    assert s['horizons']['4']['n'] == 2
    assert s['common_cohort']['4']['n'] == 1
    assert s['common_cohort']['4']['median_return_pct'] == 4


def test_report_serializes_real_outcome_scalar_types(tmp_path):
    from scripts.soft_bottoming.report import write_report
    f = daily_frame()
    r = {'symbol':'TEST','episode':True,'signal_week':'2024-01-01','regime':'above_40w',
         'features':{'soft_bottoming':True},
         'outcomes':{str(h):measure_outcome(f,f,pd.Timestamp('2024-01-01'),h,pd.Timestamp('2024-09-01')) for h in (4,12,26)}}
    write_report([r],tmp_path)
    assert (tmp_path/'summary.json').exists()


def test_snapshot_omits_stale_partial_week_even_when_wall_clock_is_later(tmp_path):
    import json
    from copenet.core.market.price_cache import PriceCache
    root = tmp_path/'cache'
    root.mkdir()
    bars = [{'t':int(pd.Timestamp(d,tz='UTC').timestamp()),'o':100,'h':101,'l':99,'c':100,'v':100}
            for d in pd.bdate_range('2024-01-01','2024-01-10')]
    (root/'VOO.json').write_text(json.dumps({'cacheVersion':1,'priceBasis':'split_adjusted',
        'symbol':'VOO','updatedAt':'2024-01-10T22:00:00+00:00','bars':bars,'splits':[],'dividends':[]}))
    output = tmp_path/'run'; output.mkdir()
    _, weekly = experiment.snapshot(PriceCache(root),[],output,pd.Timestamp('2024-02-01T00:00:00Z'))
    assert weekly['VOO'].date.tolist() == [pd.Timestamp('2024-01-01')]


def test_nonoverlapping_sensitivity_keeps_only_one_open_episode_per_symbol():
    f = daily_frame()
    rows = []
    for day in ('2024-01-01','2024-01-15'):
        rows.append({'symbol':'TEST','episode':True,'signal_week':day,'regime':'above_40w',
                     'features':{'soft_bottoming':True},
                     'outcomes':{str(h):measure_outcome(f,f,pd.Timestamp(day),h,pd.Timestamp('2024-09-01')) for h in (4,12,26)}})
    s = summarize(rows)
    assert s['common_cohort']['26']['n'] == 2
    assert s['nonoverlapping_26w']['n'] == 1
