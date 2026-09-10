"""Descriptive baseline; date-matched controls and equal-quarter sensitivity."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .outcomes import HORIZONS


def describe(outcomes: list[dict]) -> dict:
    if not outcomes:
        return {"n": 0}
    f = pd.DataFrame(outcomes)
    return {"n": len(f), "positive_pct": float((f.return_pct > 0).mean() * 100),
            "beat_benchmark_pct": float((f.excess_pct > 0).mean() * 100),
            **{f"median_{key}": float(f[key].median()) for key in
               ("return_pct", "excess_pct", "mae_pct", "max_drawdown_pct", "annualized_vol_pct")},
            "p10_return_pct": float(f.return_pct.quantile(0.1)),
            "p10_mae_pct": float(f.mae_pct.quantile(0.1)),
            "underwater_pct": float(f.went_underwater.mean()*100),
            "recovered_of_underwater_pct": (float(f.loc[f.went_underwater, "recovery_days"].notna().mean()*100)
                                            if f.went_underwater.any() else None)}


def summarize(rows: list[dict]) -> dict:
    episodes = [r for r in rows if r["episode"]]
    result = {"eligible_weeks": len(rows), "episodes": len(episodes),
              "symbols_with_episodes": len({r['symbol'] for r in episodes}),
              "distinct_signal_weeks": len({r['signal_week'] for r in episodes}),
              "horizons": {}}
    for horizon in HORIZONS:
        key = str(horizon)
        complete = [r for r in episodes if r['outcomes'][key]['status'] == 'complete']
        by_date = {}
        for r in rows:
            if r['outcomes'][key]['status'] == 'complete':
                by_date.setdefault(r['signal_week'], []).append(r)
        comparisons = []
        for event in complete:
            controls = [r for r in by_date[event['signal_week']]
                        if r['symbol'] != event['symbol'] and not r['features']['soft_bottoming']
                        and r['features']['drawdown_pct'] is not None
                        and r['features']['drawdown_pct'] <= -10]
            if controls:
                comparisons.append({"quarter": str(pd.Timestamp(event['signal_week']).to_period('Q')),
                                    "delta": event['outcomes'][key]['return_pct'] -
                                    float(np.mean([r['outcomes'][key]['return_pct'] for r in controls]))})
        quarter_means = pd.DataFrame(comparisons).groupby('quarter').delta.mean() if comparisons else pd.Series(dtype=float)
        result['horizons'][key] = {
            **describe([r['outcomes'][key] for r in complete]),
            "pending": sum(r['outcomes'][key]['status'] == 'pending' for r in episodes),
            "unusable": sum(r['outcomes'][key]['status'] not in ('pending', 'complete') for r in episodes),
            "matched_episodes": len(comparisons),
            "mean_return_advantage_vs_declining_controls_pct": float(np.mean([c['delta'] for c in comparisons])) if comparisons else None,
            "equal_quarter_mean_advantage_pct": float(quarter_means.mean()) if len(quarter_means) else None,
            "quarters_with_controls": len(quarter_means),
            "by_year": {year: describe([r['outcomes'][key] for r in complete if r['signal_week'][:4] == year])
                        for year in sorted({r['signal_week'][:4] for r in complete})},
            "by_regime": {regime: describe([r['outcomes'][key] for r in complete if r['regime'] == regime])
                          for regime in ('above_40w', 'below_40w')},
        }
    paired = [r for r in episodes if all(r['outcomes'][str(h)]['status'] == 'complete' for h in HORIZONS)]
    result['common_cohort'] = {str(h): describe([r['outcomes'][str(h)] for r in paired]) for h in HORIZONS}
    nonoverlapping = []
    last_exit = {}
    for r in sorted(paired, key=lambda r: (r['signal_week'], r['symbol'])):
        outcome = r['outcomes']['26']
        if outcome['entry_date'] > last_exit.get(r['symbol'], ''):
            nonoverlapping.append(r)
            last_exit[r['symbol']] = outcome['exit_date']
    result['nonoverlapping_26w'] = describe([r['outcomes']['26'] for r in nonoverlapping])
    result['holding_longer'] = {}
    for a,b in ((4,12),(12,26)):
        result['holding_longer'][f'{a}_to_{b}'] = {
            "n": len(paired),
            "higher_return_pct": float(np.mean([r['outcomes'][str(b)]['return_pct'] > r['outcomes'][str(a)]['return_pct'] for r in paired])*100) if paired else None,
            "loss_to_gain_count": int(sum(r['outcomes'][str(a)]['return_pct'] < 0 < r['outcomes'][str(b)]['return_pct'] for r in paired)),
            "gain_to_loss_count": int(sum(r['outcomes'][str(a)]['return_pct'] > 0 > r['outcomes'][str(b)]['return_pct'] for r in paired)),
        }
    return result


def write_report(rows: list[dict], output: Path) -> dict:
    s = summarize(rows)
    (output/'summary.json').write_text(json.dumps(s, indent=2, allow_nan=False))
    coverage_note = ''
    if (output/'config.json').exists():
        config = json.loads((output/'config.json').read_text())
        absent = len(set(config['symbols']) - {r['symbol'] for r in rows})
        coverage_note = (f"Evaluation starts {config['start']}; data frozen at {config['as_of']}. "
                         f"{len(config['symbols'])} signal-universe symbols; {absent} have no eligible evaluation weeks. "
                         'See coverage.json for individual history ranges and input hashes. Zero network requests.')
    lines = ['# Soft-bottoming baseline', '', coverage_note, '',
             f"{s['episodes']} episode starts across {s['symbols_with_episodes']} symbols and {s['distinct_signal_weeks']} distinct weeks.", '',
             'Price returns, before dividends, fees, spread, slippage and taxes. Descriptive historical research, not a portfolio backtest or out-of-sample model result.', '',
             '| Horizon | Complete / pending / unusable | Positive | Beat VOO | Median return | Median excess | Median worst entry loss | Median close drawdown | Median annualized volatility |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for h,x in s['horizons'].items():
        if not x['n']: continue
        lines.append(f"| {h} weeks | {x['n']} / {x['pending']} / {x['unusable']} | {x['positive_pct']:.1f}% | {x['beat_benchmark_pct']:.1f}% | {x['median_return_pct']:.2f}% | {x['median_excess_pct']:.2f}% | {x['median_mae_pct']:.2f}% | {x['median_max_drawdown_pct']:.2f}% | {x['median_annualized_vol_pct']:.1f}% |")
    lines += ['', '## Same-cohort holding comparison', '',
              'Only episodes with all three completed outcomes appear here, avoiding different sample mixes.']
    for h,x in s['common_cohort'].items():
        if x['n']: lines.append(f"- {h} weeks: {x['n']} setups; median return {x['median_return_pct']:.2f}%; median worst entry loss {x['median_mae_pct']:.2f}%; median volatility {x['median_annualized_vol_pct']:.1f}%.")
    for pair,x in s['holding_longer'].items():
        if x['n']: lines.append(f"- {pair} weeks: {x['higher_return_pct']:.1f}% ended with a higher return; {x['loss_to_gain_count']} changed from loss to gain; {x['gain_to_loss_count']} changed from gain to loss.")
    n = s['nonoverlapping_26w']
    if n['n']:
        lines += ['', f"Sensitivity: keeping only one open 26-week episode per symbol leaves {n['n']} setups; median return {n['median_return_pct']:.2f}%, median excess {n['median_excess_pct']:.2f}%. Cross-symbol dependence remains."]
    lines += ['', '## Date-matched declining-stock comparison', '',
              'For each episode, average other eligible symbols on that date that are at least 10% below their 52-week high and do not have an active soft-bottoming signal. This controls date and broad decline condition, not sector, beta, volatility or decline severity. Reused controls and overlapping outcomes are dependent.']
    for h,x in s['horizons'].items():
        if x['matched_episodes']: lines.append(f"- {h} weeks: {x['matched_episodes']} matched episodes; mean return advantage {x['mean_return_advantage_vs_declining_controls_pct']:+.2f} percentage points. Equal weighting of {x['quarters_with_controls']} signal quarters: {x['equal_quarter_mean_advantage_pct']:+.2f} points.")
    lines += ['', '## Annual and market-condition breakdowns', '']
    for h,x in s['horizons'].items():
        lines.append(f'### {h} weeks')
        for group,d in {**x['by_year'], **x['by_regime']}.items():
            if d['n']: lines.append(f"- {group}: n={d['n']}, positive {d['positive_pct']:.1f}%, median return {d['median_return_pct']:+.2f}%, median excess {d['median_excess_pct']:+.2f}%.")
    lines += ['', '## Limits and decision', '',
              '- Current signal-role watch universe; survivorship and operator selection bias. No account balances, positions or trade history used.',
              '- Features use only completed historical weeks and the unchanged production detector, including its full available historical prefix. Cache vintage and adjusted-price revisions limit perfect point-in-time reconstruction.',
              '- First active week is an episode; a new episode can follow any inactive week. Episodes and cross-symbol market shocks remain correlated.',
              '- Benchmark-calendar gaps make outcomes unusable; no missing value is treated as a loss. Recent outcomes remain pending.',
              '- No thresholds were tuned. This five-year period is now exploratory and cannot subsequently be called an untouched test set.',
              '- No fitted model or claim of exploitable edge. Inspect time/regime stability and independent episode counts before choosing a model; reserve future observations or a separate untouched period for evaluation.',
              '- Chart-agent exposure: none. This is an offline research runner; it does not alter live signals, scans, forecasts, or agent tools.', '']
    (output/'report.md').write_text('\n'.join(lines))
    return s
