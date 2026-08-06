"""Market read archiving and the day-over-day trail behind the briefing.

`latest-market-read.json` was overwritten on every run, so the model could never be asked what
it called yesterday or whether it held up. These cover the archive plus the trail built from it.
"""

from __future__ import annotations

from pathlib import Path

from copenet.core.market.fact_packets import market_history_section
from copenet.core.market.store import MarketStore


def _read(date: str, regime: str = "risk-on") -> dict:
    return {"headline": f"read for {date}", "regime": regime, "generatedAt": f"{date}T13:45:00Z"}


def _brief(date: str, headline: str = "", **extra) -> dict:
    return {"briefDate": date, "headline": headline or f"brief for {date}", **extra}


# ---------- archiving ----------


def test_market_read_is_archived_by_date_alongside_latest(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    store.save_market_read(_read("2026-08-04"))
    store.save_market_read(_read("2026-08-05"))

    assert store.load_market_read()["generatedAt"].startswith("2026-08-05")
    assert [r["generatedAt"][:10] for r in store.load_market_reads()] == ["2026-08-05", "2026-08-04"]


def test_a_second_edition_same_day_revises_that_days_file(tmp_path: Path) -> None:
    """Intraday editions are revisions of the day's read, not rival entries in the trail."""
    store = MarketStore(tmp_path / "market")
    store.save_market_read({"regime": "chop", "generatedAt": "2026-08-05T13:45:00Z"})
    store.save_market_read({"regime": "risk-on", "generatedAt": "2026-08-05T17:30:00Z"})

    archived = store.load_market_reads()
    assert len(archived) == 1
    assert archived[0]["regime"] == "risk-on"


def test_a_read_without_a_usable_timestamp_is_not_archived(tmp_path: Path) -> None:
    """Better no trail entry than one filed under a garbage date."""
    store = MarketStore(tmp_path / "market")
    store.save_market_read({"regime": "chop", "generatedAt": ""})
    assert store.load_market_reads() == []
    assert store.load_market_read() is not None  # latest still written


def test_loaders_are_empty_before_anything_is_archived(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    assert store.load_market_reads() == []
    assert store.load_morning_briefs() == []


def test_archives_come_back_newest_first_and_respect_limit(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")
    for day in ("2026-08-01", "2026-08-02", "2026-08-03"):
        store.save_morning_brief(_brief(day))
    assert [b["briefDate"] for b in store.load_morning_briefs(limit=2)] == ["2026-08-03", "2026-08-02"]


# ---------- the trail ----------


def test_history_reads_oldest_first_and_joins_the_model_call() -> None:
    section = market_history_section(
        [_brief("2026-08-05", "flips today"), _brief("2026-08-04", "quiet tape")],
        [_read("2026-08-04", "chop")],
    )
    assert section is not None
    body = section.split("\n")
    # Oldest first, so the trail reads forward in time.
    assert "2026-08-04" in body[1] and "2026-08-05" in body[2]
    assert "model called: chop" in body[1]
    # No archived read for the 5th — the row still renders, just without a call.
    assert "model called" not in body[2]


def test_history_matches_reads_by_date_not_by_position() -> None:
    """Briefs go ~30 days deep while reads only start where archiving started. Zipping these
    positionally would attribute yesterday's call to a session it was never made for."""
    section = market_history_section(
        [_brief("2026-08-05"), _brief("2026-08-04"), _brief("2026-08-03")],
        [_read("2026-08-03", "risk-off")],
    )
    assert section is not None
    rows = {line.strip()[:10]: line for line in section.split("\n")[1:]}
    assert "model called: risk-off" in rows["2026-08-03"]
    assert "model called" not in rows["2026-08-04"]


def test_history_renders_rotation_and_flips() -> None:
    section = market_history_section(
        [
            _brief(
                "2026-08-04",
                "XLB rotated",
                rrgShifts=[{"symbol": "XLB", "fromQuadrant": "lagging", "toQuadrant": "improving"}],
                signalFlips=[{"symbol": "META", "kind": "trend"}],
            )
        ],
        [],
    )
    assert section is not None
    assert "XLB lagging->improving" in section
    assert "META trend" in section


def test_history_is_absent_when_there_is_no_trail() -> None:
    assert market_history_section([], []) is None
    assert market_history_section([{"headline": "no date"}], []) is None
