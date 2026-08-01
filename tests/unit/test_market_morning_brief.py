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


def test_quiet_tape_headline() -> None:
    same = _wire(evidence=[_evidence_row("SOFI", "CFO bought 10k shares")])
    brief = build_morning_brief(same, same, movers=[])
    assert brief.headline.startswith("Quiet tape")


def test_small_mover_does_not_break_quiet_headline() -> None:
    # Honest-quiet rule: ordinary drift stays in the movers row; only a material move
    # (>= 3%) may claim the headline when nothing thesis-relevant changed.
    same = _wire(evidence=[_evidence_row("SOFI", "CFO bought 10k shares")])
    drift = [{"symbol": "NVDA", "name": "NVIDIA", "last": "$204.61", "change_pct": 0.9, "tone": "up"}]
    brief = build_morning_brief(same, same, movers=drift)
    assert brief.headline.startswith("Quiet tape")
    assert brief.movers == drift

    big = [{"symbol": "INTC", "name": "Intel", "last": "$108.56", "change_pct": -9.7, "tone": "down"}]
    brief = build_morning_brief(same, same, movers=big)
    assert "INTC -9.7% last session" in brief.headline


def test_first_sweep_does_not_spam_deltas() -> None:
    previous = _wire(as_of="as of no market refresh yet")
    current = _wire(evidence=[_evidence_row("SOFI", f"headline {i}") for i in range(30)])
    brief = build_morning_brief(previous, current, movers=[])
    assert brief.first_sweep is True
    assert brief.new_evidence == []
    assert brief.note is not None
    assert "baseline" in brief.headline


def test_portfolio_note_leads_with_delta_and_labels_lifetime_pnl() -> None:
    previous = _wire(portfolio={"total": "$4,400", "pnl": "+700 · +19.0%", "positions": [{"symbol": "GOOG"}]})
    current = _wire(portfolio={"total": "$4,417", "pnl": "+722 · +19.8%", "positions": [{"symbol": "GOOG"}]})
    brief = build_morning_brief(previous, current, movers=[])
    assert brief.portfolio_note == "Portfolio $4,417 · +17 since last sweep · +19.8% all-time"


def test_portfolio_note_flat_overnight_still_labels_lifetime() -> None:
    same = {"total": "$4,417", "pnl": "+722 · +19.8%", "positions": [{"symbol": "GOOG"}]}
    brief = build_morning_brief(_wire(portfolio=same), _wire(portfolio=same), movers=[])
    assert brief.portfolio_note == "Portfolio $4,417 · flat since last sweep · +19.8% all-time"


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

    store.save_bars("VOO", "daily", bars([10.0, 11.0]))  # +10%
    store.save_bars("QQQ", "daily", bars([100.0, 98.0]))  # -2%
    movers, label = compute_movers(store)
    assert movers[0]["symbol"] == "VOO"
    assert movers[0]["change_pct"] == 10.0
    assert movers[0]["tone"] == "up"
    qqq = next(m for m in movers if m["symbol"] == "QQQ")
    assert qqq["tone"] == "down"
    assert label == "last session"  # fixture bars are from 2025 — never "today"


def test_compute_movers_labels_forming_candle_as_today(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    store = MarketStore(tmp_path)
    now = int(datetime.now(timezone.utc).timestamp())
    store.save_bars(
        "VOO",
        "daily",
        [MarketBar(t=now - 86400, o=10, h=10, l=10, c=10.0, v=100), MarketBar(t=now, o=10, h=11, l=10, c=10.5, v=100)],
    )
    _, label = compute_movers(store)
    assert label == "today at the open"


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
    from copenet.core.market import sentinel as sentinel_module
    from copenet.core.market.runtime import MarketRuntime
    from copenet.core.market.sentinel import MarketSentinel, _CATCHUP_DELAY_SECONDS

    # Freeze the sentinel's clock at local noon — the assertions below construct
    # "before/after brief time" scenarios that are impossible near midnight (a same-day
    # brief can't predate a 00:00 target), which made the wall-clock version flaky.
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: N805 — datetime API
            base = cls(2026, 7, 15, 12, 0, 0)
            return base.astimezone(tz) if tz is not None else base

    monkeypatch.setattr(sentinel_module, "datetime", _FixedDateTime)

    runtime = MarketRuntime(store=MarketStore(tmp_path))

    class _Orchestrator:
        pass

    sentinel = MarketSentinel(_Orchestrator())
    now = _FixedDateTime(2026, 7, 15, 12, 0, 0)

    # Past brief time (11:00 < noon), no brief for today → catch up soon.
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", "11:00")
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

    # Before brief time (13:59 > noon) → wait until brief time, not catch-up.
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", "13:59")
    delay = sentinel._seconds_until_next_sweep(runtime)
    assert _CATCHUP_DELAY_SECONDS <= delay <= 2 * 3600
