from __future__ import annotations

import pandas as pd

from copenet.core.market.data_probe import (
    IntradayProbeSpec,
    analyze_intraday_frame,
    probe_report_has_errors,
    run_yfinance_intraday_probe,
    safe_probe_filename_part,
)


def _frame(rows: list[tuple[str, float, int]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([timestamp for timestamp, _, _ in rows])
    close = [price for _, price, _ in rows]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [price + 0.5 for price in close],
            "Low": [price - 0.5 for price in close],
            "Close": close,
            "Volume": [volume for _, _, volume in rows],
        },
        index=index,
    )


def test_analyze_intraday_frame_reports_session_volume_and_samples() -> None:
    frame = _frame(
        [
            ("2026-07-28T08:00:00Z", 201.0, 0),   # 04:00 ET premarket
            ("2026-07-28T13:30:00Z", 202.0, 100), # 09:30 ET regular
            ("2026-07-28T19:55:00Z", 203.0, 200), # 15:55 ET regular
            ("2026-07-28T20:00:00Z", 204.0, 0),   # 16:00 ET after-hours
            ("2026-07-28T23:55:00Z", 205.0, 0),   # 19:55 ET after-hours
        ]
    )

    result = analyze_intraday_frame(
        "aapl",
        frame,
        spec=IntradayProbeSpec(interval="5m", period="1d"),
    )

    assert result["status"] == "ok"
    assert result["symbol"] == "AAPL"
    assert result["sessions"]["premarket"] == {
        "row_count": 1,
        "reported_volume_rows": 1,
        "nonzero_volume_rows": 0,
        "total_volume": 0,
        "reported_volume_coverage_pct": 100.0,
        "nonzero_volume_coverage_pct": 0.0,
        "nonzero_volume_sample_timestamps": [],
    }
    assert result["sessions"]["regular"]["nonzero_volume_rows"] == 2
    assert result["sessions"]["regular"]["total_volume"] == 300
    assert result["sessions"]["regular"]["nonzero_volume_coverage_pct"] == 100.0
    assert result["sessions"]["afterhours"]["row_count"] == 2
    assert result["warnings"] == ["extended-hours volume values are present but all are zero"]
    assert [row["session"] for row in result["sample_bars"]] == [
        "premarket",
        "regular",
        "regular",
        "afterhours",
        "afterhours",
    ]


def test_run_yfinance_intraday_probe_derives_symbol_capabilities_without_network() -> None:
    frames = {
        "AAPL": _frame(
            [
                ("2026-07-28T08:00:00Z", 201.0, 5),
                ("2026-07-28T13:30:00Z", 202.0, 100),
                ("2026-07-28T20:00:00Z", 203.0, 7),
            ]
        ),
        "VIX": _frame(
            [
                ("2026-07-28T13:30:00Z", 17.0, 0),
                ("2026-07-28T13:35:00Z", 17.1, 0),
            ]
        ),
    }
    calls: list[tuple[str, str, str, bool]] = []

    def downloader(symbol: str, *, interval: str, period: str, prepost: bool) -> pd.DataFrame:
        calls.append((symbol, interval, period, prepost))
        return frames[symbol]

    report = run_yfinance_intraday_probe(
        ["aapl", "AAPL", "vix"],
        specs=[IntradayProbeSpec(interval="5m", period="1d")],
        pause_seconds=0,
        downloader=downloader,
    )

    assert calls == [
        ("AAPL", "5m", "1d", True),
        ("VIX", "5m", "1d", True),
    ]
    assert report["request_count"] == 2
    assert report["vendor_version"] == "injected"
    capabilities = report["symbols"][0]["capabilities"]
    assert capabilities["supported_intervals"] == ["5m"]
    assert capabilities["assumed_extended_price_intervals"] == ["5m"]
    assert capabilities["volume_observations_by_spec"]["5m:1d:extended"] == {
        "volume_field_present": True,
        "regular": {
            "row_count": 1,
            "reported_volume_rows": 1,
            "nonzero_volume_rows": 1,
        },
        "assumed_extended": {
            "row_count": 2,
            "reported_volume_rows": 2,
            "nonzero_volume_rows": 2,
        },
        "usable_for_vwap": "unverified",
    }
    assert (
        report["symbols"][1]["capabilities"]["volume_observations_by_spec"][
            "5m:1d:extended"
        ]["regular"][
            "nonzero_volume_rows"
        ]
        == 0
    )


def test_analyze_intraday_frame_returns_honest_empty_state() -> None:
    result = analyze_intraday_frame(
        "MISSING",
        pd.DataFrame(),
        spec=IntradayProbeSpec(interval="1m", period="5d"),
    )

    assert result["status"] == "no_data"
    assert result["row_count"] == 0
    assert result["warnings"] == ["vendor returned no bars"]


