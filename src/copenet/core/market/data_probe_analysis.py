"""Pure analysis helpers for intraday market-data capability probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import time as wall_time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

US_EQUITY_TIMEZONE = "America/New_York"
US_EQUITY_SESSION_PROFILE = "us_equity_assumed"

_SESSION_ORDER = ("premarket", "regular", "afterhours", "off_session")
_SESSION_WINDOWS = {
    "premarket": (wall_time(4, 0), wall_time(9, 30)),
    "regular": (wall_time(9, 30), wall_time(16, 0)),
    "afterhours": (wall_time(16, 0), wall_time(20, 0)),
}


@dataclass(frozen=True)
class IntradayProbeSpec:
    interval: str
    period: str
    include_extended_hours: bool = True


@dataclass(frozen=True)
class _NormalizedFrame:
    frame: pd.DataFrame
    timestamps_monotonic: bool
    volume_field_present: bool
    null_volume_rows: int


def analyze_intraday_frame(
    symbol: str,
    frame: pd.DataFrame,
    *,
    spec: IntradayProbeSpec,
    timezone_name: str = US_EQUITY_TIMEZONE,
) -> dict[str, Any]:
    """Summarize timestamps, session coverage, volume quality, and representative bars."""
    if timezone_name != US_EQUITY_TIMEZONE:
        raise ValueError(
            f"{US_EQUITY_SESSION_PROFILE} requires timezone {US_EQUITY_TIMEZONE}"
        )
    normalized_result = _normalized_intraday_frame(frame)
    normalized = normalized_result.frame
    timezone = ZoneInfo(timezone_name)
    if normalized.empty:
        return {
            "symbol": symbol.upper(),
            **asdict(spec),
            "status": "no_data",
            "row_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "timestamps_monotonic": normalized_result.timestamps_monotonic,
            "duplicate_timestamps": 0,
            "volume_field_present": normalized_result.volume_field_present,
            "null_volume_rows": normalized_result.null_volume_rows,
            "sessions": empty_session_summaries(),
            "session_profile": US_EQUITY_SESSION_PROFILE,
            "latest_session_date": None,
            "sample_bars": [],
            "warnings": ["vendor returned no bars"],
            "error": None,
        }

    local_index = normalized.index.tz_convert(timezone)
    session_labels = [_session_label(timestamp) for timestamp in local_index]
    sessions = _session_summaries(normalized, session_labels, local_index)
    duplicate_timestamps = int(normalized.index.duplicated().sum())
    warnings = _data_quality_warnings(
        sessions,
        duplicate_timestamps,
        timestamps_monotonic=normalized_result.timestamps_monotonic,
        volume_field_present=normalized_result.volume_field_present,
    )
    latest_session_date = max(timestamp.date() for timestamp in local_index).isoformat()

    return {
        "symbol": symbol.upper(),
        **asdict(spec),
        "status": "ok",
        "row_count": len(normalized),
        "first_timestamp": local_index[0].isoformat(),
        "last_timestamp": local_index[-1].isoformat(),
        "timestamps_monotonic": normalized_result.timestamps_monotonic,
        "duplicate_timestamps": duplicate_timestamps,
        "volume_field_present": normalized_result.volume_field_present,
        "null_volume_rows": normalized_result.null_volume_rows,
        "sessions": sessions,
        "session_profile": US_EQUITY_SESSION_PROFILE,
        "latest_session_date": latest_session_date,
        "sample_bars": _sample_latest_session_bars(
            normalized,
            local_index=local_index,
            session_labels=session_labels,
            latest_session_date=latest_session_date,
        ),
        "warnings": warnings,
        "error": None,
    }


def interval_volume_observation(result: dict[str, Any]) -> dict[str, Any]:
    sessions = result["sessions"]
    extended_rows, extended_reported_rows, extended_nonzero_rows = extended_volume_counts(
        sessions
    )
    regular = sessions["regular"]
    return {
        "volume_field_present": result["volume_field_present"],
        "regular": {
            "row_count": regular["row_count"],
            "reported_volume_rows": regular["reported_volume_rows"],
            "nonzero_volume_rows": regular["nonzero_volume_rows"],
        },
        "assumed_extended": {
            "row_count": extended_rows,
            "reported_volume_rows": extended_reported_rows,
            "nonzero_volume_rows": extended_nonzero_rows,
        },
        "usable_for_vwap": "unverified",
    }


def empty_session_summaries() -> dict[str, dict[str, Any]]:
    return {
        session: {
            "row_count": 0,
            "reported_volume_rows": 0,
            "nonzero_volume_rows": 0,
            "total_volume": None,
            "reported_volume_coverage_pct": 0.0,
            "nonzero_volume_coverage_pct": 0.0,
            "nonzero_volume_sample_timestamps": [],
        }
        for session in _SESSION_ORDER
    }


def extended_volume_counts(
    sessions: dict[str, dict[str, Any]],
) -> tuple[int, int, int]:
    return (
        int(sessions["premarket"]["row_count"]) + int(sessions["afterhours"]["row_count"]),
        int(sessions["premarket"]["reported_volume_rows"])
        + int(sessions["afterhours"]["reported_volume_rows"]),
        int(sessions["premarket"]["nonzero_volume_rows"])
        + int(sessions["afterhours"]["nonzero_volume_rows"]),
    )


def _normalized_intraday_frame(frame: pd.DataFrame | None) -> _NormalizedFrame:
    if frame is None or frame.empty:
        return _NormalizedFrame(
            frame=pd.DataFrame(columns=["open", "high", "low", "close", "volume"]),
            timestamps_monotonic=True,
            volume_field_present=False,
            null_volume_rows=0,
        )
    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [str(column[0]).lower() for column in normalized.columns]
    else:
        normalized.columns = [str(column).lower() for column in normalized.columns]
    required = ["open", "high", "low", "close"]
    if any(column not in normalized for column in required):
        raise ValueError(f"vendor frame is missing OHLC columns: {list(normalized.columns)}")
    parsed_index = pd.to_datetime(normalized.index, utc=True)
    timestamps_monotonic = bool(parsed_index.is_monotonic_increasing)
    volume_field_present = "volume" in normalized
    if volume_field_present:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
    else:
        normalized["volume"] = pd.Series(pd.NA, index=normalized.index, dtype="Float64")
    normalized.index = parsed_index
    normalized = normalized[["open", "high", "low", "close", "volume"]]
    normalized = normalized.dropna(subset=["close"]).sort_index()
    return _NormalizedFrame(
        frame=normalized,
        timestamps_monotonic=timestamps_monotonic,
        volume_field_present=volume_field_present,
        null_volume_rows=int(normalized["volume"].isna().sum()),
    )


def _session_label(timestamp: pd.Timestamp) -> str:
    current = timestamp.time().replace(tzinfo=None)
    for session, (start, end) in _SESSION_WINDOWS.items():
        if start <= current < end:
            return session
    return "off_session"


def _session_summaries(
    frame: pd.DataFrame,
    labels: list[str],
    local_index: pd.DatetimeIndex,
) -> dict[str, dict[str, Any]]:
    summaries = empty_session_summaries()
    volume = frame["volume"]
    for row_index, session in enumerate(labels):
        raw_value = volume.iloc[row_index]
        summaries[session]["row_count"] += 1
        if pd.isna(raw_value):
            continue
        value = int(raw_value)
        summaries[session]["reported_volume_rows"] += 1
        if value > 0:
            summaries[session]["nonzero_volume_rows"] += 1
            samples = summaries[session]["nonzero_volume_sample_timestamps"]
            if len(samples) < 6:
                samples.append(local_index[row_index].isoformat())
        total_volume = summaries[session]["total_volume"]
        summaries[session]["total_volume"] = value if total_volume is None else total_volume + value
    for summary in summaries.values():
        row_count = int(summary["row_count"])
        reported_rows = int(summary["reported_volume_rows"])
        nonzero_rows = int(summary["nonzero_volume_rows"])
        summary["reported_volume_coverage_pct"] = (
            round(reported_rows / row_count * 100, 2) if row_count else 0.0
        )
        summary["nonzero_volume_coverage_pct"] = (
            round(nonzero_rows / row_count * 100, 2) if row_count else 0.0
        )
    return summaries


def _data_quality_warnings(
    sessions: dict[str, dict[str, Any]],
    duplicate_timestamps: int,
    *,
    timestamps_monotonic: bool,
    volume_field_present: bool,
) -> list[str]:
    warnings: list[str] = []
    regular = sessions["regular"]
    extended_rows, extended_reported_rows, extended_nonzero_rows = extended_volume_counts(
        sessions
    )
    if not volume_field_present:
        warnings.append("vendor response did not include a volume field")
    if regular["row_count"] and not regular["reported_volume_rows"]:
        warnings.append("regular-session volume values are unavailable")
    elif regular["row_count"] and not regular["nonzero_volume_rows"]:
        warnings.append("regular-session volume values are present but all are zero")
    if extended_rows and not extended_reported_rows:
        warnings.append("extended-hours volume values are unavailable")
    elif extended_rows and not extended_nonzero_rows:
        warnings.append("extended-hours volume values are present but all are zero")
    elif extended_rows:
        warnings.append(
            "extended-hours nonzero volume observed on "
            f"{extended_nonzero_rows}/{extended_rows} bars; fidelity remains unverified"
        )
    if sessions["off_session"]["row_count"]:
        warnings.append("bars fall outside the assumed US-equity 04:00-20:00 session profile")
    if not timestamps_monotonic:
        warnings.append("vendor timestamps were not monotonic before normalization")
    if duplicate_timestamps:
        warnings.append(f"{duplicate_timestamps} duplicate timestamp(s) returned")
    return warnings


def _sample_latest_session_bars(
    frame: pd.DataFrame,
    *,
    local_index: pd.DatetimeIndex,
    session_labels: list[str],
    latest_session_date: str,
) -> list[dict[str, Any]]:
    candidates: dict[str, list[int]] = {session: [] for session in _SESSION_ORDER}
    for row_index, (timestamp, session) in enumerate(
        zip(local_index, session_labels, strict=True)
    ):
        if timestamp.date().isoformat() == latest_session_date:
            candidates[session].append(row_index)

    selected: list[int] = []
    for session in _SESSION_ORDER:
        indexes = candidates[session]
        if indexes:
            selected.append(indexes[0])
            if indexes[-1] != indexes[0]:
                selected.append(indexes[-1])

    samples: list[dict[str, Any]] = []
    for row_index in sorted(set(selected)):
        row = frame.iloc[row_index]
        volume = row["volume"]
        samples.append(
            {
                "timestamp": local_index[row_index].isoformat(),
                "session": session_labels[row_index],
                "open": round(float(row["open"]), 6),
                "high": round(float(row["high"]), 6),
                "low": round(float(row["low"]), 6),
                "close": round(float(row["close"]), 6),
                "volume": None if pd.isna(volume) else int(volume),
            }
        )
    return samples
