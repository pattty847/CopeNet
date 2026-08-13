"""Orchestrate collection, walk-forward fitting, ledgers, and reports."""

from __future__ import annotations

import json
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import sklearn

from copenet._paths import default_sessions_dir
from copenet.core.market.financials import supported_financial_metrics
from copenet.core.market.price_cache import PriceCache

from .contracts import EXPERIMENT_VERSION, ExperimentConfig, ForecastRecord
from .dataset import build_dataset
from .evaluate import static_strategy_controls
from .features import FEATURE_SETS, FUNDAMENTAL_SERIES
from .ledger import content_hash, write_exclusive_json, write_exclusive_jsonl
from .report import render_report
from .walk_forward import walk_forward


def default_output_root() -> Path:
    return default_sessions_dir().parent / "research" / "equity_forecast"


def metric_inventory(data_quality: dict[str, Any]) -> list[dict[str, Any]]:
    selected = set(FUNDAMENTAL_SERIES) | {"trailing_pe"}
    inventory = []
    for metric in supported_financial_metrics():
        metric_id = str(metric["id"])
        coverage = {
            symbol: report.get("series_coverage", {}).get(metric_id, "unavailable")
            for symbol, report in data_quality.items()
        }
        if metric_id in selected:
            reason = "selected for an economically comparable V1 feature or target-safe valuation"
        elif metric.get("factType") == "valuation":
            reason = "excluded because the existing weekly valuation wrapper is not safe for historical daily cutoffs; V1 reconstructs trailing P/E from the prior close only"
        elif metric_id in {"diluted_shares", "shares_outstanding", "revenue_per_share"}:
            reason = "excluded because historical share series are not normalized across stock splits"
        else:
            reason = "excluded to avoid raw-scale, redundant, or weakly covered inputs in the deliberately small V1 feature set"
        inventory.append({
            "name": metric_id,
            "source": "SEC Company Facts" if metric.get("factType") != "valuation" else "SEC Company Facts + split-adjusted daily price",
            "historical_coverage": coverage,
            "usable_for_model": metric_id in selected,
            "reason": reason,
        })
    return inventory


