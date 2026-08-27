from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from copenet.core.market.market_tape import build_market_tape
from copenet.core.market.market_tape_formatter import format_market_tape
from copenet.core.market.interpretation import MarketRead
from copenet.core.market.models import MarketBar
from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore


def _timestamp(day: date) -> int:
    return int(datetime.combine(day, time(), tzinfo=timezone.utc).timestamp())


def _daily_bars(start: date, count: int, *, first_close: float = 100.0) -> list[MarketBar]:
    bars: list[MarketBar] = []
    day = start
    index = 0
    while len(bars) < count:
        if day.weekday() < 5:
            close = first_close + index * 0.6
            bars.append(
                MarketBar(
                    t=_timestamp(day),
                    o=close - 0.2,
                    h=close + 0.8,
                    l=close - 0.7,
                    c=close,
                    v=1_000_000 + index * 10_000,
                )
            )
            index += 1
        day += timedelta(days=1)
    return bars


def _rrg_dashboard() -> dict:
    return {
        "rrg": {
            "data": [
                {
                    "symbol": "XLK",
                    "quadrant": "leading",
                    "tails": {
                        "fast": [{"x": 101.0, "y": 100.5}],
                        "default": [{"x": 100.0, "y": 99.0}, {"x": 101.5, "y": 100.0}],
                        "slow": [{"x": 100.4, "y": 100.2}],
                    },
                }
            ]
        }
    }


def test_market_tape_is_point_in_time_and_marks_current_session_partial(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    voo = _daily_bars(date(2026, 5, 1), 86)
    qqq = voo[:-2]
    store.save_bars("VOO", "daily", voo)
    store.save_bars("QQQ", "daily", qqq)

    as_of = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    tape = build_market_tape(store, _rrg_dashboard(), now=as_of)
    wire = tape.to_wire()
    by_symbol = {item.symbol: item for item in tape.instruments}

    assert by_symbol["VOO"].bars[-1].date == "2026-08-27"
    assert by_symbol["VOO"].latest_bar_complete is False
    assert all(bar.date <= "2026-08-27" for bar in by_symbol["VOO"].bars)
    assert len(by_symbol["VOO"].bars) == 15
    assert tape.completed_through == "2026-08-26"
    assert "VOO" in tape.data_quality.potentially_incomplete_daily_symbols
    assert wire["schemaVersion"] == "market_tape.v1"
    assert wire["instruments"][0]["bars"][-1]["complete"] is False


def test_market_tape_marks_the_session_complete_after_the_close(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    store.save_bars("VOO", "daily", _daily_bars(date(2026, 5, 1), 85))

    tape = build_market_tape(
        store,
        {},
        now=datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc),
    )

    assert tape.instruments[0].bars[-1].date == "2026-08-27"
    assert tape.instruments[0].latest_bar_complete is True
    assert tape.completed_through == "2026-08-27"
    assert tape.data_quality.potentially_incomplete_daily_symbols == []


def test_market_tape_uses_dashboard_observation_time_for_stale_snapshots(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    store.save_bars("VOO", "daily", _daily_bars(date(2026, 5, 1), 85))
    dashboard = {
        "briefing": {
            "asOf": "2026-08-27T13:46:00Z",
            "data": {},
        }
    }

    tape = build_market_tape(
        store,
        dashboard,
        now=datetime(2026, 8, 27, 23, 0, tzinfo=timezone.utc),
    )

    assert tape.observed_at == "2026-08-27T13:46:00Z"
    assert tape.instruments[0].latest_bar_complete is False
    assert tape.data_quality.source_age_minutes == 554.0
    assert "predates packet generation" in tape.data_quality.warnings[-1]


def test_market_tape_suppresses_impossible_ohlc_geometry(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    bars = _daily_bars(date(2026, 5, 1), 85)
    latest = bars[-1]
    bars[-1] = MarketBar(
        t=latest.t,
        o=latest.l - 1,
        h=latest.h,
        l=latest.l,
        c=latest.c,
        v=latest.v,
    )
    store.save_bars("VOO", "daily", bars)

    tape = build_market_tape(
        store,
        {},
        now=datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc),
    )
    bar = tape.instruments[0].bars[-1]

    assert bar.geometry_valid is False
    assert bar.gap_pct is None
    assert bar.range_atr is None
    assert bar.body_atr is None
    assert tape.data_quality.malformed_daily_symbols == ["VOO"]
    assert "INVALID OHLC GEOMETRY" in format_market_tape(tape)


def test_market_tape_derives_rrg_motion_and_formats_model_semantics(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    store.save_bars("VOO", "daily", _daily_bars(date(2026, 5, 1), 85))

    tape = build_market_tape(
        store,
        _rrg_dashboard(),
        now=datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc),
    )
    vector = tape.rrg[0].modes["default"]
    rendered = format_market_tape(tape)

    assert vector.delta_x == 1.5
    assert vector.delta_y == 1.0
    assert vector.velocity == 1.803
    assert "PARTIAL CURRENT SESSION" in rendered
    assert "ACCOUNT-NEUTRAL PARTICIPATION" in rendered
    assert "RRG MOTION" in rendered
    assert "DATA QUALITY WARNING" in rendered


def test_market_tape_persistence_keeps_intraday_editions(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    first = {"schemaVersion": "market_tape.v1", "generatedAt": "2026-08-27T13:46:00Z"}
    second = {"schemaVersion": "market_tape.v1", "generatedAt": "2026-08-27T19:00:00Z"}

    store.save_market_tape(first)
    store.save_market_tape(second)

    assert store.load_market_tape() == second
    archive = tmp_path / "market" / "market-tapes" / "2026-08-27"
    assert len(list(archive.glob("*.json"))) == 2


async def test_market_interpretation_persists_the_exact_tape_shown_to_the_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import copenet.core.market.runtime as runtime_module

    store = MarketStore(tmp_path / "market")
    store.save_bars("VOO", "daily", _daily_bars(date(2026, 5, 1), 85))
    captured: dict[str, str] = {}

    async def fake_generate_market_read(provider, packet: str, *, model: str, generated_at: str) -> MarketRead:
        captured["packet"] = packet
        return MarketRead(
            headline="Test read",
            emphasis="flat",
            summary="Test summary",
            regime="chop",
            regime_reasoning="Mixed evidence.",
            continuity="",
            attention=[],
            rotation_read="",
            speculative_comment="",
            thesis_killers=[],
            caveats="",
            model=model,
            generated_at=generated_at,
        )

    monkeypatch.setattr(runtime_module, "_now_iso", lambda: "2026-08-27T13:46:00Z")
    monkeypatch.setattr(runtime_module, "load_base_rate", lambda *_: None)
    monkeypatch.setattr(runtime_module, "generate_market_read", fake_generate_market_read)
    monkeypatch.setattr(runtime_module, "track_record_line", lambda *_: None)
    monkeypatch.setattr(runtime_module, "record_market_read_claims", lambda *_: 0)
    monkeypatch.setattr(runtime_module, "include_portfolio_context_enabled", lambda: False)

    await MarketRuntime(store=store).interpret(object(), target="market")

    saved = store.load_market_tape()
    assert saved is not None
    assert saved["generatedAt"] == "2026-08-27T13:46:00Z"
    assert saved["schemaVersion"] == "market_tape.v1"
    assert "MARKET TAPE SNAPSHOT" in captured["packet"]
    assert "PARTIAL CURRENT SESSION" in captured["packet"]
