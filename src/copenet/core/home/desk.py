"""The desk snapshot: what ran lately, and whether the runtime is healthy.

Assembled here rather than in the client because the honest version of both questions is a
query across every session, and the client can only ask per session. Observability's own
fan-out — one `sessions.runs` call per active session — is what this exists to avoid.

Nothing in here is sampled or estimated: every number is counted from durable run records
or the session index. Metrics that would need a sampler CopeNet does not run (host memory,
for one) are absent rather than approximated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from copenet.core.runtime.runs import RunRecord

# One hour of buckets for the activity histograms. Five-minute resolution is fine enough to
# show a burst and coarse enough that an idle desk is not a row of single pixels.
HEALTH_WINDOW = timedelta(hours=1)
HEALTH_BUCKETS = 12


@dataclass
class ActivityEntry:
    """One recent run, as the desk reads it: what it was, and how it ended."""

    run_id: str
    session_key: str
    session_title: str
    provider: str
    model: str | None
    status: str
    summary: str
    tool_count: int
    started_at: str
    completed_at: str | None
    duration_ms: int | None
    errored: bool


@dataclass
class DeskHealth:
    """Runtime health over the last hour, counted from run records."""

    """Sessions that actually ran something in the last 24 hours. The count of un-archived
    sessions is a filing-cabinet number — this workspace has hundreds — and calling it
    "active" would make a healthy idle desk look busy."""
    active_sessions: int
    """Every un-archived session, said plainly rather than dressed up as activity."""
    total_sessions: int
    """Sessions currently holding an in-flight run — the real queue depth."""
    in_flight: int
    tool_calls: int
    error_rate: float
    """None when no run in the window completed; an average over nothing is not zero."""
    avg_latency_ms: int | None
    runs: int
    tool_call_series: list[int] = field(default_factory=list)
    run_series: list[int] = field(default_factory=list)
    error_series: list[int] = field(default_factory=list)


@dataclass
class DeskSnapshot:
    generated_at: str
    activity: list[ActivityEntry]
    health: DeskHealth
    quote: dict[str, str] | None

    def to_public_dict(self) -> dict:
        return {
            "generatedAt": self.generated_at,
            "activity": [
                {
                    "runId": entry.run_id,
                    "sessionKey": entry.session_key,
                    "sessionTitle": entry.session_title,
                    "provider": entry.provider,
                    "model": entry.model,
                    "status": entry.status,
                    "summary": entry.summary,
                    "toolCount": entry.tool_count,
                    "startedAt": entry.started_at,
                    "completedAt": entry.completed_at,
                    "durationMs": entry.duration_ms,
                    "errored": entry.errored,
                }
                for entry in self.activity
            ],
            "health": {
                "activeSessions": self.health.active_sessions,
                "totalSessions": self.health.total_sessions,
                "inFlight": self.health.in_flight,
                "toolCalls": self.health.tool_calls,
                "errorRate": self.health.error_rate,
                "avgLatencyMs": self.health.avg_latency_ms,
                "runs": self.health.runs,
                "toolCallSeries": self.health.tool_call_series,
                "runSeries": self.health.run_series,
                "errorSeries": self.health.error_series,
                "windowMinutes": int(HEALTH_WINDOW.total_seconds() // 60),
            },
            "quote": self.quote,
        }


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _errored(record: RunRecord) -> bool:
    return bool(record.error) or str(record.status).lower() in {"error", "failed"}


def _summary(record: RunRecord) -> str:
    """What the run was about. The operator's own words beat a generated summary; the
    output summary is the fallback, and an empty run says so rather than showing a blank."""
    for candidate in (record.user_message, record.output_summary):
        text = " ".join(str(candidate or "").split())
        if text:
            return text
    return "(no message)"


def build_desk_snapshot(
    *,
    runs: list[RunRecord],
    session_titles: dict[str, str],
    total_sessions: int,
    in_flight: int,
    quote: dict[str, str] | None,
    now: datetime | None = None,
    activity_limit: int = 8,
) -> DeskSnapshot:
    moment = now or datetime.now(timezone.utc)
    window_start = moment - HEALTH_WINDOW
    bucket_seconds = HEALTH_WINDOW.total_seconds() / HEALTH_BUCKETS

    tool_series = [0] * HEALTH_BUCKETS
    run_series = [0] * HEALTH_BUCKETS
    error_series = [0] * HEALTH_BUCKETS
    tool_calls = 0
    windowed_runs = 0
    errors = 0
    durations: list[int] = []
    day_start = moment - timedelta(hours=24)
    sessions_today: set[str] = set()

    activity: list[ActivityEntry] = []
    for record in runs:
        started = _parse(record.started_at)
        completed = _parse(record.completed_at)
        duration_ms = (
            int((completed - started).total_seconds() * 1000)
            if started and completed and completed >= started
            else None
        )
        errored = _errored(record)

        if len(activity) < activity_limit:
            activity.append(
                ActivityEntry(
                    run_id=record.run_id,
                    session_key=record.session_key,
                    session_title=session_titles.get(record.session_key) or record.session_key,
                    provider=record.provider,
                    model=record.model,
                    status=record.status,
                    summary=_summary(record),
                    tool_count=len(record.tool_steps),
                    started_at=record.started_at,
                    completed_at=record.completed_at,
                    duration_ms=duration_ms,
                    errored=errored,
                )
            )

        if started is not None and started >= day_start:
            sessions_today.add(record.session_key)

        if started is None or started < window_start:
            continue
        index = min(HEALTH_BUCKETS - 1, int((started - window_start).total_seconds() // bucket_seconds))
        windowed_runs += 1
        run_series[index] += 1
        tool_calls += len(record.tool_steps)
        tool_series[index] += len(record.tool_steps)
        if errored:
            errors += 1
            error_series[index] += 1
        if duration_ms is not None:
            durations.append(duration_ms)

    health = DeskHealth(
        active_sessions=len(sessions_today),
        total_sessions=total_sessions,
        in_flight=in_flight,
        tool_calls=tool_calls,
        error_rate=(errors / windowed_runs) if windowed_runs else 0.0,
        avg_latency_ms=(round(sum(durations) / len(durations)) if durations else None),
        runs=windowed_runs,
        tool_call_series=tool_series,
        run_series=run_series,
        error_series=error_series,
    )

    return DeskSnapshot(
        generated_at=moment.isoformat(),
        activity=activity,
        health=health,
        quote=quote,
    )


__all__ = ["ActivityEntry", "DeskHealth", "DeskSnapshot", "build_desk_snapshot", "asdict"]
