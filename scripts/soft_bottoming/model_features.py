"""Scale-independent features sampled at the completed signal week only."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

WEEKLY = ['r_4w','r_13w','drawdown_pct','rsi_14','vol_13w','atr_pct',
          'dist_ma10','dist_ma40','vol_vs_avg','rs_momentum','excess_13w',
          'sb_lower_lows_stopped','sb_higher_low','sb_ma_reclaim',
          'sb_drawdown_stabilized','sb_rs_improving','sb_volume_drying','sb_momentum_divergence']
MAMA = ['gap_pct','gap_atr','price_mama_pct','above','mama_slope_short',
        'mama_slope_long','fama_slope_short','fama_slope_long','cross_age']
DAILY = ['return_5','return_20','vol_20','rsi_14','atr_pct','volume_ratio','excess_20']
GROUPS = {
    'weekly': WEEKLY + ['market_above_40w'],
    'weekly_mama': WEEKLY + ['market_above_40w'] + ['w_'+k for k in MAMA],
    'daily_context': WEEKLY + ['market_above_40w'] + ['w_'+k for k in MAMA] + ['d_'+k for k in DAILY],
    'daily_mama': WEEKLY + ['market_above_40w'] + ['w_'+k for k in MAMA] + ['d_'+k for k in DAILY+MAMA],
}


def indicator_series(daily, weekly, output):
    payload = {}
    for timeframe, frames in [('d',daily),('w',weekly)]:
        for symbol, f in frames.items():
            payload[timeframe+':'+symbol] = [dict(t=int(r.date.timestamp()),o=r.open,h=r.high,
                                                 l=r.low,c=r.close,v=r.volume)
                                            for r in f.itertuples()]
    path = output/'indicator-inputs.json'
    path.write_text(json.dumps(payload, allow_nan=False))
    target = output/'indicator-series.json'
    subprocess.run(['src/copenet/host/frontend/node_modules/.bin/tsx',
                    'scripts/soft_bottoming/mama.ts',str(path),str(target)], check=True)
    return json.loads(target.read_text())


def atr(f):
    previous = f.close.shift(1)
    return pd.concat([f.high-f.low,(f.high-previous).abs(),(f.low-previous).abs()],axis=1).max(axis=1).tail(14).mean()


def mama_features(f, series, index, short, long):
    m = np.array(series['mama'][:index+1],dtype=float)
    a = np.array(series['fama'][:index+1],dtype=float)
    price = float(f.close.iloc[index])
    if not len(m) or not np.isfinite(m[-1]) or not np.isfinite(a[-1]):
        return dict.fromkeys(MAMA)
    gap = m-a
    crosses = np.flatnonzero(np.isfinite(gap[1:]) & np.isfinite(gap[:-1]) & ((gap[1:] > 0) != (gap[:-1] > 0)))+1
    result = {'gap_pct':100*gap[-1]/price,'gap_atr':gap[-1]/atr(f.iloc[:index+1]),
              'price_mama_pct':100*(price-m[-1])/price,'above':int(gap[-1]>0),
              'cross_age':int(index-crosses[-1]) if len(crosses) else None}
    for name,values in [('mama',m),('fama',a)]:
        for label,lag in [('short',short),('long',long)]:
            result[name+'_slope_'+label] = 100*(values[-1]-values[-lag-1])/price if len(values)>lag else None
    return result


def daily_features(f, benchmark):
    c=f.close
    delta=c.diff(); gain=delta.clip(lower=0).tail(14).mean(); loss=(-delta.clip(upper=0)).tail(14).mean()
    rsi = 100*gain/(gain+loss) if gain+loss else 50.
    br = benchmark.set_index('date').close.reindex(f.date).to_numpy()
    return {'return_5':100*(c.iloc[-1]/c.iloc[-6]-1),
            'return_20':100*(c.iloc[-1]/c.iloc[-21]-1),
            'vol_20':float(c.pct_change().tail(20).std()*np.sqrt(252)*100),
            'rsi_14':rsi,'atr_pct':float(100*atr(f)/c.iloc[-1]),
            'volume_ratio':float(f.volume.iloc[-1]/f.volume.tail(20).mean()) if f.volume.tail(20).mean() else None,
            'excess_20':100*(c.iloc[-1]/c.iloc[-21]-br[-1]/br[-21])}


def engineer(row, daily, weekly, series):
    symbol=row['symbol']; end=pd.Timestamp(row['signal_week'])+pd.Timedelta(days=7)
    d=daily[symbol]; w=weekly[symbol]
    di=int(d.date.searchsorted(end))-1; wi=int(w.date.searchsorted(end))-1
    values={k:row['features'][k] for k in WEEKLY}
    values['market_above_40w']=int(row['regime']=='above_40w')
    for prefix, f, index, short,long in [('d',d,di,5,20),('w',w,wi,1,4)]:
        values.update({prefix+'_'+k:v for k,v in mama_features(f,series[prefix+':'+symbol],index,short,long).items()})
    values.update({'d_'+k:v for k,v in daily_features(d.iloc[:di+1],daily['VOO']).items()})
    # This is the raw engineered-feature boundary: non-finite values become missing.
    return {k:float(v) if v is not None and np.isfinite(v) else None for k,v in values.items()}
