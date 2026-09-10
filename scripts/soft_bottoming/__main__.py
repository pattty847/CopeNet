"""Run with uv run python -m scripts.soft_bottoming; never performs network I/O."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from copenet.core.market.price_cache import PriceCache
from copenet.core.market.universe import SIGNAL_ROLES, merge_watchlist_assets
from copenet.core.market.watchlist_store import WatchlistStore
from .experiment import replay, snapshot
from .report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market-dir', type=Path, default=Path.home()/'.copenet/market')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', default=pd.Timestamp.now(tz='UTC').isoformat())
    parser.add_argument('--years', type=int, default=5)
    parser.add_argument('--from-run', type=Path, help='Replay the frozen inputs and scope of an earlier run')
    args = parser.parse_args()
    if args.years < 1: parser.error('--years must be positive')
    prior = json.loads((args.from_run/'config.json').read_text()) if args.from_run else None
    as_of = pd.Timestamp(prior['as_of'] if prior else args.as_of)
    if as_of.tzinfo is None: parser.error('--as-of must include a timezone')
    args.output.mkdir(parents=True, exist_ok=False)
    if prior:
        symbols = prior['symbols']
    else:
        assets = merge_watchlist_assets(WatchlistStore(args.market_dir/'watchlist.json').scan_lists())
        symbols = sorted(a.symbol for a in assets if a.role in SIGNAL_ROLES)
    cutoff = as_of.tz_convert('America/New_York').tz_localize(None).normalize()
    start = pd.Timestamp(prior['start']) if prior else cutoff - pd.DateOffset(years=args.years)
    config = {"as_of": as_of.isoformat(), "start": str(start.date()), "symbols": symbols,
              "horizons_weeks": [4,12,26], "benchmark": "VOO", "network_requests": 0,
              "feature_minimum_weeks": 44, "entry": "next session open", "price_basis": "split_adjusted",
              "git_commit": subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()}
    config["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [*Path("scripts/soft_bottoming").glob("*.py"),
                                         Path("src/copenet/core/market/features.py"),
                                         Path("src/copenet/core/market/price_history.py")]}
    (args.output/'config.json').write_text(json.dumps(config, indent=2))
    source = args.from_run/'inputs' if prior else args.market_dir/'prices'
    daily, weekly = snapshot(PriceCache(source), symbols, args.output, as_of)
    if 'VOO' not in daily: raise RuntimeError('VOO cache is required; no automatic download')
    result = replay(daily, weekly, symbols, start, cutoff, args.output)
    summary = write_report(result, args.output)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('horizons','common_cohort')}, indent=2))
    print(f'Report: {args.output / "report.md"}')


if __name__ == '__main__': main()
