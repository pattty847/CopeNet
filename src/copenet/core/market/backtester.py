"""Portfolio backtesting and macro scenario simulation logic."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .data_sources import fetch_ohlcv
from .models import MarketBar
from .store import MarketStore


@dataclass
class BacktestResult:
    """Standardized backtest execution DTO."""

    portfolio_series: list[dict[str, Any]]
    benchmark_series: list[dict[str, Any]]
    metrics: dict[str, float]
    metadata: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "portfolioSeries": self.portfolio_series,
            "benchmarkSeries": self.benchmark_series,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


SCENARIOS = {
    "2022_tech_dump": {
        "name": "2022 Tech Dump",
        "duration_weeks": 52,
        "shocks": [
            {"symbol_or_sector": "XLK", "magnitude_pct": -33.0},
            {"symbol_or_sector": "GOOG", "magnitude_pct": -39.0},
            {"symbol_or_sector": "VOO", "magnitude_pct": -19.0},
            {"symbol_or_sector": "SOFI", "magnitude_pct": -60.0},
            {"symbol_or_sector": "SLI", "magnitude_pct": -70.0},
        ],
    },
    "2020_covid_crash": {
        "name": "2020 Covid Crash",
        "duration_weeks": 5,
        "shocks": [
            {"symbol_or_sector": "VOO", "magnitude_pct": -34.0},
            {"symbol_or_sector": "XLK", "magnitude_pct": -30.0},
            {"symbol_or_sector": "GOOG", "magnitude_pct": -28.0},
            {"symbol_or_sector": "VTI", "magnitude_pct": -35.0},
            {"symbol_or_sector": "SOFI", "magnitude_pct": -50.0},
            {"symbol_or_sector": "SLI", "magnitude_pct": -55.0},
        ],
    },
}

TECH_SYMBOLS = {"GOOG", "XLK", "NVDA", "TSLA", "AMZN", "INTC", "SOX", "SMH", "CRWV"}


def _to_float(value: Any) -> float:
    """Positions can come from the dashboard's display-formatted Portfolio wire (PortfolioPosition
    .last is a str like "$2.78", not a raw float) as well as from plain numeric input (e.g. an LLM
    tool call). Parse both rather than assuming the caller always sends a clean float."""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    cleaned = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ---------- Metrics Calculation (Plain Functions) ----------


def calculate_max_drawdown(nav_series: pd.Series) -> float:
    """Calculate the maximum drawdown percentage of a NAV series."""
    if nav_series.empty:
        return 0.0
    peaks = nav_series.cummax()
    drawdowns = (nav_series - peaks) / peaks
    min_dd = float(drawdowns.min())
    return round(min_dd * 100, 2)


def calculate_volatility(nav_series: pd.Series) -> float:
    """Calculate annualized daily volatility percentage."""
    if len(nav_series) < 2:
        return 0.0
    returns = nav_series.pct_change().dropna()
    daily_vol = returns.std()
    annualized_vol = daily_vol * (252**0.5)
    return round(float(annualized_vol) * 100, 2)


def calculate_sharpe(nav_series: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calculate Sharpe ratio (annualized, excess return / annualized volatility)."""
    if len(nav_series) < 2:
        return 0.0
    returns = nav_series.pct_change().dropna()
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess = returns - daily_rf
    mean_excess = excess.mean()
    std_dev = returns.std()
    if std_dev == 0:
        return 0.0
    daily_sharpe = mean_excess / std_dev
    annualized_sharpe = daily_sharpe * (252**0.5)
    return round(float(annualized_sharpe), 2)


