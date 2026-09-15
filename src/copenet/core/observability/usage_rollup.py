"""Roll durable run records up into the operator's usage picture.

Pure functions over `RunRecord`s: no store access, no clock of its own, no new
collection. Everything here is already recorded per run — provider-reported
token usage, tool steps, coding metrics — and this module only groups it.

Three honesty rules the shapes encode:

- **Usage is provider-reported or absent.** A run whose provider reported
  nothing has `token_usage is None`; it is counted in `runs` and in
  `usageCoverage.runsWithoutUsage`, and contributes zero tokens. The rollup
  never substitutes `input_token_estimate` for usage, so a low token total on a
  provider that reports nothing reads as missing coverage, not as cheap runs.
- **Cached input is a subset of input.** `cachedInputTokens <= inputTokens`, so
  the daily by-type split is output / cache-read / fresh input, where
  `freshInputTokens = inputTokens - cachedInputTokens`. Stacking cached input
  beside input would double-count the whole cache.
- **A rate with no denominator is None, not zero.** `cacheHitRate` on a day with
  no reported input tokens is unknown; rendering it as 0% would read as a cache
  that missed every time.

No money: CopeNet runs on subscriptions, so there is no per-token price to
multiply by and any dollar figure here would be invented.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Iterable

from copenet.core.observability.usage_buckets import (
    TOKEN_KEYS,
    CodingBucket,
    TokenBucket,
    ToolBucket,
    parse_timestamp,
    ratio,
)
from copenet.core.runtime.runs import RunRecord

# Benchmark suites write their runs into sessions under this prefix. They are real
# runs with real usage, but they are not the operator's own work, so the rollup
# excludes them unless asked.
BENCH_SESSION_PREFIX = "bench-"


def is_bench_session(session_key: str) -> bool:
    """True for a benchmark-suite session, whose runs are not operator work."""
    return session_key.startswith(BENCH_SESSION_PREFIX)


def _usage_of(record: RunRecord) -> dict[str, Any] | None:
    """The run's provider-reported usage, or None. Never an estimate."""
    usage = record.token_usage
    if not isinstance(usage, dict) or not usage:
        return None
    if not any(usage.get(key) is not None for key in TOKEN_KEYS):
        return None
    return usage


def _duration_seconds(record: RunRecord, tz: tzinfo) -> float | None:
    started = parse_timestamp(record.started_at, tz)
    completed = parse_timestamp(record.completed_at, tz)
    if started is None or completed is None:
        return None
    seconds = (completed - started).total_seconds()
    return seconds if seconds >= 0 else None


def build_usage_rollup(
    records: Iterable[RunRecord],
    *,
    days: int,
    now: datetime,
    include_bench: bool = False,
    tz: tzinfo | None = None,
    top_limit: int = 12,
) -> dict[str, Any]:
    """Group run records into the Usage view's payload.

    `days` is a window of whole local days ending with the local day of `now`, so
    `days=1` means "today" and `days=30` means today plus the 29 days before it.
    Every calendar day in the window appears in `daily`, zero-filled, so the
    heatmap and the bar chart do not silently close gaps where nothing ran.
    """
    tz = tz or (now.tzinfo or timezone.utc)
    days = max(1, int(days))
    now_local = now.astimezone(tz)
    end_day = now_local.date()
    start_day = end_day - timedelta(days=days - 1)

    totals = TokenBucket()
    coding = CodingBucket()
    by_model: dict[tuple[str, str], TokenBucket] = defaultdict(TokenBucket)
    by_provider: dict[str, TokenBucket] = defaultdict(TokenBucket)
    by_tool: dict[str, ToolBucket] = defaultdict(ToolBucket)
    by_day: dict[str, TokenBucket] = defaultdict(TokenBucket)
    coding_by_day: dict[str, CodingBucket] = defaultdict(CodingBucket)
    by_weekday: dict[int, TokenBucket] = defaultdict(TokenBucket)
    by_hour: dict[int, TokenBucket] = defaultdict(TokenBucket)

    bench_runs_excluded = 0
    undated_runs = 0
    durations: list[float] = []
    first_run_at: str | None = None
    last_run_at: str | None = None

    for record in records:
        if is_bench_session(record.session_key) and not include_bench:
            bench_runs_excluded += 1
            continue
        started = parse_timestamp(record.started_at, tz)
        if started is None:
            undated_runs += 1
            continue
        day = started.date()
        if day < start_day or day > end_day:
            continue

        usage = _usage_of(record)
        day_key = day.isoformat()
        provider = record.provider or "unknown"
        model = record.model or "unknown"

        totals.add(record, usage)
        by_model[(provider, model)].add(record, usage)
        by_provider[provider].add(record, usage)
        by_day[day_key].add(record, usage)
        by_weekday[day.weekday()].add(record, usage)
        by_hour[started.hour].add(record, usage)

        if isinstance(record.coding_metrics, dict) and record.coding_metrics:
            coding.add(record.coding_metrics)
            coding_by_day[day_key].add(record.coding_metrics)

        for step in record.tool_steps:
            tool_id = str(step.get("toolId") or "").strip() or "unknown"
            by_tool[tool_id].add(record.run_id, step)

        duration = _duration_seconds(record, tz)
        if duration is not None:
            durations.append(duration)
        if first_run_at is None or record.started_at < first_run_at:
            first_run_at = record.started_at
        if last_run_at is None or record.started_at > last_run_at:
            last_run_at = record.started_at

    daily = [
        _day_row(day_key, by_day.get(day_key), coding_by_day.get(day_key))
        for day_key in _day_keys(start_day, end_day)
    ]

    return {
        "range": {
            "days": days,
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "generatedAt": now_local.isoformat(),
            "timezone": now_local.tzname() or "",
        },
        "includeBench": include_bench,
        "benchRunsExcluded": bench_runs_excluded,
        "undatedRunsSkipped": undated_runs,
        "totals": _overview(totals, by_tool, daily, durations, first_run_at, last_run_at),
        "usageCoverage": {
            "runs": totals.runs,
            "runsWithUsage": totals.runs_with_usage,
            "runsWithoutUsage": totals.runs - totals.runs_with_usage,
            "ratio": ratio(totals.runs_with_usage, totals.runs),
        },
        "models": _top_models(by_model, top_limit),
        "providers": _top_named(by_provider, "provider", top_limit),
        "tools": _top_tools(by_tool, top_limit),
        "daily": daily,
        "weekday": [_index_row("weekday", index, by_weekday.get(index)) for index in range(7)],
        "hourly": [_index_row("hour", index, by_hour.get(index)) for index in range(24)],
        "coding": {
            **coding.to_public_dict(),
            "daily": [{"date": row["date"], **row["coding"]} for row in daily],
        },
    }


