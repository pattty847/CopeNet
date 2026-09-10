"""Human-readable exploratory results, with sample counts and model ablations."""
import json
from pathlib import Path

from .model_eval import summarize_predictions


def write_model_report(predictions, folds, rows, output: Path):
    summary=summarize_predictions(predictions)
    (output/'model-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    (output/'folds.json').write_text(json.dumps(folds,indent=2))
    lines=['# Weekly soft-bottoming models with daily features','',
           f'{len(rows)} frozen weekly episodes. Primary target: beat VOO over 26 weeks; 12 and 52 weeks are secondary. Price returns exclude dividends and trading costs. No live signal changes.', '',
           'Models predict whether an episode beats VOO. Quarterly expanding training uses only outcomes that have fully finished before the test quarter. All symbols share temporal boundaries. Median imputation and scaling fit on training data only.', '',
           'The selection threshold is the training-score 67th percentile, fixed for the following quarter. This is not a hindsight top-third ranking of the test quarter. Scores are uncalibrated; AUC measures ranking, Brier measures squared probability error (lower is better). Prior Brier uses the training-only class frequency.', '',
           'Feature groups: weekly = existing compact weekly features and market condition; weekly_mama adds weekly MAMA/FAMA; daily_context adds daily return, volatility, RSI, ATR, volume and VOO-relative return; daily_mama adds daily MAMA/FAMA. Adjacent groups isolate incremental information.', '',
           '| Weeks | Features | Model | Evaluated | Selected | AUC | Brier / prior | All median excess | Selected median excess | Selected beat VOO | Selected worst entry loss¹ |',
           '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        a=r['all'];s=r['selected']
        if not a['n']:continue
        auc=f"{a['auc']:.3f}" if a['auc'] is not None else 'n/a'
        selected = f"{s['median_excess_pct']:+.2f}% | {s['beat_voo_pct']:.1f}% | {s['median_mae_pct']:.1f}%" if s['n'] else 'n/a | n/a | n/a'
        lines.append(f"| {r['horizon']} | {r['group']} | {r['model']} | {a['n']} | {s['n']} | {auc} | {a['brier']:.3f} / {a['prior_brier']:.3f} | {a['median_excess_pct']:+.2f}% | {selected} |")
    lines+=['','¹Median intraday loss relative to entry, not peak-to-trough drawdown. Excess returns are percentage-point differences from VOO.', '',
            '## Non-overlapping selected episodes', '',
            'Keep only one open selected setup per symbol for the relevant horizon. These remain correlated across stocks and market periods. This sensitivity is not a capital-constrained portfolio simulation.']
    for r in summary:
        s=r['selected_nonoverlap']
        if s['n']:lines.append(f"- {r['horizon']}w {r['group']} / {r['model']}: n={s['n']}, beat VOO {s['beat_voo_pct']:.1f}%, median excess {s['median_excess_pct']:+.2f}%, median drawdown {s['median_drawdown_pct']:.1f}%, median annualized volatility {s['median_vol_pct']:.1f}%.")
    lines+=['','## Quarter-by-quarter selection results','']
    for r in summary:
        if not r['all']['n']:continue
        lines.append(f"### {r['horizon']}w {r['group']} / {r['model']}")
        for q,x in r['quarters'].items():
            a=x['all'];s=x['selected']
            selected=f"{s['median_excess_pct']:+.2f}%" if s['n'] else 'n/a'
            lines.append(f"- {q}: {s['n']}/{a['n']} selected; all median excess {a['median_excess_pct']:+.2f}%; selected {selected}.")
    lines+=['','## Data and limits','',
            '- Reuses the frozen universe and price caches from the baseline. No Yahoo requests or account data. Some symbols have short histories; missing feature values remain missing until training-only imputation.',
            '- Weekly triggers remain unchanged. Daily slopes use 5/20 sessions; weekly slopes use 1/4 bars. MAMA/FAMA uses the production implementation: close, fast=0.5, slow=0.05, warmup=32. All features stop before the next signal week.',
            '- At least 40 matured training episodes, 20 distinct signal weeks and 10 examples per class are required. Every skipped fold is recorded in folds.json. Larger horizons have fewer usable folds.',
            '- Training gives each signal week equal total weight. Serial and cross-symbol dependence remains. Results do not have independent-observation confidence intervals.',
            '- Fixed logistic C=0.1; forest=200 trees, depth=3, minimum leaf=10, max_features=0.7, seed=17. No hyperparameter search, PCA or feature selection after looking at outcomes.',
            '- These years have already been inspected in the baseline: chronological out-of-training predictions are still exploratory, not a pristine external holdout. Comparing multiple feature sets/models/horizons also invites winner selection.',
            '- Selection can change stock, sector, market-date, beta and volatility exposure. Higher selected returns do not establish a timing edge. Calibration, costs, survival bias and current-universe selection remain unresolved.',
            '- No fitted model is promoted to production or presented as a live trading signal. A next step requires stability across quarters and genuinely new evaluation observations.',
            '- Exact predictions, thresholds, fold counts, features, outcomes and source hashes remain in this local run directory. Chart-agent exposure: none.', '']
    (output/'model-report.md').write_text('\n'.join(lines))
    return summary