def summarize_contributions(contributions: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for feature_set, models in contributions.items():
        for model_name, folds in models.items():
            by_feature: dict[str, list[float]] = {}
            for fold in folds:
                for name, value in fold["values"].items():
                    by_feature.setdefault(name, []).append(float(value))
            if not by_feature:
                continue
            rows = []
            for name, values in by_feature.items():
                positives = sum(value > 0 for value in values)
                negatives = sum(value < 0 for value in values)
                rows.append({
                    "feature": name,
                    "mean": sum(values) / len(values),
                    "mean_absolute": sum(abs(value) for value in values) / len(values),
                    "sign_consistency": max(positives, negatives) / len(values),
                    "folds": len(values),
                })
            summary[f"{feature_set}:{model_name}"] = sorted(
                rows, key=lambda item: (-item["mean_absolute"], item["feature"])
            )
    return summary


def _ledger_rows(predictions: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in predictions.iterrows():
        feature_names = FEATURE_SETS[str(row["feature_set"])]
        actual = float(row["excess_return_12m"])
        predicted = float(row["predicted"])
        prediction_id = f"{row['ticker']}_{str(row['prediction_timestamp'])[:10]}_{row['model']}_{row['feature_set']}_v1"
        record = ForecastRecord(
            prediction_id=prediction_id,
            ticker=str(row["ticker"]),
            prediction_timestamp=str(row["prediction_timestamp"]),
            knowledge_cutoff=str(row["knowledge_cutoff"]),
            model={"type": row["model"], "version": "v1", "feature_set": row["feature_set"], "training_rows": int(row["training_rows"])},
            features={name: None if pd.isna(row[name]) else float(row[name]) for name in feature_names},
            prediction={"expected_12m_excess_return": predicted},
            actual={
                **{
                    f"stock_{months}m_return": float(row[f"forward_return_{months}m"])
                    for months in (6, 24)
                    if pd.notna(row.get(f"forward_return_{months}m"))
                },
                **{
                    f"benchmark_{months}m_return": float(row[f"benchmark_forward_return_{months}m"])
                    for months in (6, 24)
                    if pd.notna(row.get(f"benchmark_forward_return_{months}m"))
                },
                **{
                    f"excess_return_{months}m": float(row[f"excess_return_{months}m"])
                    for months in (6, 24)
                    if pd.notna(row.get(f"excess_return_{months}m"))
                },
                "stock_12m_return": float(row["forward_return_12m"]),
                "benchmark_12m_return": float(row["benchmark_forward_return_12m"]),
                "excess_return_12m": actual,
            },
            error={"absolute_error": abs(predicted - actual), "direction_correct": (predicted >= 0) == (actual >= 0)},
            provenance={"filings": row["filings"], "market_data_timestamp": row["market_data_timestamp"]},
        )
        rows.append(record.to_json())
    return rows


async def run_experiment(config: ExperimentConfig) -> Path:
    root = Path(config.output_root).expanduser() if config.output_root else default_output_root()
    if config.snapshot_path:
        snapshot_path = Path(config.snapshot_path).expanduser()
        snapshot_records = [json.loads(line) for line in snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        dataset = pd.DataFrame(snapshot_records)
        manifest_path = snapshot_path.parent / "manifest.json"
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        data_quality = source_manifest.get("data_quality", {})
    else:
        price_cache = PriceCache(default_sessions_dir().parent / "market" / "prices")
        dataset, data_quality = await build_dataset(config, price_cache=price_cache)
    dataset_records = dataset.to_dict(orient="records")
    snapshot_hash = content_hash(dataset_records)
    analysis_hash = content_hash({"experiment_version": EXPERIMENT_VERSION, "dataset_sha256": snapshot_hash, "config": config.to_json()})
    run_id = f"{EXPERIMENT_VERSION}-{analysis_hash[:12]}"
    run_dir = root / run_id
    if run_dir.exists():
        raise FileExistsError(f"immutable experiment run already exists: {run_dir}")
    predictions, results, contributions = walk_forward(
        dataset,
        minimum_training_rows=config.minimum_training_rows,
        seed=config.random_seed,
        cost_bps=config.transaction_cost_bps,
    )
    contribution_summary = summarize_contributions(contributions)
    first_evaluated = str(predictions["prediction_timestamp"].min())
    controls = static_strategy_controls(dataset, start_timestamp=first_evaluated, cost_bps=config.transaction_cost_bps)
    manifest = {
        "experiment_version": EXPERIMENT_VERSION,
        "run_id": run_id,
        "config": config.to_json(),
        "coverage": {
            "dataset_start": str(dataset["prediction_timestamp"].min())[:10],
            "dataset_end": str(dataset["prediction_timestamp"].max())[:10],
            "evaluation_start": str(predictions["prediction_timestamp"].min())[:10],
            "evaluation_end": str(predictions["prediction_timestamp"].max())[:10],
            "rows": len(dataset),
            "out_of_sample_predictions_per_configuration": int(predictions.groupby(["feature_set", "model"]).size().min()),
        },
        "timing_policy": "prior-calendar-day filing embargo; per-cutoff as_of resolution; target end strictly before training prediction time",
        "dataset_sha256": snapshot_hash,
        "versions": {"python": platform.python_version(), "pandas": pd.__version__, "scikit_learn": sklearn.__version__},
        "data_quality": data_quality,
        "strategy_controls": controls,
        "universe_notes": {
            "selection": "Hand-picked present-day mega-cap survivors; not a point-in-time historical universe.",
            "replacement": "XOM was attempted first and replaced before accepting results because its canonical SEC pipeline returned zero filing provenance and 100% missing fundamentals. NVDA was selected from pre-result coverage probes because it had usable point-in-time filing history.",
        },
    }
    run_dir.mkdir(parents=True)
    write_exclusive_jsonl(run_dir / "dataset.jsonl", dataset_records)
    write_exclusive_jsonl(run_dir / "predictions.jsonl", _ledger_rows(predictions))
    predictions.drop(columns=["filings", "financial_warnings"], errors="ignore").to_csv(run_dir / "predictions.csv", index=False)
    write_exclusive_json(run_dir / "manifest.json", manifest)
    write_exclusive_json(run_dir / "metrics.json", results)
    write_exclusive_json(run_dir / "feature_importance.json", contributions)
    write_exclusive_json(run_dir / "feature_importance_summary.json", contribution_summary)
    write_exclusive_json(run_dir / "series_inventory.json", metric_inventory(data_quality))
    (run_dir / "REPORT.md").write_text(
        render_report(manifest, results, contribution_summary), encoding="utf-8"
    )
    return run_dir
