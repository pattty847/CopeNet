"""The Usage rollup groups durable run records without inventing numbers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from copenet.core.observability.usage_rollup import build_usage_rollup
from copenet.core.runtime.runs import RunRecord

NOW = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)


def make_run(
    *,
    run_id: str = "run-1",
    session_key: str = "session-a",
    provider: str = "openai-codex",
    model: str | None = "gpt-5.5",
    status: str = "ok",
    started_at: str = "2026-09-15T09:30:00+00:00",
    completed_at: str | None = "2026-09-15T09:30:12+00:00",
    token_usage: dict[str, Any] | None = None,
    tool_steps: list[dict[str, Any]] | None = None,
    coding_metrics: dict[str, Any] | None = None,
    error: str | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        session_key=session_key,
        provider=provider,
        model=model,
        status=status,
        user_message="probe",
        tool_execution_mode="responses",
        will_attempt_tool_loop=True,
        started_at=started_at,
        completed_at=completed_at,
        tool_steps=tool_steps or [],
        token_usage=token_usage,
        coding_metrics=coding_metrics,
        error=error,
    )


def usage(**overrides: Any) -> dict[str, Any]:
    base = {
        "source": "provider",
        "modelCalls": 2,
        "inputTokens": 10_000,
        "peakInputTokens": 6_000,
        "cachedInputTokens": 4_000,
        "outputTokens": 1_000,
        "reasoningTokens": 400,
        "steps": [],
    }
    base.update(overrides)
    return base


def rollup(records: list[RunRecord], **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("days", 7)
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("tz", timezone.utc)
    return build_usage_rollup(records, **kwargs)


def test_totals_sum_provider_reported_usage_and_derive_a_cache_hit_rate():
    result = rollup([make_run(token_usage=usage()), make_run(run_id="run-2", token_usage=usage())])

    totals = result["totals"]
    assert totals["runs"] == 2
    assert totals["modelCalls"] == 4
    assert totals["inputTokens"] == 20_000
    assert totals["cachedInputTokens"] == 8_000
    assert totals["freshInputTokens"] == 12_000
    assert totals["outputTokens"] == 2_000
    assert totals["totalTokens"] == 22_000
    assert totals["cacheHitRate"] == 0.4
    assert totals["peakInputTokens"] == 6_000, "peak is the largest single call, never a sum"
    assert totals["avgTokensPerRun"] == 11_000


def test_a_run_whose_provider_reported_nothing_counts_as_missing_coverage_not_zero_cost():
    result = rollup([make_run(token_usage=usage()), make_run(run_id="run-2", token_usage=None)])

    assert result["usageCoverage"] == {
        "runs": 2,
        "runsWithUsage": 1,
        "runsWithoutUsage": 1,
        "ratio": 0.5,
    }
    # The average divides by the runs that actually reported, not by every run.
    assert result["totals"]["avgTokensPerRun"] == 11_000


def test_a_rate_with_no_denominator_is_none_rather_than_zero():
    result = rollup([make_run(token_usage=None)])

    assert result["totals"]["cacheHitRate"] is None
    assert result["totals"]["toolFailureRate"] is None
    assert result["coding"]["verifiedAfterEditRate"] is None
    assert result["totals"]["errorRate"] == 0.0, "an error rate over real runs is a real zero"


def test_error_runs_count_a_failed_status_or_a_recorded_error():
    result = rollup(
        [
            make_run(),
            make_run(run_id="run-2", status="error"),
            make_run(run_id="run-3", status="ok", error="provider stream died"),
        ]
    )

    assert result["totals"]["errorRuns"] == 2
    assert result["totals"]["errorRate"] == pytest.approx(0.6667, abs=1e-4)


def test_tool_rows_separate_failures_from_policy_blocked_calls():
    steps = [
        {"toolId": "files.read", "ok": True},
        {"toolId": "files.read", "ok": False, "error": "no such file"},
        {"toolId": "shell.exec", "ok": False, "policyDecision": "write_blocked"},
        {"toolId": "files.rg", "ok": True},
    ]
    result = rollup([make_run(tool_steps=steps)])

    by_id = {row["toolId"]: row for row in result["tools"]}
    assert by_id["files.read"]["calls"] == 2
    assert by_id["files.read"]["failures"] == 1
    assert by_id["files.read"]["blocked"] == 0
    assert by_id["shell.exec"]["blocked"] == 1
    assert result["totals"]["toolCalls"] == 4
    assert result["totals"]["toolFailures"] == 2
    assert result["totals"]["toolBlocked"] == 1
    assert result["totals"]["distinctTools"] == 3


def test_top_lists_rank_models_and_providers_by_tokens():
    result = rollup(
        [
            make_run(model="gpt-5.5", token_usage=usage(inputTokens=1_000, outputTokens=100)),
            make_run(run_id="r2", model="gpt-5.5", token_usage=usage(inputTokens=1_000, outputTokens=100)),
            make_run(
                run_id="r3",
                provider="claude-cli",
                model="opus-5",
                token_usage=usage(inputTokens=9_000, outputTokens=500),
            ),
        ]
    )

    assert [row["model"] for row in result["models"]] == ["opus-5", "gpt-5.5"]
    assert [row["provider"] for row in result["providers"]] == ["claude-cli", "openai-codex"]
    assert result["models"][0]["runs"] == 1
    assert result["models"][1]["runs"] == 2


def test_every_day_in_the_window_is_present_even_when_nothing_ran():
    result = rollup([make_run(started_at="2026-09-14T09:00:00+00:00", token_usage=usage())], days=5)

    assert [row["date"] for row in result["daily"]] == [
        "2026-09-11",
        "2026-09-12",
        "2026-09-13",
        "2026-09-14",
        "2026-09-15",
    ]
    assert result["daily"][3]["totalTokens"] == 11_000
    assert result["daily"][4]["runs"] == 0
    assert result["range"] == {
        "days": 5,
        "start": "2026-09-11",
        "end": "2026-09-15",
        "generatedAt": "2026-09-15T18:00:00+00:00",
        "timezone": "UTC",
    }


def test_runs_outside_the_window_are_dropped():
    result = rollup(
        [
            make_run(started_at="2026-09-15T09:00:00+00:00", token_usage=usage()),
            make_run(run_id="old", started_at="2026-08-01T09:00:00+00:00", token_usage=usage()),
        ],
        days=7,
    )

    assert result["totals"]["runs"] == 1


def test_weekday_and_hour_buckets_cover_the_full_cycle():
    # 2026-09-15 is a Tuesday (weekday index 1).
    result = rollup([make_run(started_at="2026-09-15T14:05:00+00:00", token_usage=usage())])

    assert [row["weekday"] for row in result["weekday"]] == list(range(7))
    assert [row["hour"] for row in result["hourly"]] == list(range(24))
    assert result["weekday"][1]["runs"] == 1
    assert result["hourly"][14]["runs"] == 1
    assert sum(row["runs"] for row in result["hourly"]) == 1


def test_local_timezone_places_a_run_in_its_own_local_day():
    from datetime import timedelta

    ahead = timezone(timedelta(hours=10))
    # 22:30 UTC on the 14th is 08:30 on the 15th in a UTC+10 timezone.
    result = build_usage_rollup(
        [make_run(started_at="2026-09-14T22:30:00+00:00", token_usage=usage())],
        days=3,
        now=NOW,
        tz=ahead,
    )

    by_date = {row["date"]: row for row in result["daily"]}
    assert by_date["2026-09-15"]["runs"] == 1
    assert by_date["2026-09-14"]["runs"] == 0
    assert result["hourly"][8]["runs"] == 1


def test_bench_sessions_are_excluded_by_default_and_counted_when_they_are():
    records = [
        make_run(token_usage=usage()),
        make_run(run_id="b1", session_key="bench-coding-001", token_usage=usage()),
    ]

    excluded = rollup(records)
    assert excluded["totals"]["runs"] == 1
    assert excluded["benchRunsExcluded"] == 1
    assert excluded["includeBench"] is False

    included = rollup(records, include_bench=True)
    assert included["totals"]["runs"] == 2
    assert included["benchRunsExcluded"] == 0
    assert included["includeBench"] is True


def test_coding_habits_roll_up_and_the_verified_rate_ignores_runs_with_no_edit():
    def metrics(edits: int, after_last_edit: bool | None, redundant: int = 0) -> dict[str, Any]:
        return {
            "toolCalls": 6,
            "reads": {"distinctFiles": 3, "redundant": redundant, "afterOwnEdit": 1},
            "searches": {"count": 2, "overCap": 1, "cap": 200},
            "edits": {"count": edits, "files": edits, "staleErrors": 0},
            "exactRepeats": 1,
            "failures": {"count": 1, "blocked": 0, "blindRetries": 2},
            "verification": {"commands": 1, "tests": 1, "afterLastEdit": after_last_edit},
            "recovery": {"failedVerificationsAfterEdit": 1, "editsAfterFailedVerification": 1},
        }

    result = rollup(
        [
            make_run(coding_metrics=metrics(2, True, redundant=3)),
            make_run(run_id="r2", coding_metrics=metrics(1, False)),
            make_run(run_id="r3", coding_metrics=metrics(0, None)),
            make_run(run_id="r4", coding_metrics=None),
        ]
    )

    coding = result["coding"]
    assert coding["runsWithMetrics"] == 3
    assert coding["redundantReads"] == 3
    assert coding["blindRetries"] == 6
    assert coding["searchDumps"] == 3
    assert coding["runsWithEdits"] == 2, "the chat-only run has no last edit to verify after"
    assert coding["runsVerifiedAfterLastEdit"] == 1
    assert coding["verifiedAfterEditRate"] == 0.5
    assert [row["date"] for row in coding["daily"]] == [row["date"] for row in result["daily"]]


def test_an_unparseable_started_at_is_skipped_and_reported():
    result = rollup([make_run(started_at="not-a-timestamp"), make_run(run_id="r2", token_usage=usage())])

    assert result["undatedRunsSkipped"] == 1
    assert result["totals"]["runs"] == 1


def test_busiest_day_is_none_when_no_tokens_were_reported():
    assert rollup([make_run(token_usage=None)])["totals"]["busiestDay"] is None
    assert rollup([make_run(token_usage=usage())])["totals"]["busiestDay"] == "2026-09-15"


def test_an_empty_window_still_returns_a_full_shape():
    result = rollup([], days=3)

    assert result["totals"]["runs"] == 0
    assert result["models"] == []
    assert result["tools"] == []
    assert len(result["daily"]) == 3
    assert len(result["weekday"]) == 7
    assert len(result["hourly"]) == 24
    assert result["totals"]["avgTokensPerRun"] is None
    assert result["totals"]["avgRunSeconds"] is None


def test_run_duration_uses_completed_at_and_skips_an_unfinished_run():
    result = rollup(
        [
            make_run(started_at="2026-09-15T09:00:00+00:00", completed_at="2026-09-15T09:00:10+00:00"),
            make_run(run_id="r2", started_at="2026-09-15T09:00:00+00:00", completed_at=None),
        ]
    )

    assert result["totals"]["avgRunSeconds"] == 10.0
