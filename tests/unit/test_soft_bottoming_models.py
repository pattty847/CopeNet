"""Feature causality, indicator integration, and matured-label split contracts."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import pytest

from scripts.soft_bottoming.model_features import indicator_series, mama_features, daily_features, engineer, WEEKLY
from scripts.soft_bottoming.model_eval import split_indices, evaluate


def prices(n=150):
    dates=pd.bdate_range('2023-01-02',periods=n)
    c=100+np.arange(n)*0.1+np.sin(np.arange(n)/3)*3
    return pd.DataFrame({'date':dates,'open':c,'high':c+1,'low':c-1,'close':c,'volume':1000.})


def test_production_mama_has_values_and_does_not_change_with_future_bars(tmp_path):
    f=prices(); prefix=f.iloc[:100]
    s=indicator_series({'full':f,'prefix':prefix},{},tmp_path)
    assert s['d:full']['mama'][99] is not None
    assert s['d:full']['mama'][:100]==s['d:prefix']['mama']
    assert s['d:full']['fama'][:100]==s['d:prefix']['fama']
    a=mama_features(f,s['d:full'],99,5,20)
    b=mama_features(prefix,s['d:prefix'],99,5,20)
    assert a==b
    assert all(v is None or np.isfinite(v) for v in a.values())


def test_price_normalization_preserves_scale(tmp_path):
    f=prices(); scaled=f.copy(); scaled[['open','high','low','close']]*=10
    s=indicator_series({'a':f,'b':scaled},{},tmp_path)
    a=mama_features(f,s['d:a'],149,5,20);b=mama_features(scaled,s['d:b'],149,5,20)
    for key in a: assert a[key]==pytest.approx(b[key])


def test_daily_features_cut_at_signal_week_before_next_open(tmp_path):
    f=prices(); week=pd.Timestamp('2023-05-01')
    w=f.iloc[::5].reset_index(drop=True)
    s=indicator_series({'TEST':f,'VOO':f},{'TEST':w},tmp_path)
    row={'symbol':'TEST','signal_week':str(week.date()),'regime':'above_40w','features':dict.fromkeys(WEEKLY,0)}
    result=engineer(row,{'TEST':f,'VOO':f},{'TEST':w},s)
    mutated=f.copy();mutated.loc[mutated.date>=week+pd.Timedelta(days=7),'close']*=9
    assert engineer(row,{'TEST':mutated,'VOO':mutated},{'TEST':w},s)==result
    expected=daily_features(f[f.date<week+pd.Timedelta(days=7)],f)
    assert result['d_return_20']==expected['return_20']


def test_split_purges_unfinished_labels_and_groups_dates():
    def row(signal,exit,status='complete'):
        return {'signal_week':signal,'outcomes':{'52':{'status':status,'exit_date':exit}}}
    rows=[row('2022-01-03','2022-12-30'),row('2022-12-05','2023-12-01'),
          row('2023-01-02','2023-12-29'),row('2023-01-02','2023-12-29'),row('2023-01-09','2024-01-05','pending')]
    train,test=split_indices(rows,52,pd.Timestamp('2023-01-01'),pd.Timestamp('2023-04-01'))
    assert train==[0]
    assert test==[2,3]


def test_insufficient_training_is_reported_not_fitted():
    rows=[{'signal_week':'2021-01-04','outcomes':{str(h):{'status':'pending'} for h in (12,26,52)}},
          {'signal_week':'2024-01-01','outcomes':{str(h):{'status':'pending'} for h in (12,26,52)}}]
    predictions,folds=evaluate(rows)
    assert not predictions
    assert folds and all(f['status']=='insufficient_data' for f in folds)


def test_first_quarter_scores_ignore_that_quarters_outcomes(monkeypatch):
    import scripts.soft_bottoming.model_eval as module
    monkeypatch.setattr(module,'HORIZONS',(12,))
    monkeypatch.setattr(module,'GROUPS',{'test':['x']})
    rows=[]
    for i,week in enumerate(pd.date_range('2021-01-04','2023-03-27',freq='W-MON')):
        rows.append({'symbol':'TEST','signal_week':str(week.date()),'engineered':{'x':None if i%9==0 else float(i%7)},
                     'outcomes':{'12':{'status':'complete','entry_date':str((week+pd.Timedelta(days=7)).date()),
                                      'exit_date':str((week+pd.Timedelta(weeks=12)).date()),
                                      'excess_pct':1 if i%2 else -1}}})
    first,_=evaluate(rows)
    import copy
    altered=copy.deepcopy(rows)
    for r in altered:
        if r['signal_week']>='2023-01-01':r['outcomes']['12']['excess_pct']*=-1
    second,_=evaluate(altered)
    assert first and len(first)==len(second)
    assert [(p['score'],p['threshold']) for p in first]==[(p['score'],p['threshold']) for p in second]
