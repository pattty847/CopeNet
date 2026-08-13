from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from copenet.core.research_lab.equity_forecast.dataset import load_financial_snapshot
from copenet.core.research_lab.equity_forecast.features import cagr, derive_fundamental_features, growth, safe_ratio
from copenet.core.research_lab.equity_forecast.ledger import canonical_json, content_hash, write_exclusive_jsonl
from copenet.core.research_lab.equity_forecast.models import build_model
from copenet.core.research_lab.equity_forecast.experiment import summarize_contributions
from copenet.core.research_lab.equity_forecast.targets import forward_targets, market_features, total_return
from copenet.core.research_lab.equity_forecast.walk_forward import walk_forward


@pytest.mark.asyncio
async def test_point_in_time_snapshot_passes_cutoff_and_rejects_future_filing() -> None:
    seen: list[str] = []

    async def loader(**kwargs):
        seen.append(kwargs["as_of"])
        return {"observations": [{"periodEnd": "2019-12-31", "availableAt": "2020-02-01", "value": 1.0}]}

    series, _ = await load_financial_snapshot("TEST", date(2020, 2, 14), refresh=False, loader=loader)
    assert seen and set(seen) == {"2020-02-14"}
    assert series["revenue"][0]["availableAt"] == "2020-02-01"

    async def cheating_loader(**_kwargs):
        return {"observations": [{"periodEnd": "2019-12-31", "availableAt": "2020-02-15", "value": 1.0}]}

    with pytest.raises(ValueError, match="future financial observation"):
        await load_financial_snapshot("TEST", date(2020, 2, 14), refresh=False, loader=cheating_loader)


def test_forward_total_and_excess_return_use_horizon_prices() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-07-02", "2021-01-04", "2022-01-03"])
    stock = pd.Series([100.0, 110.0, 125.0, 150.0], index=index)
    spy = pd.Series([100.0, 105.0, 110.0, 120.0], index=index)
    assert total_return(stock, date(2020, 1, 2), 12) == pytest.approx((0.25, "2021-01-04"))
    targets = forward_targets(stock, spy, date(2020, 1, 2))
    assert targets is not None
    assert targets["forward_return_12m"] == pytest.approx(0.25)
    assert targets["benchmark_forward_return_12m"] == pytest.approx(0.10)
    assert targets["excess_return_12m"] == pytest.approx(0.15)


def test_feature_derivation_is_deterministic_and_handles_missing_values() -> None:
    def rows(values):
        return [
            {"periodEnd": f"{year}-12-31", "availableAt": f"{year + 1}-02-01", "value": value}
            for year, value in values
        ]

    series = {
        "revenue": rows([(2018, 80), (2019, 90), (2020, 100), (2021, 120)]),
        "operating_income": rows([(2020, 10), (2021, 15)]),
        "fcf": rows([(2020, 8), (2021, 12)]),
        "operating_margin": rows([(2020, 0.10), (2021, 0.125)]),
        "fcf_margin": rows([(2020, 0.08), (2021, 0.10)]),
        "net_debt": rows([(2021, 24)]),
        "working_capital": rows([(2021, 30)]),
    }
    features = derive_fundamental_features(series)
    assert growth(120, 100) == pytest.approx(0.2)
    assert cagr(120, 80, 3) == pytest.approx((1.5 ** (1 / 3)) - 1)
    assert features["net_debt_to_fcf"] == pytest.approx(2.0)
    assert features["working_capital_to_revenue"] == pytest.approx(0.25)
    assert features["roic"] is None
    assert safe_ratio(1, 0) is None


def test_price_features_never_use_prediction_day_or_future_price() -> None:
    index = pd.date_range("2020-01-01", periods=370, freq="D")
    prices = pd.Series(np.arange(1, 371, dtype=float), index=index)
    cutoff = date(2021, 1, 1)
    features = market_features(prices, cutoff)
    altered = prices.copy()
    altered.loc[altered.index.date >= cutoff] = 1_000_000
    assert market_features(altered, cutoff) == features


