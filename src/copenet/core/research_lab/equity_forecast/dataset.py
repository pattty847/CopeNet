"""Point-in-time dataset construction over canonical filings and daily prices."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from copenet.core.market.financials import get_financial_series
from copenet.core.market.price_cache import PriceCache, PriceHistory
from copenet.core.market.price_history import DAILY, SPLIT_ADJUSTED, TOTAL_RETURN, bar_date

from .contracts import ExperimentConfig
from .features import FUNDAMENTAL_FEATURES, FUNDAMENTAL_SERIES, derive_fundamental_features, safe_ratio
from .targets import forward_targets, market_features, price_before


FinancialLoader = Callable[..., Awaitable[dict[str, Any] | None]]


def series_from_history(history: PriceHistory, *, basis: str) -> pd.Series:
    bars = history.derive(timeframe=DAILY, basis=basis)
    return pd.Series([float(bar.c) for bar in bars], index=pd.to_datetime([bar_date(bar) for bar in bars])).sort_index()


def prediction_anchors(trading_days: pd.DatetimeIndex, start_year: int, end_year: int) -> list[date]:
    anchors: list[date] = []
    for year in range(start_year, end_year + 1):
        for month in (2, 5, 8, 11):
            target = date(year, month, 15)
            eligible = trading_days[trading_days.date >= target]
            if len(eligible):
                anchors.append(eligible[0].date())
    return anchors


def _provenance(series: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    filings: dict[str, dict[str, Any]] = {}
    for rows in series.values():
        for row in rows:
            source = row.get("availabilitySource") or {}
            accession = source.get("accessionNumber")
            if accession:
                filings[str(accession)] = {
                    "accession": str(accession),
                    "filed_date": source.get("filed") or row.get("availableAt"),
                    "form": source.get("form"),
                    "source_url": source.get("sourceUrl"),
                }
    return sorted(filings.values(), key=lambda item: (str(item["filed_date"]), item["accession"]))


async def load_financial_snapshot(
    symbol: str,
    cutoff: date,
    *,
    refresh: bool,
    loader: FinancialLoader = get_financial_series,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    series: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for metric, frequency in FUNDAMENTAL_SERIES.items():
        payload = await loader(
            symbol=symbol,
            metric=metric,
            frequency=frequency,
            basis="canonical",
            alignment="availability",
            as_of=cutoff.isoformat(),
            refresh=refresh,
            include_provenance=True,
        )
        observations = list((payload or {}).get("observations") or [])
        for row in observations:
            available = pd.to_datetime(row.get("availableAt"), errors="coerce")
            if pd.isna(available) or available.date() > cutoff:
                raise ValueError(f"future financial observation for {symbol}/{metric} at {cutoff}")
        series[metric] = observations
        warnings.extend(str(item) for item in (payload or {}).get("warnings") or [])
    return series, sorted(set(warnings))


async def build_dataset(
    config: ExperimentConfig,
    *,
    price_cache: PriceCache,
    loader: FinancialLoader = get_financial_series,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    histories: dict[str, PriceHistory] = {}
    for symbol in (*config.symbols, config.benchmark):
        history = await asyncio.to_thread(price_cache.refresh, symbol, force=config.refresh)
        if history is None:
            raise ValueError(f"no price history for {symbol}")
        histories[symbol] = history
    split_prices = {symbol: series_from_history(history, basis=SPLIT_ADJUSTED) for symbol, history in histories.items()}
    total_returns = {symbol: series_from_history(history, basis=TOTAL_RETURN) for symbol, history in histories.items()}
    anchors = prediction_anchors(total_returns[config.benchmark].index, config.start_year, config.end_year)
    rows: list[dict[str, Any]] = []
    quality: dict[str, Any] = {
        symbol: {
            "historical_start_date": total_returns[symbol].index[0].date().isoformat(),
            "price_history_end": total_returns[symbol].index[-1].date().isoformat(),
            "prediction_observations": 0,
            "excluded_observations": 0,
            "exclusion_reasons": {},
            "filings_used": set(),
            "warnings": set(),
            "series_coverage": {},
        }
        for symbol in config.symbols
    }
    for anchor in anchors:
        cutoff = anchor - timedelta(days=1)
        benchmark_target = total_returns[config.benchmark]
        for symbol in config.symbols:
            target = forward_targets(total_returns[symbol], benchmark_target, anchor)
            if target is None:
                reason = "missing_12m_target_price"
                quality[symbol]["excluded_observations"] += 1
                quality[symbol]["exclusion_reasons"][reason] = quality[symbol]["exclusion_reasons"].get(reason, 0) + 1
                continue
            financial_series, warnings = await load_financial_snapshot(symbol, cutoff, refresh=config.refresh, loader=loader)
            for metric, observations in financial_series.items():
                if not observations:
                    continue
                periods = [str(row.get("periodEnd")) for row in observations if row.get("periodEnd")]
                if not periods:
                    continue
                coverage = quality[symbol]["series_coverage"].setdefault(metric, {"start": min(periods), "end": max(periods), "observations": 0})
                coverage["start"] = min(coverage["start"], min(periods))
                coverage["end"] = max(coverage["end"], max(periods))
                coverage["observations"] = max(coverage["observations"], len(observations))
            features = derive_fundamental_features(financial_series)
            features.update(market_features(total_returns[symbol], anchor))
            eps_rows = financial_series.get("diluted_eps", [])
            latest_eps = None if not eps_rows else float(max(eps_rows, key=lambda row: (str(row.get("periodEnd")), str(row.get("availableAt"))))["value"])
            prior_price = price_before(split_prices[symbol], anchor)
            features["trailing_pe"] = safe_ratio(prior_price[1] if prior_price else None, latest_eps if latest_eps and latest_eps > 0 else None)
            filings = _provenance(financial_series)
            missing = sum(features.get(name) is None for name in features)
            quality[symbol]["prediction_observations"] += 1
            quality[symbol]["filings_used"].update(item["accession"] for item in filings)
            quality[symbol]["warnings"].update(warnings)
            prediction_time = pd.Timestamp(anchor).replace(hour=16, minute=0, tzinfo=ZoneInfo("America/New_York"))
            cutoff_time = pd.Timestamp(cutoff).replace(hour=23, minute=59, second=59, tzinfo=ZoneInfo("America/New_York"))
            for months in (6, 12, 24):
                target_key = f"target_end_{months}m"
                if target_key in target:
                    target[target_key] = pd.Timestamp(target[target_key]).replace(hour=16, tzinfo=ZoneInfo("America/New_York")).isoformat()
            rows.append({
                "ticker": symbol,
                "prediction_timestamp": prediction_time.isoformat(),
                "knowledge_cutoff": cutoff_time.isoformat(),
                **features,
                **target,
                "holding_period_return": None,
                "benchmark_holding_period_return": None,
                "holding_period_end": None,
                "missing_feature_count": missing,
                "filings": filings,
                "financial_warnings": warnings,
                "market_data_timestamp": prior_price[0].date().isoformat() if prior_price else None,
            })
    frame = pd.DataFrame(rows).sort_values(["prediction_timestamp", "ticker"]).reset_index(drop=True)
    next_period = dict(zip(anchors, anchors[1:]))
    for index, row in frame.iterrows():
        anchor = pd.Timestamp(row["prediction_timestamp"]).date()
        end = next_period.get(anchor)
        if end is None:
            continue
        stock_return = forward_targets(total_returns[row["ticker"]], benchmark_target, anchor)
        stock_entry = total_returns[row["ticker"]][total_returns[row["ticker"]].index.date >= anchor].iloc[0]
        stock_exit = total_returns[row["ticker"]][total_returns[row["ticker"]].index.date >= end].iloc[0]
        bench_entry = benchmark_target[benchmark_target.index.date >= anchor].iloc[0]
        bench_exit = benchmark_target[benchmark_target.index.date >= end].iloc[0]
        frame.at[index, "holding_period_return"] = float(stock_exit / stock_entry - 1.0)
        frame.at[index, "benchmark_holding_period_return"] = float(bench_exit / bench_entry - 1.0)
        frame.at[index, "holding_period_end"] = pd.Timestamp(end).replace(hour=16, tzinfo=ZoneInfo("America/New_York")).isoformat()
    for symbol, report in quality.items():
        report["filings_used"] = len(report["filings_used"])
        report["warnings"] = sorted(report["warnings"])
        symbol_rows = frame[frame["ticker"] == symbol]
        report["missing_feature_pct"] = float(symbol_rows[list(FUNDAMENTAL_FEATURES)].isna().mean().mean()) if not symbol_rows.empty else 1.0
        report["corporate_action_issues"] = "Share-count growth omitted because historical shares are not normalized across splits."
    return frame, quality
