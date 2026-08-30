from __future__ import annotations

import pytest

from copenet.core.market.formulas import (
    FormulaError,
    active_formula_symbol,
    evaluate_formulas,
    formula_search_candidate,
    parse_formula,
)
from copenet.core.market.models import MarketBar
from copenet.host import rpc_market_formula


def _bars(values: list[float], *, start: int = 100) -> list[MarketBar]:
    return [MarketBar(t=start + index, o=value, h=value, l=value, c=value, v=1) for index, value in enumerate(values)]


def test_formula_parser_normalizes_precedence_and_yahoo_symbols() -> None:
    parsed = parse_formula(" 0.6*voo + 0.4 * (tlt / GLD) ")
    assert parsed.expression == "0.6 * VOO + 0.4 * (TLT / GLD)"
    assert parsed.components == ("VOO", "TLT", "GLD")
    assert parsed.synthetic is True
    assert parse_formula("BTC-USD").synthetic is False
    assert parse_formula("QQQ - SPY").expression == "QQQ - SPY"
    assert parse_formula("QQQ-SPY").components == ("QQQ-SPY",)


def test_formula_search_candidate_and_active_operand() -> None:
    candidate = formula_search_candidate("VOO/GLD")
    assert candidate == {
        "type": "formula",
        "symbol": "VOO / GLD",
        "name": "Formula symbol · 2 components",
        "exchange": "SYNTHETIC",
        "components": ["VOO", "GLD"],
    }
    assert formula_search_candidate("VOO") is None
    assert active_formula_symbol("VOO / go") == "GO"
    assert active_formula_symbol("VOO / 2") == ""


def test_formula_evaluation_uses_shared_timestamps_and_skips_zero_division() -> None:
    histories = {
        "VOO": _bars([100, 110, 120]),
        "GLD": _bars([50, 0, 40]),
    }
    result = evaluate_formulas(["VOO / GLD"], histories.__getitem__)[0]
    assert [(point.t, point.value) for point in result.points] == [(100, 2.0), (102, 3.0)]
    assert result.warnings == ("Skipped 1 point with undefined or non-finite results",)


def test_formula_evaluation_rejects_missing_histories_and_unsafe_syntax() -> None:
    with pytest.raises(FormulaError, match="No price history for GLD"):
        evaluate_formulas(["VOO / GLD"], lambda symbol: _bars([1]) if symbol == "VOO" else [])
    with pytest.raises(FormulaError, match="Unsupported character"):
        parse_formula("__import__('os')")
    with pytest.raises(FormulaError, match="ends before"):
        parse_formula("VOO /")


@pytest.mark.asyncio
async def test_formula_rpc_returns_split_adjusted_scalar_series(monkeypatch: pytest.MonkeyPatch) -> None:
    class Runtime:
        def cached_bars(self, symbol: str, timeframe: str, *, basis: str) -> list[MarketBar]:
            assert timeframe == "weekly"
            assert basis == "split_adjusted"
            return {"VOO": _bars([100, 120]), "GLD": _bars([50, 40])}[symbol]

    monkeypatch.setattr(rpc_market_formula, "resolve_market_runtime", lambda orchestrator: Runtime())
    frames: list[dict[str, object]] = []

    async def send_json(frame: dict[str, object]) -> None:
        frames.append(frame)

    await rpc_market_formula.handle_market_chart_formulas_get(
        "formula",
        {"expressions": ["VOO/GLD"], "timeframe": "weekly"},
        send_json,
        object(),
    )

    payload = frames[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["priceBasis"] == "split_adjusted"
    assert payload["formulas"][0]["expression"] == "VOO / GLD"  # type: ignore[index]
    assert payload["formulas"][0]["points"][-1] == {"t": 101, "value": 3.0}  # type: ignore[index]
