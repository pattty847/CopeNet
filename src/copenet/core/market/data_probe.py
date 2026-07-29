"""Read-only intraday market-data capability probes.

This module deliberately sits outside the production MarketRuntime. It measures what a
vendor actually returns before CopeNet relies on that data for alert evaluation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import UTC, datetime
import time
from typing import Any

import pandas as pd

from .data_probe_analysis import (
    US_EQUITY_SESSION_PROFILE,
    US_EQUITY_TIMEZONE,
    IntradayProbeSpec,
    analyze_intraday_frame,
    empty_session_summaries,
    interval_volume_observation,
)


DEFAULT_INTRADAY_PROBE_SPECS = (
    IntradayProbeSpec(interval="1m", period="5d"),
    IntradayProbeSpec(interval="5m", period="1mo"),
    IntradayProbeSpec(interval="1h", period="1mo"),
)

FrameDownloader = Callable[..., pd.DataFrame]


def run_yfinance_intraday_probe(
    symbols: Iterable[str],
    *,
    specs: Iterable[IntradayProbeSpec] = DEFAULT_INTRADAY_PROBE_SPECS,
    timezone_name: str = US_EQUITY_TIMEZONE,
    pause_seconds: float = 1.0,
    downloader: FrameDownloader | None = None,
) -> dict[str, Any]:
    """Probe symbols sequentially and return a compact, durable capability report."""
    if timezone_name != US_EQUITY_TIMEZONE:
        raise ValueError(
            f"{US_EQUITY_SESSION_PROFILE} requires timezone {US_EQUITY_TIMEZONE}"
        )
    normalized_symbols = _normalized_symbols(symbols)
    normalized_specs = tuple(specs)
    fetch = downloader or _download_yfinance_frame
    vendor_version = _yfinance_version() if downloader is None else "injected"
    results: list[dict[str, Any]] = []

    request_index = 0
    for symbol in normalized_symbols:
        for spec in normalized_specs:
            if request_index and pause_seconds > 0:
                time.sleep(pause_seconds)
            request_index += 1
            started = time.monotonic()
            try:
                frame = fetch(
                    symbol,
                    interval=spec.interval,
                    period=spec.period,
                    prepost=spec.include_extended_hours,
                )
                result = analyze_intraday_frame(
                    symbol,
                    frame,
                    spec=spec,
                    timezone_name=timezone_name,
                )
            except Exception as exc:
                result = _failed_result(symbol, spec, exc)
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            results.append(result)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "vendor": "yfinance",
        "vendor_version": vendor_version,
        "timezone": timezone_name,
        "session_profile": {
            "name": US_EQUITY_SESSION_PROFILE,
            "calendar_aware": False,
            "bar_classification": "start_timestamp",
        },
        "request_count": len(results),
        "symbols": [
            _symbol_report(symbol, [result for result in results if result["symbol"] == symbol])
            for symbol in normalized_symbols
        ],
    }


def probe_report_has_errors(report: dict[str, Any]) -> bool:
    return any(
        result["status"] == "error"
        for symbol in report["symbols"]
        for result in symbol["results"]
    )


def safe_probe_filename_part(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value
    )
    return cleaned.strip("._") or "symbol"


def _download_yfinance_frame(
    symbol: str,
    *,
    interval: str,
    period: str,
    prepost: bool,
) -> pd.DataFrame:
    import yfinance as yf

    # The split-adjustment invariant applies even to experiments. Raw vendor intraday
    # data must never accidentally establish a second price basis in CopeNet.
    return yf.download(
        symbol,
        interval=interval,
        period=period,
        prepost=prepost,
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=15,
    )


def _symbol_report(symbol: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [result for result in results if result["status"] == "ok"]
    return {
        "symbol": symbol,
        "capabilities": {
            "supported_intervals": list(
                dict.fromkeys(result["interval"] for result in successful)
            ),
            "volume_observations_by_spec": {
                _probe_spec_identity(result): interval_volume_observation(result)
                for result in successful
            },
            "assumed_extended_price_intervals": list(
                dict.fromkeys(
                    result["interval"]
                    for result in successful
                    if result["sessions"]["premarket"]["row_count"]
                    + result["sessions"]["afterhours"]["row_count"]
                    > 0
                )
            ),
        },
        "results": results,
    }


def _probe_spec_identity(result: dict[str, Any]) -> str:
    session = "extended" if result["include_extended_hours"] else "regular"
    return f"{result['interval']}:{result['period']}:{session}"


def _failed_result(
    symbol: str,
    spec: IntradayProbeSpec,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        **asdict(spec),
        "status": "error",
        "row_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "timestamps_monotonic": True,
        "duplicate_timestamps": 0,
        "volume_field_present": False,
        "null_volume_rows": 0,
        "sessions": empty_session_summaries(),
        "session_profile": US_EQUITY_SESSION_PROFILE,
        "latest_session_date": None,
        "sample_bars": [],
        "warnings": [],
        "error": f"{type(exc).__name__}: {exc}",
    }


def _normalized_symbols(symbols: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = symbol.strip().upper()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    if not normalized:
        raise ValueError("at least one symbol is required")
    return normalized


def _yfinance_version() -> str:
    import yfinance as yf

    return str(yf.__version__)
