#!/usr/bin/env python3
"""Reproduce the CopeNet baseline equity forecast experiment."""

from __future__ import annotations

import argparse
import asyncio

from copenet.core.research_lab.equity_forecast import ExperimentConfig, run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"])
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--minimum-training-rows", type=int, default=20)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=847)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root")
    parser.add_argument("--snapshot", help="Replay a frozen dataset.jsonl without SEC/Yahoo access")
    args = parser.parse_args()
    run_dir = asyncio.run(run_experiment(ExperimentConfig(
        symbols=tuple(symbol.upper() for symbol in args.symbols), benchmark=args.benchmark.upper(),
        start_year=args.start_year, end_year=args.end_year,
        minimum_training_rows=args.minimum_training_rows,
        transaction_cost_bps=args.transaction_cost_bps, random_seed=args.seed,
        refresh=args.refresh, output_root=args.output_root, snapshot_path=args.snapshot,
    )))
    print(run_dir)


if __name__ == "__main__":
    main()