def calculate_beta_and_correlation(portfolio_nav: pd.Series, benchmark_nav: pd.Series) -> tuple[float, float]:
    """Calculate portfolio beta and correlation vs benchmark."""
    p_returns = portfolio_nav.pct_change().dropna()
    b_returns = benchmark_nav.pct_change().dropna()
    common_idx = p_returns.index.intersection(b_returns.index)
    if len(common_idx) < 2:
        return 0.0, 0.0
    p = p_returns.loc[common_idx]
    b = b_returns.loc[common_idx]
    b_var = b.var()
    if b_var == 0:
        return 0.0, 0.0
    covariance = p.cov(b)
    beta = covariance / b_var
    correlation = p.corr(b)
    if math.isnan(beta):
        beta = 0.0
    if math.isnan(correlation):
        correlation = 0.0
    return round(beta, 2), round(correlation, 2)


# ---------- Data Fetching & Caching ----------


def get_daily_close_series(symbol: str, start_date: str, end_date: str, store: MarketStore | None) -> pd.Series:
    """Get aligned daily closing prices, utilizing the MarketStore cache."""
    normalized = symbol.strip().upper()
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # 1. Try cache
    bars = store.load_bars(normalized, "daily") if store else []
    if bars:
        dates = [pd.to_datetime(bar.t, unit="s") for bar in bars]
        closes = [bar.c for bar in bars]
        series = pd.Series(closes, index=dates)
        if series.index.min() <= start_dt and series.index.max() >= end_dt:
            return series[start_dt:end_dt].sort_index()

    # 2. Fetch live (split-adjusted: auto_adjust=True)
    df = fetch_ohlcv(normalized, interval="1d", period="max", auto_adjust=True)
    if df.empty:
        raise ValueError(f"No price data found for {normalized}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    series = df["close"].astype(float)

    # Cache the full historical download in MarketStore for future queries
    if store:
        new_bars = []
        for dt, row in df.iterrows():
            t_val = int(dt.timestamp())
            new_bars.append(
                MarketBar(
                    t=t_val,
                    o=float(row["open"]),
                    h=float(row["high"]),
                    l=float(row["low"]),
                    c=float(row["close"]),
                    v=int(row["volume"]),
                )
            )
        store.save_bars(normalized, "daily", new_bars)

    # Slice to requested date range
    sliced = series[start_dt:end_dt]
    if sliced.empty:
        # Fall back to nearest available dates if index boundary is tight
        sliced = series.reindex(pd.date_range(start_dt, end_dt)).ffill().bfill().dropna()
    return sliced


# ---------- Main Engines ----------


def run_portfolio_backtest(
    symbols: list[str],
    weights: list[float],
    start_date: str,
    end_date: str,
    benchmark: str = "VOO",
    rebalance: str = "buy_and_hold",
    rebalance_interval: str | None = None,
    initial_capital: float = 100000.0,
    store: MarketStore | None = None,
) -> BacktestResult:
    """Run portfolio backtesting using cached or live-fetched data."""
    if len(symbols) != len(weights):
        raise ValueError("Number of symbols must match number of weights")
    if abs(sum(weights) - 1.0) > 1e-4:
        # Normalize weights if they don't sum to 1.0 exactly
        total = sum(weights)
        weights = [w / total for w in weights]

    # Load daily closes
    closes_df = pd.DataFrame()
    for symbol in symbols:
        closes_df[symbol] = get_daily_close_series(symbol, start_date, end_date, store)
    bench_series = get_daily_close_series(benchmark, start_date, end_date, store)

    # Align dates with benchmark index
    closes_df = closes_df.ffill().bfill()
    closes_df = closes_df.reindex(bench_series.index).ffill().bfill()

    # Rebalance simulation loop
    current_value = initial_capital
    shares = [0.0] * len(symbols)
    prices_on_day = closes_df.iloc[0]
    for i, symbol in enumerate(symbols):
        shares[i] = (current_value * weights[i]) / prices_on_day[symbol]

    nav_list = []
    last_rebalance_date = closes_df.index[0]

    for date, row in closes_df.iterrows():
        day_nav = sum(shares[i] * row[symbol] for i, symbol in enumerate(symbols))

        # Check if periodic rebalance is triggered
        if rebalance == "periodic" and date != closes_df.index[0]:
            should_rebalance = False
            if rebalance_interval == "daily":
                should_rebalance = True
            elif rebalance_interval == "weekly":
                if date.isocalendar().week != last_rebalance_date.isocalendar().week:
                    should_rebalance = True
            elif rebalance_interval == "monthly":
                if date.month != last_rebalance_date.month:
                    should_rebalance = True

            if should_rebalance:
                for i, symbol in enumerate(symbols):
                    shares[i] = (day_nav * weights[i]) / row[symbol]
                last_rebalance_date = date

        nav_list.append(day_nav)

    portfolio_nav = pd.Series(nav_list, index=closes_df.index)

    # Calculate metrics
    tot_ret = ((portfolio_nav.iloc[-1] / portfolio_nav.iloc[0]) - 1) * 100
    bench_tot_ret = ((bench_series.iloc[-1] / bench_series.iloc[0]) - 1) * 100

    max_dd = calculate_max_drawdown(portfolio_nav)
    bench_max_dd = calculate_max_drawdown(bench_series)

    vol = calculate_volatility(portfolio_nav)
    bench_vol = calculate_volatility(bench_series)

    sharpe = calculate_sharpe(portfolio_nav)
    bench_sharpe = calculate_sharpe(bench_series)

    beta, corr = calculate_beta_and_correlation(portfolio_nav, bench_series)

    # Normalize outputs for wire
    portfolio_series = [
        {"date": date.strftime("%Y-%m-%d"), "value": round(val, 2)}
        for date, val in portfolio_nav.items()
    ]
    benchmark_series = [
        {"date": date.strftime("%Y-%m-%d"), "value": round((val / bench_series.iloc[0]) * initial_capital, 2)}
        for date, val in bench_series.items()
    ]

    metrics = {
        "total_return": round(tot_ret, 2),
        "benchmark_total_return": round(tot_ret - bench_tot_ret, 2),  # relative
        "max_drawdown": max_dd,
        "benchmark_max_drawdown": bench_max_dd,
        "volatility": vol,
        "benchmark_volatility": bench_vol,
        "sharpe": sharpe,
        "benchmark_sharpe": bench_sharpe,
        "beta": beta,
        "correlation": corr,
    }

    metadata = {
        "symbols": symbols,
        "weights": weights,
        "startDate": start_date,
        "endDate": end_date,
        "rebalanceMode": rebalance,
        "rebalanceInterval": rebalance_interval,
        "benchmark": benchmark,
    }

    return BacktestResult(
        portfolio_series=portfolio_series,
        benchmark_series=benchmark_series,
        metrics=metrics,
        metadata=metadata,
    )


def run_scenario(
    positions: list[dict[str, Any]],
    scenario_key: str,
    initial_capital: float = 100000.0,
) -> BacktestResult:
    """Applies a named shock scenario to current holdings and projects drawdown trajectory."""
    spec = SCENARIOS.get(scenario_key)
    if not spec:
        raise ValueError(f"Unknown scenario key: {scenario_key}")

    name = spec["name"]
    duration_weeks = spec["duration_weeks"]
    shocks = {s["symbol_or_sector"]: s["magnitude_pct"] for s in spec["shocks"]}

    # Compute portfolio value and weighted impact
    total_val = sum(_to_float(p.get("shares")) * _to_float(p.get("last")) for p in positions)
    used_fallback_positions = total_val == 0
    if used_fallback_positions:
        # Fallback to an illustrative example allocation if no real portfolio was supplied (empty
        # or fresh/zeroed sync) — flagged in metadata so callers never mistake this for the real book.
        total_val = initial_capital
        dummy_positions = [
            {"symbol": "GOOG", "value": initial_capital * 0.2},
            {"symbol": "XLK", "value": initial_capital * 0.3},
            {"symbol": "VTI", "value": initial_capital * 0.25},
            {"symbol": "SOFI", "value": initial_capital * 0.15},
            {"symbol": "SLI", "value": initial_capital * 0.10},
        ]
        weighted_loss_pct = 0.0
        for pos in dummy_positions:
            sym = pos["symbol"]
            val = pos["value"]
            # Find shock magnitude
            shock_pct = shocks.get(sym, shocks.get("XLK" if sym in TECH_SYMBOLS else "VOO", -20.0))
            weighted_loss_pct += (val / total_val) * shock_pct
    else:
        weighted_loss_pct = 0.0
        for p in positions:
            sym = p["symbol"].upper()
            val = _to_float(p.get("shares")) * _to_float(p.get("last"))
            shock_pct = shocks.get(sym, shocks.get("XLK" if sym in TECH_SYMBOLS else "VOO", -20.0))
            weighted_loss_pct += (val / total_val) * shock_pct

    # S-curve cosine trajectory generation over W weeks
    # NAV(t) = Initial - Loss * (1 - cos(pi * t / duration_weeks)) / 2
    steps = duration_weeks * 5  # daily-ish steps
    portfolio_nav_points = []
    benchmark_nav_points = []

    # Benchmark VOO shock
    bench_shock = shocks.get("VOO", -20.0)

    # Seed random for organic noise reproducibility
    rng = random.Random(42)

    start_date = datetime.now(timezone.utc)

    for step in range(steps + 1):
        t = step / steps
        # Cosine factor ranging from 0.0 to 1.0
        cosine_factor = (1.0 - math.cos(math.pi * t)) / 2.0

        # Loss trajectories
        portfolio_drop_pct = weighted_loss_pct * cosine_factor
        bench_drop_pct = bench_shock * cosine_factor

        # Add organic wiggle noise
        noise_p = rng.normalvariate(0, 0.005)
        noise_b = rng.normalvariate(0, 0.004)

        p_nav = initial_capital * (1.0 + (portfolio_drop_pct / 100.0) + noise_p)
        b_nav = initial_capital * (1.0 + (bench_drop_pct / 100.0) + noise_b)

        date_str = (start_date + timedelta(days=step * 1.4)).strftime("%Y-%m-%d")
        portfolio_nav_points.append({"date": date_str, "value": round(p_nav, 2)})
        benchmark_nav_points.append({"date": date_str, "value": round(b_nav, 2)})

    # Calculate simulated summary stats
    nav_series = pd.Series([p["value"] for p in portfolio_nav_points])
    bench_series = pd.Series([b["value"] for b in benchmark_nav_points])

    tot_ret = ((nav_series.iloc[-1] / nav_series.iloc[0]) - 1) * 100
    bench_tot_ret = ((bench_series.iloc[-1] / bench_series.iloc[0]) - 1) * 100

    max_dd = calculate_max_drawdown(nav_series)
    bench_max_dd = calculate_max_drawdown(bench_series)

    vol = calculate_volatility(nav_series)
    bench_vol = calculate_volatility(bench_series)

    sharpe = calculate_sharpe(nav_series)
    bench_sharpe = calculate_sharpe(bench_series)

    beta, corr = calculate_beta_and_correlation(nav_series, bench_series)

    metrics = {
        "total_return": round(tot_ret, 2),
        "benchmark_total_return": round(tot_ret - bench_tot_ret, 2),
        "max_drawdown": max_dd,
        "benchmark_max_drawdown": bench_max_dd,
        "volatility": vol,
        "benchmark_volatility": bench_vol,
        "sharpe": sharpe,
        "benchmark_sharpe": bench_sharpe,
        "beta": beta,
        "correlation": corr,
    }

    metadata = {
        "scenarioName": name,
        "scenarioKey": scenario_key,
        "durationWeeks": duration_weeks,
        "shockDetails": shocks,
        "usedFallbackPositions": used_fallback_positions,
    }

    return BacktestResult(
        portfolio_series=portfolio_nav_points,
        benchmark_series=benchmark_nav_points,
        metrics=metrics,
        metadata=metadata,
    )
