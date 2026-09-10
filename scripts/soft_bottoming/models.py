"""Fit fixed exploratory models from an existing frozen baseline, entirely offline."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import sklearn

from copenet.core.market.price_cache import PriceCache
from .experiment import snapshot
from .model_features import GROUPS, engineer, indicator_series
from .model_eval import HORIZONS, evaluate
from .model_report import write_model_report
from .outcomes import measure_outcome


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prior=json.loads((args.from_run/'config.json').read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    sources=[*Path('scripts/soft_bottoming').glob('*.py'),*Path('scripts/soft_bottoming').glob('*.ts'),
             *Path('src/copenet/host/frontend/src/sections/market/indicators').rglob('*.ts')]
    config={**prior,'horizons_weeks':list(HORIZONS),'primary_horizon':26,'feature_groups':GROUPS,
            'sklearn_version':sklearn.__version__,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'baseline_observations_sha256':hashlib.sha256((args.from_run/'observations.jsonl').read_bytes()).hexdigest(),
            'protocol':{'quarterly_expanding':True,'minimum_train':40,'minimum_train_weeks':20,'minimum_class':10,
                        'label':'excess_pct > 0','threshold':'training score quantile 2/3','logistic_C':0.1,
                        'forest_trees':200,'forest_depth':3,'forest_min_leaf':10,'forest_max_features':0.7,'seed':17}}
    (args.output/'config.json').write_text(json.dumps(config,indent=2))
    asof=pd.Timestamp(prior['as_of']);cutoff=asof.tz_convert('America/New_York').tz_localize(None).normalize()
    daily,weekly=snapshot(PriceCache(args.from_run/'inputs'),prior['symbols'],args.output,asof)
    series=indicator_series(daily,weekly,args.output)
    rows=[]
    for line in (args.from_run/'observations.jsonl').read_text().splitlines():
        r=json.loads(line)
        if not r['episode']:continue
        r['engineered']=engineer(r,daily,weekly,series)
        r['outcomes']={str(h):measure_outcome(daily[r['symbol']],daily['VOO'],pd.Timestamp(r['signal_week']),h,cutoff) for h in HORIZONS}
        rows.append(r)
    quality={c:{'missing':sum(r['engineered'][c] is None for r in rows),
                'distinct':len({r['engineered'][c] for r in rows if r['engineered'][c] is not None})}
             for c in GROUPS['daily_mama']}
    (args.output/'feature-quality.json').write_text(json.dumps(quality,indent=2))
    (args.output/'model-episodes.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    print(f'Engineered {len(rows)} episodes; fitting fixed models',flush=True)
    predictions,folds=evaluate(rows)
    (args.output/'predictions.jsonl').write_text(''.join(json.dumps(p,allow_nan=False)+'\n' for p in predictions))
    write_model_report(predictions,folds,rows,args.output)
    print(f"Report: {args.output/'model-report.md'}",flush=True)


if __name__=='__main__':main()
