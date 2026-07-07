from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from copenet.core.market.backtester import (
    SCENARIOS,
    calculate_beta_and_correlation,
    calculate_max_drawdown,
    calculate_sharpe,
    calculate_volatility,
    run_portfolio_backtest,
    run_scenario,
)
from copenet.core.market.models import MarketBar
from copenet.core.market.store import MarketStore


def _bars(start_price: float, daily_pct_changes: list[float], start: datetime | None = None) -> list[MarketBar]:
    """Build a synthetic daily bar series so tests never touch the network."""
    start = start or datetime(2022, 1, 3, tzinfo=timezone.utc)
    price = start_price
    bars: list[MarketBar] = []
    for i, pct in enumerate(daily_pct_changes):
        price = price * (1 + pct)
        t = int((start + timedelta(days=i)).timestamp())
        bars.append(MarketBar(t=t, o=price, h=price * 1.01, l=price * 0.99, c=price, v=1_000_000))
    return bars


def _seed_store(tmp_path: Path, series: dict[str, list[MarketBar]]) -> MarketStore:
    store = MarketStore(tmp_path)
    for symbol, bars in series.items():
        store.save_bars(symbol, "daily", bars)
    return store


# ---------- metrics ----------


def test_max_drawdown_on_known_series() -> None:
    nav = pd.Series([100.0, 120.0, 90.0, 95.0, 110.0])
    # peak 120 -> trough 90 = -25%
    assert calculate_max_drawdown(nav) == pytest.approx(-25.0, abs=0.01)


def test_max_drawdown_empty_series_is_zero() -> None:
    assert calculate_max_drawdown(pd.Series([], dtype=float)) == 0.0


def test_volatility_zero_for_flat_series() -> None:
    nav = pd.Series([100.0] * 30)
    assert calculate_volatility(nav) == 0.0


def test_sharpe_zero_when_std_is_zero() -> None:
    nav = pd.Series([100.0] * 10)
    assert calculate_sharpe(nav) == 0.0


def test_beta_and_correlation_double_beta_series() -> None:
    # Portfolio's daily RETURNS are exactly 2x the benchmark's -> beta ~2, corr ~1.
    # (Scaling price *level* would NOT double beta -- pct_change is scale-invariant --
    # so the amplification has to be applied to the returns themselves.)
    bench = pd.Series([100.0, 101.0, 102.0, 101.0, 103.0, 104.0])
    bench_returns = bench.pct_change().dropna()
    portfolio = pd.Series([100.0] + list(100.0 * (1 + 2 * bench_returns).cumprod()))
    beta, corr = calculate_beta_and_correlation(portfolio, bench)
    assert beta == pytest.approx(2.0, abs=0.05)
    assert corr == pytest.approx(1.0, abs=0.01)


def test_beta_and_correlation_uncorrelated_short_series_is_safe() -> None:
    # Fewer than 2 overlapping return points must not raise
    beta, corr = calculate_beta_and_correlation(pd.Series([100.0]), pd.Series([100.0]))
    assert beta == 0.0
    assert corr == 0.0


# ---------- run_portfolio_backtest ----------


def test_backtest_uses_cached_bars_without_network(tmp_path: Path) -> None:
    days = 60
    aaa = _bars(100.0, [0.01] * days)  # steadily up
    bbb = _bars(100.0, [-0.005] * days)  # steadily down
    bench = _bars(100.0, [0.002] * days)
    store = _seed_store(tmp_path, {"AAA": aaa, "BBB": bbb, "VOO": bench})

    start = datetime(2022, 1, 3, tzinfo=timezone.utc).strftime("%Y-%m-%d")
    end = (datetime(2022, 1, 3, tzinfo=timezone.utc) + timedelta(days=days - 1)).strftime("%Y-%m-%d")

    result = run_portfolio_backtest(
        symbols=["AAA", "BBB"],
        weights=[0.5, 0.5],
        start_date=start,
        end_date=end,
        benchmark="VOO",
        store=store,
    )

    assert len(result.portfolio_series) > 0
    assert len(result.benchmark_series) > 0
    # AAA rises ~1%/day, BBB falls ~0.5%/day; a 50/50 blend should net positive over 60 days
    assert result.metrics["total_return"] > 0
    assert result.metadata["symbols"] == ["AAA", "BBB"]
    assert result.metadata["rebalanceMode"] == "buy_and_hold"


