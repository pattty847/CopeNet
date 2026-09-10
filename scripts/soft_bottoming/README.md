# Soft-bottoming baseline experiment

An offline, descriptive calibration of the unchanged production weekly soft-bottoming detector. This is not a trading strategy, a trained model, or a replacement for the live replay API.

Run from the repository root:

```sh
uv run python -m scripts.soft_bottoming --output ~/.copenet/research/soft-bottoming/my-run
```

The output directory must not exist. The runner reads the current signal-role universe through `merge_watchlist_assets`, excluding public index/sector/macro context instruments, and reads VOO as the benchmark. It never downloads data or changes the live cache. Missing history is reported rather than fetched. Run artifacts contain the private watch universe and must stay outside version control.

To reproduce a run with its exact cached inputs, dates and universe:

```sh
uv run python -m scripts.soft_bottoming --from-run ~/.copenet/research/soft-bottoming/my-run --output ~/.copenet/research/soft-bottoming/reproduction
```

Artifacts:

- `config.json`: scope, dates, execution convention, source hashes and Git revision.
- `coverage.json`: symbol-level coverage, cache timestamps and SHA-256 hashes.
- `inputs/`: frozen canonical split-only daily price caches. No account or watchlist documents.
- `observations.jsonl`: each eligible week, its historical features, episode flag and separate outcomes.
- `summary.json`, `report.md`: full-sample, common-cohort, year/regime and control comparisons.

## Fixed protocol

- Five evaluation years by default; all available earlier history warms the existing feature extractor. At least 44 aligned weekly bars are required. No padding of recent listings.
- Features receive only their historical stock and VOO prefixes. Completed calendar weeks only; cache timestamps also prevent treating an old partial week as complete. Weekly dates are Monday labels, not information-availability dates.
- One episode on inactive-to-active transition. The preceding week establishes state at the evaluation boundary. An inactive week rearms the detector; episodes can still overlap. A separate sensitivity keeps only one open 26-week episode per symbol.
- Entry is the first VOO-calendar session open after the signal week. Exit is the final session close strictly before entry plus 4, 12 or 26 calendar weeks. No signal-close execution.
- Daily price returns exclude dividends and execution costs. MAE is the worst intraday low relative to entry; maximum drawdown uses the entry and subsequent closes. Annualized volatility uses daily close returns, with the first return measured from entry open.
- Recovery means the first close at or above entry after an underwater close. This is not recovery from the maximum drawdown, and a recovered setup can lose again.
- Pending outcomes remain pending. Missing outcome sessions relative to VOO are unusable, not failures. This does not establish vendor completeness or historical ticker membership.
- Controls are other eligible, non-signal symbols on the same date, at least 10% below their 52-week high. Each episode is compared with that control group's mean return. Signal-quarter equal weighting is a sensitivity, not an independence correction or confidence interval.
- Market condition is VOO above/below its trailing 40-week average at the signal date. No future regime information.
- No parameter optimization, ML fitting, significance claims or automatic promotion. These inspected years become exploratory data. Any later model needs a declared temporal validation design and genuinely untouched evaluation observations.

The report cannot establish causality or an exploitable edge. Current-universe survivorship/selection bias, adjusted vendor revisions, correlated market episodes and omitted execution costs remain material limits. Benchmarks are not risk-matched. Long-horizon price returns naturally embed more market exposure.

Chart-agent exposure: none. No UI, RPC, live signal, scan, forecast or tool behavior changes; no server restart is needed for this standalone script.

Verification:

```sh
uv run --extra dev pytest -q tests/unit/test_soft_bottoming_experiment.py
```

## Exploratory model comparison

```sh
uv run python -m scripts.soft_bottoming.models --from-run ~/.copenet/research/soft-bottoming/my-run --output ~/.copenet/research/soft-bottoming/my-model-run
```

Requires installed frontend dependencies (`tsx`) and scikit-learn. Reuses the frozen episode scope and inputs; no new acquisition. Model outcomes are 12/26/52 weeks with 26 primary. The original 4/12/26 baseline remains a separate descriptive experiment.

`mama.ts` invokes the exact chart calculation with its default close/0.5/0.05/32 settings. The bridge validates the native `IndicatorBar` contract. Weekly slopes use 1/4 bars and daily slopes use 5/20 sessions. Slopes and gaps are normalized by current price; one gap is divided by ATR. Crossover age is in bars of the respective timeframe, and is missing until a crossover has been observed.

Four fixed feature sets isolate weekly MAMA/FAMA, daily context and daily MAMA/FAMA additions. Regularized logistic regression and a constrained random forest fit expanding quarterly folds; training labels must finish before each test quarter. Training-only imputation/scaling, minimum sample/class counts and fixed training-score selection thresholds are recorded with the run. Each signal week has equal total training weight. Pending outcomes are excluded from evaluation, not classified as failures.

Reports include AUC, probability-error comparisons against the training-only class prior, selection counts, VOO-relative returns, drawdown, volatility, per-quarter results and one-open-selected-episode-per-symbol sensitivity. Feature missingness is explicit in `feature-quality.json`. Predictions and thresholds are inspectable in `predictions.jsonl`; source and input hashes are recorded in `config.json` and `coverage.json`.

This is an exploratory ablation study, with no tuned hyperparameters, deployed models, significance claims or pristine holdout. Predictions are out of their training periods, but the baseline already exposed the period to researcher inspection. Compare models on the same horizon/folds, inspect quarter stability and avoid declaring the best historical combination a discovered edge.
