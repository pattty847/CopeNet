"""Deterministic whole-period orientation for a frozen candle resource."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from statistics import fmean, pstdev

DIGEST_VERSION = "period-v1"


def utc_timestamp(value: int | float | None) -> str | None:
    if type(value) not in (int, float):
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def rows_in_window(rows: list[dict], window: dict) -> list[dict]:
    start, end = window.get("from"), window.get("to")
    return [
        row for row in rows
        if type(row.get("t")) in (int, float)
        and (start is None or row["t"] >= start)
        and (end is None or row["t"] <= end)
    ]


def build_period_digest(resource: dict, rows: list[dict]) -> dict:
    """Summarize every completed visible bar while keeping its exact source addressable."""
    completed, unconfirmed, completion = _split_completion(resource, rows)
    valid = [row for row in completed if _number(row.get("c"))]
    digest = {
        "version": DIGEST_VERSION,
        "resourceKey": resource["key"],
        "timeframe": resource.get("metadata", {}).get("timeframe"),
        "visibleBarCount": len(rows),
        "completedBarCount": len(completed),
        "unconfirmedBarCount": len(unconfirmed),
        "completion": completion,
        "visibleRange": _time_range(rows),
        "completedRange": _time_range(completed),
        "latestCapturedBar": rows[-1] if rows else None,
        "latestCompletedBar": completed[-1] if completed else None,
        "facts": {},
        "chronology": _chronology(valid),
        "definitions": {
            "periodReturnPct": "(last completed close / first completed close - 1) * 100",
            "maxCloseDrawdownPct": "Largest completed-close decline from a prior completed-close peak",
            "closeReturnStdDevPct": "Population standard deviation of consecutive completed close returns; not annualized",
            "atr14": "Mean true range over the latest 14 completed bars",
            "latestVolumeVs20BarMean": "Latest completed volume / mean volume of up to 20 completed bars",
        },
    }
    if not valid:
        return digest

    first, last = valid[0], valid[-1]
    facts = digest["facts"]
    facts["firstCompletedClose"] = {"t": first["t"], "value": first["c"]}
    facts["lastCompletedClose"] = {"t": last["t"], "value": last["c"]}
    if first["c"] != 0:
        facts["periodReturnPct"] = (last["c"] / first["c"] - 1) * 100

    highs = [(row.get("h", row["c"]), row) for row in valid if _number(row.get("h", row["c"]))]
    lows = [(row.get("l", row["c"]), row) for row in valid if _number(row.get("l", row["c"]))]
    if highs:
        value, row = max(highs, key=lambda pair: pair[0])
        facts["highestHigh"] = {"t": row["t"], "value": value}
    if lows:
        value, row = min(lows, key=lambda pair: pair[0])
        facts["lowestLow"] = {"t": row["t"], "value": value}

    drawdown = _max_drawdown(valid)
    if drawdown:
        facts["maxCloseDrawdownPct"] = drawdown
    returns = [(current["c"] / prior["c"] - 1) * 100 for prior, current in zip(valid, valid[1:]) if prior["c"] != 0]
    if returns:
        facts["closeReturnStdDevPct"] = pstdev(returns)
    atr = _atr14(valid)
    if atr is not None:
        facts["atr14"] = atr
    volumes = [row["v"] for row in valid[-20:] if _number(row.get("v"))]
    if volumes and _number(last.get("v")) and fmean(volumes) != 0:
        facts["latestVolumeVs20BarMean"] = last["v"] / fmean(volumes)
    return digest


def adaptive_row_selection(rows: list[dict], target: int) -> tuple[list[dict], list[int]]:
    """Retain edges, structural events and chronological coverage deterministically."""
    if target <= 0 or not rows:
        return [], []
    if len(rows) <= target:
        return list(rows), list(range(len(rows)))

    priority: list[int] = []

    def add(index: int, neighbors: int = 0) -> None:
        for value in range(max(index - neighbors, 0), min(index + neighbors + 1, len(rows))):
            if value not in priority:
                priority.append(value)

    add(0)
    add(len(rows) - 1)

    numeric_highs = [(row.get("h", row.get("c")), index) for index, row in enumerate(rows) if _number(row.get("h", row.get("c")))]
    numeric_lows = [(row.get("l", row.get("c")), index) for index, row in enumerate(rows) if _number(row.get("l", row.get("c")))]
    if numeric_highs:
        add(max(numeric_highs)[1], 2)
    if numeric_lows:
        add(min(numeric_lows)[1], 2)

    valid = [(index, row) for index, row in enumerate(rows) if _number(row.get("c"))]
    drawdown = _max_drawdown([row for _, row in valid])
    if drawdown:
        by_time = {row["t"]: index for index, row in valid}
        add(by_time[drawdown["peakT"]], 2)
        add(by_time[drawdown["troughT"]], 2)

    volume = sorted(
        ((row.get("v"), index) for index, row in enumerate(rows) if _number(row.get("v"))),
        reverse=True,
    )
    for _, index in volume[:4]:
        add(index, 1)
    gaps = sorted(
        ((abs(row.get("o", prior.get("c")) - prior["c"]), index)
         for index, (prior, row) in enumerate(zip(rows, rows[1:]), start=1)
         if _number(prior.get("c")) and _number(row.get("o", prior.get("c")))),
        reverse=True,
    )
    for _, index in gaps[:4]:
        add(index, 1)

    for index in range(min(4, len(rows))):
        add(index)
    for index in range(max(len(rows) - 16, 0), len(rows)):
        add(index)

    if target == 1:
        return [rows[-1]], [len(rows) - 1]
    for position in range(target):
        add(round(position * (len(rows) - 1) / (target - 1)))
    indexes = sorted(priority[:target])
    return [rows[index] for index in indexes], indexes


def contiguous_index_ranges(rows: list[dict], indexes: list[int]) -> list[dict]:
    if not indexes:
        return []
    ranges, start, previous = [], indexes[0], indexes[0]
    for index in indexes[1:]:
        if index == previous + 1:
            previous = index
            continue
        ranges.append(_index_range(rows, start, previous))
        start = previous = index
    ranges.append(_index_range(rows, start, previous))
    return ranges


def _split_completion(resource: dict, rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    declared = resource.get("metadata", {}).get("completion")
    cutoff = declared.get("completedThrough") if isinstance(declared, dict) else None
    if type(cutoff) in (int, float):
        completed = [row for row in rows if row.get("t") <= cutoff]
        return completed, [row for row in rows if row.get("t") > cutoff], {
            "policy": "declared_cutoff",
            "status": declared.get("status"),
            "completedThrough": cutoff,
            "completedThroughUtc": utc_timestamp(cutoff),
            "completedCloseAt": declared.get("completedCloseAt"),
        }
    completed = rows[:-1] if rows else []
    return completed, rows[-1:] if rows else [], {
        "policy": "conservative_latest_excluded",
        "status": declared.get("status", "unknown") if isinstance(declared, dict) else "unknown",
        "error": declared.get("error") if isinstance(declared, dict) else None,
        "notice": "No timeframe-specific completion cutoff was captured; the latest bar is excluded from completed-bar facts.",
    }


def _chronology(rows: list[dict], buckets: int = 8) -> list[dict]:
    if not rows:
        return []
    size = math.ceil(len(rows) / min(buckets, len(rows)))
    result = []
    for start in range(0, len(rows), size):
        group = rows[start:start + size]
        highs = [row.get("h", row["c"]) for row in group if _number(row.get("h", row["c"]))]
        lows = [row.get("l", row["c"]) for row in group if _number(row.get("l", row["c"]))]
        entry = {
            "from": group[0]["t"], "to": group[-1]["t"],
            "fromUtc": utc_timestamp(group[0]["t"]), "toUtc": utc_timestamp(group[-1]["t"]),
            "bars": len(group), "firstClose": group[0]["c"], "lastClose": group[-1]["c"],
        }
        if group[0]["c"] != 0:
            entry["returnPct"] = (group[-1]["c"] / group[0]["c"] - 1) * 100
        if highs:
            entry["high"] = max(highs)
        if lows:
            entry["low"] = min(lows)
        result.append(entry)
    return result


def _max_drawdown(rows: list[dict]) -> dict | None:
    valid = [row for row in rows if _number(row.get("c"))]
    if not valid:
        return None
    peak = valid[0]
    worst = None
    for row in valid:
        if row["c"] > peak["c"]:
            peak = row
        if peak["c"] == 0:
            continue
        decline = (row["c"] / peak["c"] - 1) * 100
        if worst is None or decline < worst["value"]:
            worst = {"value": decline, "peakT": peak["t"], "troughT": row["t"]}
    return worst


def _atr14(rows: list[dict]) -> float | None:
    if len(rows) < 14:
        return None
    ranges = []
    for index, row in enumerate(rows):
        if not _number(row.get("h")) or not _number(row.get("l")):
            continue
        prior_close = rows[index - 1].get("c") if index else row.get("c")
        if not _number(prior_close):
            continue
        ranges.append(max(row["h"] - row["l"], abs(row["h"] - prior_close), abs(row["l"] - prior_close)))
    return fmean(ranges[-14:]) if len(ranges) >= 14 else None


def _time_range(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return {
        "from": rows[0]["t"], "to": rows[-1]["t"],
        "fromUtc": utc_timestamp(rows[0]["t"]), "toUtc": utc_timestamp(rows[-1]["t"]),
    }


def _index_range(rows: list[dict], start: int, end: int) -> dict:
    result = {"fromIndex": start, "toIndex": end}
    if "t" in rows[start] and "t" in rows[end]:
        result.update({"from": rows[start]["t"], "to": rows[end]["t"]})
    return result


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)
