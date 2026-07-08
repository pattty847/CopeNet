"""Morning delta brief — delta computation, persistence, and sentinel scheduling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from copenet.core.market.brief import build_morning_brief, compute_movers
from copenet.core.market.models import MarketBar
from copenet.core.market.store import MarketStore


def _panel(data) -> dict:
    return {"status": "live", "data": data}


def _wire(
    *,
    as_of: str = "as of Tue 4:00PM ET market refresh",
    evidence=None,
    soft=None,
    trend=None,
    rrg=None,
    regime: str = "chop",
    portfolio=None,
) -> dict:
    return {
        "asOf": as_of,
        "evidence": _panel(evidence or []),
        "softBottoming": _panel(soft or []),
        "trend": _panel(trend or []),
        "rrg": _panel(rrg or []),
        "regime": _panel({"current": regime, "scale": []}),
        "portfolio": _panel(portfolio or {}),
    }


def _evidence_row(symbol: str, headline: str, kind: str = "Insider") -> dict:
    return {"type": kind, "symbol": symbol, "headline": headline, "source": "SEC Form 4", "tone": "up", "t": 1751500000}


def test_new_evidence_is_diffed_by_identity_not_count() -> None:
    previous = _wire(evidence=[_evidence_row("SOFI", "CFO bought 10k shares")])
    current = _wire(
        evidence=[
            _evidence_row("SOFI", "CFO bought 10k shares"),
            _evidence_row("TSLA", "8-K: results announced", kind="8-K"),
        ]
    )
    brief = build_morning_brief(previous, current, movers=[])
    assert [e.symbol for e in brief.new_evidence] == ["TSLA"]
    assert brief.first_sweep is False
    assert "1 new SEC filing" in brief.headline


def test_signal_flips_soft_bottoming_and_trend() -> None:
    previous = _wire(
        soft=[{"symbol": "TSLA", "score": 0.7}],
        trend=[{"symbol": "GOOG", "direction": "up", "confirmed": True}],
    )
    current = _wire(
        soft=[{"symbol": "SOFI", "score": 0.65}],
        trend=[{"symbol": "GOOG", "direction": "down", "confirmed": True}],
    )
    brief = build_morning_brief(previous, current, movers=[])
    kinds = {(f["symbol"], f["kind"]) for f in brief.signal_flips}
    assert ("SOFI", "soft-bottoming") in kinds  # fired
    assert ("TSLA", "soft-bottoming") in kinds  # cleared
    goog = next(f for f in brief.signal_flips if f["symbol"] == "GOOG")
    assert "up → down" in goog["detail"]
    assert goog["tone"] == "down"


def test_rrg_shift_and_regime_shift() -> None:
    previous = _wire(rrg=[{"symbol": "XLK", "name": "Technology", "quadrant": "leading"}], regime="risk-on")
    current = _wire(rrg=[{"symbol": "XLK", "name": "Technology", "quadrant": "weakening"}], regime="chop")
    brief = build_morning_brief(previous, current, movers=[])
    assert brief.rrg_shifts == [
        {"symbol": "XLK", "name": "Technology", "from_quadrant": "leading", "to_quadrant": "weakening", "tone": "down"}
    ]
    assert brief.regime_shift == {"from": "risk-on", "to": "chop"}


def test_quiet_overnight_headline() -> None:
    same = _wire(evidence=[_evidence_row("SOFI", "CFO bought 10k shares")])
    brief = build_morning_brief(same, same, movers=[])
    assert brief.headline.startswith("Quiet overnight")


def test_first_sweep_does_not_spam_deltas() -> None:
    previous = _wire(as_of="as of no market refresh yet")
    current = _wire(evidence=[_evidence_row("SOFI", f"headline {i}") for i in range(30)])
    brief = build_morning_brief(previous, current, movers=[])
    assert brief.first_sweep is True
    assert brief.new_evidence == []
    assert brief.note is not None
    assert "baseline" in brief.headline


def test_portfolio_note_includes_delta_vs_previous_sweep() -> None:
    previous = _wire(portfolio={"total": "$4,400", "pnl": "+700 · +19.0%", "positions": [{"symbol": "GOOG"}]})
    current = _wire(portfolio={"total": "$4,417", "pnl": "+722 · +19.8%", "positions": [{"symbol": "GOOG"}]})
    brief = build_morning_brief(previous, current, movers=[])
    assert brief.portfolio_note is not None
    assert "$4,417" in brief.portfolio_note
    assert "+17 vs previous sweep" in brief.portfolio_note


def test_wire_shape_is_camel_case() -> None:
    previous = _wire(rrg=[{"symbol": "XLK", "name": "Technology", "quadrant": "leading"}])
    current = _wire(rrg=[{"symbol": "XLK", "name": "Technology", "quadrant": "improving"}])
    wire = build_morning_brief(previous, current, movers=[{"symbol": "SOFI", "name": "SoFi", "last": "$14.00", "change_pct": 4.2, "tone": "up"}]).to_wire()
    assert wire["briefDate"]
    assert wire["rrgShifts"][0]["fromQuadrant"] == "leading"
    assert wire["movers"][0]["changePct"] == 4.2
    assert wire["firstSweep"] is False


def test_compute_movers_ranks_by_absolute_change(tmp_path: Path) -> None:
    store = MarketStore(tmp_path)

    def bars(closes: list[float]) -> list[MarketBar]:
        return [MarketBar(t=1751000000 + i * 86400, o=c, h=c, l=c, c=c, v=100) for i, c in enumerate(closes)]

    store.save_bars("SOFI", "daily", bars([10.0, 11.0]))  # +10%
    store.save_bars("GOOG", "daily", bars([100.0, 98.0]))  # -2%
    movers = compute_movers(store)
    assert movers[0]["symbol"] == "SOFI"
    assert movers[0]["change_pct"] == 10.0
    assert movers[0]["tone"] == "up"
    goog = next(m for m in movers if m["symbol"] == "GOOG")
    assert goog["tone"] == "down"


def test_store_brief_round_trip_and_dated_copy(tmp_path: Path) -> None:
    store = MarketStore(tmp_path)
    assert store.load_morning_brief() is None
    wire = build_morning_brief(_wire(), _wire(), movers=[]).to_wire()
    store.save_morning_brief(wire)
    loaded = store.load_morning_brief()
    assert loaded == wire
    dated = tmp_path / "briefs" / f"{wire['briefDate']}.json"
    assert dated.is_file()


def test_sentinel_schedules_catchup_when_brief_missing(tmp_path: Path, monkeypatch) -> None:
    from copenet.core.market.runtime import MarketRuntime
    from copenet.core.market.sentinel import MarketSentinel, _CATCHUP_DELAY_SECONDS

    runtime = MarketRuntime(store=MarketStore(tmp_path))

    class _Orchestrator:
        pass

    sentinel = MarketSentinel(_Orchestrator())
    now = datetime.now()
    past = f"{max(now.hour - 1, 0):02d}:00"
    future = f"{min(now.hour + 1, 23):02d}:59"

    # Past brief time, no brief for today → catch up soon.
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", past)
    assert sentinel._seconds_until_next_sweep(runtime) == _CATCHUP_DELAY_SECONDS

    # Past brief time, but today's brief predates brief time (a pre-dawn manual sweep) →
    # the scheduled sweep still owes a run.
    runtime.store.save_morning_brief(
        {
            "briefDate": now.strftime("%Y-%m-%d"),
            "generatedAt": now.replace(hour=0, minute=30).astimezone().isoformat(),
            "headline": "x",
        }
    )
    assert sentinel._seconds_until_next_sweep(runtime) == _CATCHUP_DELAY_SECONDS

    # Past brief time, today's brief generated after brief time → wait for tomorrow.
    runtime.store.save_morning_brief(
        {
            "briefDate": now.strftime("%Y-%m-%d"),
            "generatedAt": now.astimezone().isoformat(),
            "headline": "x",
        }
    )
    assert sentinel._seconds_until_next_sweep(runtime) > 3600

    # Before brief time → wait until brief time, not catch-up.
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", future)
    delay = sentinel._seconds_until_next_sweep(runtime)
    assert _CATCHUP_DELAY_SECONDS <= delay <= 2 * 3600