def _overview(
    totals: TokenBucket,
    by_tool: dict[str, ToolBucket],
    daily: list[dict[str, Any]],
    durations: list[float],
    first_run_at: str | None,
    last_run_at: str | None,
) -> dict[str, Any]:
    """The tile strip's numbers: the totals plus what only the groupings know."""
    tool_failures = sum(bucket.failures for bucket in by_tool.values())
    tool_blocked = sum(bucket.blocked for bucket in by_tool.values())
    busiest = max(daily, key=lambda row: row["totalTokens"], default=None)
    return {
        **totals.to_public_dict(),
        "toolFailures": tool_failures,
        "toolBlocked": tool_blocked,
        "toolFailureRate": ratio(tool_failures, totals.tool_calls),
        "distinctTools": len(by_tool),
        "avgToolCallsPerRun": round(totals.tool_calls / totals.runs, 2) if totals.runs else None,
        "avgTokensPerRun": round(totals.total_tokens / totals.runs_with_usage) if totals.runs_with_usage else None,
        "avgOutputTokensPerRun": (
            round(totals.output_tokens / totals.runs_with_usage) if totals.runs_with_usage else None
        ),
        "avgRunSeconds": round(sum(durations) / len(durations), 1) if durations else None,
        "firstRunAt": first_run_at,
        "lastRunAt": last_run_at,
        "busiestDay": busiest["date"] if busiest and busiest["totalTokens"] > 0 else None,
    }


def _day_keys(start_day: date, end_day: date) -> list[str]:
    keys: list[str] = []
    cursor = start_day
    while cursor <= end_day:
        keys.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return keys


def _day_row(day_key: str, bucket: TokenBucket | None, coding: CodingBucket | None) -> dict[str, Any]:
    return {
        "date": day_key,
        **(bucket or TokenBucket()).to_public_dict(),
        "coding": (coding or CodingBucket()).to_day_dict(),
    }


def _index_row(key: str, index: int, bucket: TokenBucket | None) -> dict[str, Any]:
    return {key: index, **(bucket or TokenBucket()).to_public_dict()}


def _rank(row: dict[str, Any]) -> tuple[int, int, int]:
    """Rank by tokens, then runs, then tool calls — a provider that reports no usage
    still ranks by the work it did instead of sinking silently to the bottom."""
    return (row["totalTokens"], row["runs"], row["toolCalls"])


def _top_models(buckets: dict[tuple[str, str], TokenBucket], limit: int) -> list[dict[str, Any]]:
    rows = [
        {"provider": provider, "model": model, **bucket.to_public_dict()}
        for (provider, model), bucket in buckets.items()
    ]
    rows.sort(key=_rank, reverse=True)
    return rows[:limit]


def _top_named(buckets: dict[str, TokenBucket], key: str, limit: int) -> list[dict[str, Any]]:
    rows = [{key: name, **bucket.to_public_dict()} for name, bucket in buckets.items()]
    rows.sort(key=_rank, reverse=True)
    return rows[:limit]


def _top_tools(buckets: dict[str, ToolBucket], limit: int) -> list[dict[str, Any]]:
    rows = [bucket.to_public_dict(tool_id) for tool_id, bucket in buckets.items()]
    rows.sort(key=lambda row: (row["calls"], row["runs"]), reverse=True)
    return rows[:limit]