def test_backtest_normalizes_weights_that_dont_sum_to_one(tmp_path: Path) -> None:
    days = 30
    store = _seed_store(
        tmp_path,
        {
            "AAA": _bars(100.0, [0.0] * days),
            "VOO": _bars(100.0, [0.0] * days),
        },
    )
    start = datetime(2022, 1, 3, tzinfo=timezone.utc).strftime("%Y-%m-%d")
    end = (datetime(2022, 1, 3, tzinfo=timezone.utc) + timedelta(days=days - 1)).strftime("%Y-%m-%d")

    # weights sum to 2.0, not 1.0 -- should be normalized rather than raising
    result = run_portfolio_backtest(
        symbols=["AAA"], weights=[2.0], start_date=start, end_date=end, benchmark="VOO", store=store
    )
    assert result.metadata["weights"] == [1.0]


def test_backtest_rejects_mismatched_symbols_and_weights(tmp_path: Path) -> None:
    store = MarketStore(tmp_path)
    with pytest.raises(ValueError, match="symbols must match"):
        run_portfolio_backtest(
            symbols=["AAA", "BBB"], weights=[1.0], start_date="2022-01-01", end_date="2022-02-01", store=store
        )


def test_periodic_rebalance_diverges_from_buy_and_hold(tmp_path: Path) -> None:
    """A winner/loser pair should produce a different terminal NAV under periodic rebalancing
    than buy-and-hold, since rebalancing trims the winner and adds to the loser along the way."""
    days = 90
    store = _seed_store(
        tmp_path,
        {
            "WINNER": _bars(100.0, [0.01] * days),
            "LOSER": _bars(100.0, [-0.01] * days),
            "VOO": _bars(100.0, [0.0] * days),
        },
    )
    start = datetime(2022, 1, 3, tzinfo=timezone.utc).strftime("%Y-%m-%d")
    end = (datetime(2022, 1, 3, tzinfo=timezone.utc) + timedelta(days=days - 1)).strftime("%Y-%m-%d")

    buy_and_hold = run_portfolio_backtest(
        symbols=["WINNER", "LOSER"], weights=[0.5, 0.5], start_date=start, end_date=end, benchmark="VOO", store=store
    )
    rebalanced = run_portfolio_backtest(
        symbols=["WINNER", "LOSER"],
        weights=[0.5, 0.5],
        start_date=start,
        end_date=end,
        benchmark="VOO",
        rebalance="periodic",
        rebalance_interval="monthly",
        store=store,
    )
    assert buy_and_hold.metrics["total_return"] != rebalanced.metrics["total_return"]


# ---------- run_scenario ----------


def test_scenario_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="Unknown scenario key"):
        run_scenario(positions=[], scenario_key="not_a_real_scenario")


def test_scenario_flags_fallback_positions_when_portfolio_is_empty() -> None:
    result = run_scenario(positions=[], scenario_key="2022_tech_dump")
    assert result.metadata["usedFallbackPositions"] is True


def test_scenario_uses_real_positions_when_provided() -> None:
    positions = [{"symbol": "XLK", "shares": 100, "last": 200.0}]
    result = run_scenario(positions=positions, scenario_key="2022_tech_dump")
    assert result.metadata["usedFallbackPositions"] is False
    # 100% XLK exposure under the 2022 preset's XLK shock should land near that shock magnitude
    xlk_shock = SCENARIOS["2022_tech_dump"]["shocks"][0]["magnitude_pct"]
    assert result.metrics["total_return"] == pytest.approx(xlk_shock, abs=1.0)


def test_scenario_handles_dashboard_formatted_price_strings() -> None:
    """Regression test: the dashboard's Portfolio wire (PortfolioPosition.last) is a display
    string like "$2.78", not a raw float -- that's exactly what the frontend sends when a real
    Webull-synced portfolio is stress-tested. This used to raise
    ValueError: could not convert string to float: '$2.78'."""
    positions = [
        {"symbol": "SOFI", "shares": "1,000", "last": "$2.78"},
        {"symbol": "GOOG", "shares": 5, "last": "$314.55"},
    ]
    result = run_scenario(positions=positions, scenario_key="2022_tech_dump")
    assert result.metadata["usedFallbackPositions"] is False
    assert isinstance(result.metrics["total_return"], float)


def test_scenario_metadata_shock_details_are_real_for_each_preset() -> None:
    """Guards against UI code hardcoding a shock magnitude that only matches one preset."""
    for key in SCENARIOS:
        result = run_scenario(positions=[], scenario_key=key)
        assert result.metadata["shockDetails"] == {
            s["symbol_or_sector"]: s["magnitude_pct"] for s in SCENARIOS[key]["shocks"]
        }
