from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from copenet.core.market.stooq import STOOQ_BASIS, StooqUnavailable, load_archive
from copenet.core.market.stooq import participation as participation_module
from copenet.core.market.stooq.participation import (
    compute_participation,
    select_universe,
)

HEADER = "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>"


def _write(directory, symbol: str, closes: list[float], volumes: list[float]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    lines = [HEADER]
    for index, (close, volume) in enumerate(zip(closes, volumes)):
        day = (start + timedelta(days=index)).strftime("%Y%m%d")
        lines.append(
            f"{symbol.upper()}.US,D,{day},000000,{close},{close + 1},{close - 1},{close},{volume},0"
        )
    (directory / f"{symbol}.us.txt").write_text("\n".join(lines) + "\n")


@pytest.fixture()
def archive(tmp_path):
    root = tmp_path / "us"
    _write(root / "nyse stocks" / "1", "liquid", [100.0] * 300, [1_000_000.0] * 300)
    _write(root / "nasdaq stocks" / "1", "thin", [10.0] * 300, [100.0] * 300)
    # One enormous session on an otherwise untraded name: the reason the filter takes a
    # median and not a mean.
    _write(root / "nasdaq stocks" / "1", "spiky", [10.0] * 300, [50.0] * 299 + [900_000_000.0])
    _write(root / "nyse stocks" / "1", "short", [50.0] * 30, [1_000_000.0] * 30)
    _write(root / "nyse etfs", "fund", [100.0] * 300, [1_000_000.0] * 300)
    return load_archive(root)


def test_archive_separates_funds_from_common_stocks_by_folder(archive) -> None:
    assert set(archive.paths) == {"LIQUID", "THIN", "SPIKY", "SHORT", "FUND"}
    assert archive.equities == frozenset({"LIQUID", "THIN", "SPIKY", "SHORT"})
    assert "FUND" not in archive.equities


def test_reading_a_symbol_parses_the_stooq_layout_and_honours_a_limit(archive) -> None:
    bars = archive.read("liquid", limit=5)

    assert len(bars) == 5
    assert bars[0].close == 100.0 and bars[0].volume == 1_000_000.0
    assert bars[-1].date > bars[0].date
    assert archive.read("NOT_LISTED") == []


def test_a_missing_archive_is_reported_rather_than_silently_empty(tmp_path) -> None:
    with pytest.raises(StooqUnavailable):
        load_archive(tmp_path / "absent")


def test_universe_takes_liquid_common_stocks_and_ignores_one_day_volume_spikes(archive) -> None:
    universe = select_universe(archive, min_dollar_volume=1_000_000.0)

    assert universe == ["LIQUID"]
    assert "FUND" not in universe, "funds are not a common-stock population"
    assert "SHORT" not in universe, "too little history for a 200-day average"
    assert "SPIKY" not in universe, "a single huge session must not admit an untraded name"


def test_participation_percentages_always_carry_their_own_denominator(archive, monkeypatch) -> None:
    """A share without its coverage is unreadable: a fetch that lost most of the universe
    looks identical to a market that narrowed."""

    def evaluator(payload):
        rows = []
        for index, request in enumerate(payload["requests"]):
            if index == 0:  # one symbol still warming up: counted in coverage, not in the share
                rows.append({"key": request["key"], "t": 1, "error": None, "values": {
                    "ma50": {"value": 5.0}, "ma200": {"value": None},
                    "mama": {"mama": None, "fama": None}, "atr": {"atr": 2.0}}})
            else:
                rows.append({"key": request["key"], "t": 1, "error": None, "values": {
                    "ma50": {"value": 5.0}, "ma200": {"value": 8.0},
                    "mama": {"mama": 5.0, "fama": 3.0}, "atr": {"atr": 2.0}}})
        return {"results": rows}

    monkeypatch.setattr(participation_module, "evaluator_request", evaluator)
    result = compute_participation(archive, ["LIQUID", "THIN", "SPIKY"])
    summary = result.summary()

    assert summary["basis"] == STOOQ_BASIS
    assert summary["universe"] == 3 and summary["read"] == 3
    assert summary["pctAboveMa50"] == 100.0 and summary["pctAboveMa50Counted"] == 3
    # The warming-up symbol drops out of the 200-day share and out of its denominator too.
    assert summary["pctAboveMa200"] == 100.0 and summary["pctAboveMa200Counted"] == 2
    assert summary["pctMamaAboveFama"] == 100.0 and summary["pctMamaAboveFamaCounted"] == 2
    assert result.readings[1].mama_spread_atr == pytest.approx(1.0)


def test_an_unavailable_evaluator_records_errors_instead_of_reporting_zero(archive, monkeypatch) -> None:
    def unavailable(_payload):
        raise ValueError("Indicator evaluator unavailable")

    monkeypatch.setattr(participation_module, "evaluator_request", unavailable)
    result = compute_participation(archive, ["LIQUID", "THIN"])

    assert result.read == 0
    assert set(result.errors) == {"LIQUID", "THIN"}
    assert result.summary()["pctAboveMa200"] is None, "no data must read as unknown, never 0%"
