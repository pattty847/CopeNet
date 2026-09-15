"""Benchmark report: repeats aggregate to pass rate and median/min/max per task."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.coding.report import aggregate_rows, render_suite_report  # noqa: E402


def _result(task_id: str, repeat: int, *, passed: bool, tool_calls: int, peak: int, billed: int, dumps: int) -> dict:
    return {
        "id": task_id,
        "repeat": repeat,
        "passed": passed,
        "title": "t",
        "capability": "c",
        "sessionKey": f"bench-{task_id}-r{repeat}",
        "turns": [{"turn": 1, "runId": "x", "status": "ok", "elapsedSec": 10.0}],
        "checks": [{"name": "the check", "ok": passed, "detail": ""}],
        "analyses": [
            {
                "toolCalls": tool_calls,
                "modelCalls": tool_calls - 2,
                "tokens": {"providerReported": {"peakInputTokens": peak, "inputTokensTotal": billed}},
                "reads": {"redundantReadCount": 0, "searchDumps": [{}] * dumps},
                "outcome": {"elapsedSec": 10.0},
                "header": {},
                "verification": {},
            }
        ],
    }


def test_aggregate_rows_report_pass_rate_and_spread_per_task() -> None:
    results = [
        _result("broad", 1, passed=True, tool_calls=41, peak=81_391, billed=2_008_098, dumps=2),
        _result("broad", 2, passed=False, tool_calls=47, peak=77_854, billed=2_310_516, dumps=4),
        _result("broad", 3, passed=True, tool_calls=40, peak=64_354, billed=1_587_047, dumps=2),
        _result("fix", 1, passed=True, tool_calls=10, peak=22_460, billed=165_629, dumps=1),
    ]
    rows = {row["id"]: row for row in aggregate_rows(results)}
    assert rows["broad"]["passes"] == 2 and rows["broad"]["runs"] == 3
    assert rows["broad"]["toolCalls"] == {"median": 41, "min": 40, "max": 47, "n": 3}
    assert rows["broad"]["searchDumps"] == {"median": 2, "min": 2, "max": 4, "n": 3}
    assert rows["broad"]["billedInput"]["median"] == 2_008_098
    assert rows["broad"]["failedChecks"] == {"the check": 1}
    assert rows["fix"]["runs"] == 1 and rows["fix"]["peakInput"]["median"] == 22_460


def test_report_leads_with_the_spread_table_when_repeated() -> None:
    results = [_result("broad", k, passed=True, tool_calls=40 + k, peak=60_000, billed=1_000_000, dumps=2) for k in (1, 2, 3)]
    summary = {"provider": "openai-codex", "model": "gpt-5.5", "ranAt": "now", "score": "3/3", "repeat": 3, "tasks": [], "aggregate": aggregate_rows(results)}
    report = render_suite_report(summary, results)
    assert "over 3 runs per task" in report
    assert "Median (min–max) across runs" in report
    assert "| broad | 3/3 | 42 (41–43) |" in report
    assert "## broad — run 2 — t" in report
    single = render_suite_report({**summary, "repeat": 1, "aggregate": []}, results[:1])
    assert "Median (min–max)" not in single