def _synthetic_dataset() -> pd.DataFrame:
    rows = []
    periods = pd.date_range("2015-02-16", periods=28, freq="QS-FEB")
    for p_index, period in enumerate(periods):
        for s_index, ticker in enumerate(("A", "B", "C", "D", "E")):
            signal = (s_index - 2) * 0.02 + p_index * 0.001
            rows.append({
                "ticker": ticker,
                "prediction_timestamp": period.tz_localize("America/New_York").replace(hour=16).isoformat(),
                "target_end_12m": (period + pd.DateOffset(months=12)).tz_localize("America/New_York").replace(hour=16).isoformat(),
                "excess_return_12m": signal,
                "holding_period_return": signal / 4,
                "benchmark_holding_period_return": 0.02,
                "holding_period_end": (period + pd.DateOffset(months=3)).isoformat(),
                **{name: signal for names in __import__("copenet.core.research_lab.equity_forecast.features", fromlist=["FEATURE_SETS"]).FEATURE_SETS.values() for name in names},
            })
    return pd.DataFrame(rows)


def test_walk_forward_enforces_target_reveal_and_is_deterministic() -> None:
    dataset = _synthetic_dataset()
    first, _, _ = walk_forward(dataset, minimum_training_rows=20, seed=7, cost_bps=10)
    second, _, _ = walk_forward(dataset, minimum_training_rows=20, seed=7, cost_bps=10)
    pd.testing.assert_frame_equal(first, second)
    assert not first.empty
    assert first[first["model"] == "naive"]["predicted"].nunique() > 0
    for _, row in first.iterrows():
        eligible = dataset[(pd.to_datetime(dataset["prediction_timestamp"], utc=True) < pd.to_datetime(row["prediction_timestamp"], utc=True)) & (pd.to_datetime(dataset["target_end_12m"], utc=True) < pd.to_datetime(row["prediction_timestamp"], utc=True))]
        assert row["training_rows"] == len(eligible)


def test_walk_forward_excludes_target_revealed_at_prediction_timestamp() -> None:
    dataset = _synthetic_dataset()
    prediction_time = pd.to_datetime(dataset.iloc[25]["prediction_timestamp"], utc=True)
    dataset.loc[0, "target_end_12m"] = prediction_time.isoformat()
    predictions, _, _ = walk_forward(dataset, minimum_training_rows=1, seed=7, cost_bps=10)
    matching = predictions[
        pd.to_datetime(predictions["prediction_timestamp"], utc=True) == prediction_time
    ]
    assert not matching.empty
    assert set(matching["training_rows"]) == {4}


def test_feature_contribution_summary_is_stable_and_sorted() -> None:
    summary = summarize_contributions({
        "features": {
            "ridge": [
                {"values": {"a": 2.0, "b": -1.0}},
                {"values": {"a": 4.0, "b": 1.0}},
            ]
        }
    })
    rows = summary["features:ridge"]
    assert [row["feature"] for row in rows] == ["a", "b"]
    assert rows[0]["mean_absolute"] == pytest.approx(3.0)
    assert rows[0]["sign_consistency"] == pytest.approx(1.0)


def test_scaler_is_fit_only_on_training_window() -> None:
    model = build_model("ridge", 7)
    train = pd.DataFrame({"x": [0.0, 2.0]})
    model.fit(train, [0.0, 1.0])
    assert model.named_steps["scaler"].mean_[0] == pytest.approx(1.0)


def test_prediction_ledger_is_immutable(tmp_path) -> None:
    path = tmp_path / "predictions.jsonl"
    write_exclusive_jsonl(path, [{"prediction_id": "one"}])
    with pytest.raises(FileExistsError):
        write_exclusive_jsonl(path, [{"prediction_id": "two"}])
    assert canonical_json({"missing": float("nan")}) == '{"missing":null}'
    assert content_hash([{"value": 0.123456789012345}]) == content_hash([{"value": 0.123456789012345}])