def test_run_yfinance_intraday_probe_does_not_treat_sparse_boundary_volume_as_usable() -> None:
    rows = [
        (f"2026-07-28T{hour:02d}:{minute:02d}:00Z", 200.0 + index, 0)
        for index, (hour, minute) in enumerate(
            [
                (8, 0),
                (8, 5),
                (8, 10),
                (8, 15),
                (8, 20),
                (8, 25),
                (8, 30),
                (8, 35),
                (8, 40),
                (8, 45),
                (8, 50),
                (8, 55),
                (9, 0),
                (9, 5),
                (9, 10),
                (9, 15),
                (9, 20),
                (9, 25),
                (9, 30),
                (9, 35),
                (20, 0),
            ]
        )
    ]
    rows[-1] = (rows[-1][0], rows[-1][1], 500_000)

    report = run_yfinance_intraday_probe(
        ["AAPL"],
        specs=[IntradayProbeSpec(interval="1m", period="1d")],
        pause_seconds=0,
        downloader=lambda *_args, **_kwargs: _frame(rows),
    )

    observation = report["symbols"][0]["capabilities"]["volume_observations_by_spec"][
        "1m:1d:extended"
    ]
    assert observation["assumed_extended"] == {
        "row_count": 21,
        "reported_volume_rows": 21,
        "nonzero_volume_rows": 1,
    }
    assert observation["usable_for_vwap"] == "unverified"
    assert "fidelity remains unverified" in report["symbols"][0]["results"][0]["warnings"][0]


def test_probe_output_filename_does_not_trust_symbol_text() -> None:
    assert safe_probe_filename_part("^VIX") == "VIX"
    assert safe_probe_filename_part("../../AAPL") == "AAPL"


def test_analyze_intraday_frame_preserves_missing_volume_and_original_order_facts() -> None:
    frame = pd.DataFrame(
        {
            "Open": [202.0, 201.0],
            "High": [202.5, 201.5],
            "Low": [201.5, 200.5],
            "Close": [202.0, 201.0],
        },
        index=pd.DatetimeIndex(
            [
                "2026-07-28T13:35:00Z",
                "2026-07-28T13:30:00Z",
            ]
        ),
    )

    result = analyze_intraday_frame(
        "AAPL",
        frame,
        spec=IntradayProbeSpec(interval="5m", period="1d"),
    )

    assert result["volume_field_present"] is False
    assert result["null_volume_rows"] == 2
    assert result["timestamps_monotonic"] is False
    assert result["sessions"]["regular"]["reported_volume_rows"] == 0
    assert result["sessions"]["regular"]["total_volume"] is None
    assert result["warnings"] == [
        "vendor response did not include a volume field",
        "regular-session volume values are unavailable",
        "vendor timestamps were not monotonic before normalization",
    ]


def test_probe_report_detects_when_any_vendor_request_errors() -> None:
    report = {
        "symbols": [
            {
                "results": [
                    {"status": "ok"},
                    {"status": "error"},
                ]
            }
        ]
    }

    assert probe_report_has_errors(report) is True
    report["symbols"][0]["results"][1]["status"] = "no_data"
    assert probe_report_has_errors(report) is False


def test_probe_keeps_repeated_interval_observations_by_full_spec() -> None:
    report = run_yfinance_intraday_probe(
        ["AAPL"],
        specs=[
            IntradayProbeSpec(interval="5m", period="1d"),
            IntradayProbeSpec(interval="5m", period="1mo"),
        ],
        pause_seconds=0,
        downloader=lambda *_args, **_kwargs: _frame(
            [("2026-07-28T13:30:00Z", 202.0, 100)]
        ),
    )

    capabilities = report["symbols"][0]["capabilities"]
    assert capabilities["supported_intervals"] == ["5m"]
    assert list(capabilities["volume_observations_by_spec"]) == [
        "5m:1d:extended",
        "5m:1mo:extended",
    ]


def test_us_equity_session_profile_rejects_a_conflicting_timezone() -> None:
    try:
        run_yfinance_intraday_probe(
            ["AAPL"],
            timezone_name="Europe/London",
            pause_seconds=0,
            downloader=lambda *_args, **_kwargs: pd.DataFrame(),
        )
    except ValueError as exc:
        assert "America/New_York" in str(exc)
    else:
        raise AssertionError("expected the US-equity session profile to reject another timezone")


def test_null_volume_count_only_includes_retained_price_rows() -> None:
    frame = pd.DataFrame(
        {
            "Open": [202.0, 201.0],
            "High": [202.5, 201.5],
            "Low": [201.5, 200.5],
            "Close": [202.0, None],
            "Volume": [None, None],
        },
        index=pd.DatetimeIndex(
            [
                "2026-07-28T13:30:00Z",
                "2026-07-28T13:35:00Z",
            ]
        ),
    )

    result = analyze_intraday_frame(
        "AAPL",
        frame,
        spec=IntradayProbeSpec(interval="5m", period="1d"),
    )

    assert result["row_count"] == 1
    assert result["null_volume_rows"] == 1
