"""Render the benchmark suite report as Markdown."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any

from benchmarks.coding.trace_analysis import render_markdown


def _turn_metric(result: dict[str, Any], pick) -> int | float | None:
    values = [pick(a) for a in result["analyses"] if a and pick(a) is not None]
    return sum(values) if values else None


def _peak(result: dict[str, Any]) -> int | None:
    values = [((a.get("tokens") or {}).get("providerReported") or {}).get("peakInputTokens") for a in result["analyses"] if a]
    values = [v for v in values if v is not None]
    return max(values) if values else None


def _stat(values: list) -> dict[str, Any]:
    clean = [v for v in values if v is not None]
    if not clean:
        return {"median": None, "min": None, "max": None, "n": 0}
    med = median(clean)
    return {"median": int(med) if float(med).is_integer() else round(med, 1), "min": min(clean), "max": max(clean), "n": len(clean)}


def aggregate_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per task across its repeats: pass rate and median/min/max of the numbers that move.

    Single runs of the same task swing ±20% on billed tokens and 2→4→2 on search
    dumps; a decision needs the spread, not the last digit.
    """
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []
    for result in results:
        if result["id"] not in by_task:
            order.append(result["id"])
        by_task[result["id"]].append(result)
    rows = []
    for task_id in order:
        runs = by_task[task_id]
        failed = Counter(check["name"] for r in runs for check in r["checks"] if not check["ok"])
        rows.append(
            {
                "id": task_id,
                "runs": len(runs),
                "passes": sum(1 for r in runs if r["passed"]),
                "toolCalls": _stat([_turn_metric(r, lambda a: a.get("toolCalls")) for r in runs]),
                "modelCalls": _stat([_turn_metric(r, lambda a: a.get("modelCalls")) for r in runs]),
                "peakInput": _stat([_peak(r) for r in runs]),
                "billedInput": _stat([_turn_metric(r, lambda a: ((a.get("tokens") or {}).get("providerReported") or {}).get("inputTokensTotal")) for r in runs]),
                "redundantReads": _stat([_turn_metric(r, lambda a: (a.get("reads") or {}).get("redundantReadCount")) for r in runs]),
                "searchDumps": _stat([_turn_metric(r, lambda a: len((a.get("reads") or {}).get("searchDumps") or [])) for r in runs]),
                "elapsedSec": _stat([_turn_metric(r, lambda a: (a.get("outcome") or {}).get("elapsedSec")) for r in runs]),
                "failedChecks": dict(failed),
            }
        )
    return rows


def _spread_cell(stat: dict[str, Any]) -> str:
    if stat.get("median") is None:
        return "—"
    return f"{stat['median']} ({stat['min']}–{stat['max']})"


def summary_row(result: dict[str, Any]) -> dict[str, Any]:
    """The per-task row of summary.json, built the same way after a live run and after a regrade."""
    analyses = result["analyses"]
    return {
        "id": result["id"],
        "repeat": result.get("repeat", 1),
        "passed": result["passed"],
        "sessionKey": result["sessionKey"],
        "turns": result["turns"],
        "failedChecks": [c["name"] for c in result["checks"] if not c["ok"]],
        "toolCalls": [a.get("toolCalls") for a in analyses],
        "modelCalls": [a.get("modelCalls") for a in analyses],
        "peakInput": [(a.get("tokens") or {}).get("providerReported", {}).get("peakInputTokens") for a in analyses],
        "totalInput": [(a.get("tokens") or {}).get("providerReported", {}).get("inputTokensTotal") for a in analyses],
        "redundantReads": [(a.get("reads") or {}).get("redundantReadCount") for a in analyses],
        "searchDumps": [len((a.get("reads") or {}).get("searchDumps") or []) for a in analyses],
        "receiptedOutputs": [((a.get("header") or {}).get("replayReceipts") or {}).get("receiptedOutputs") for a in analyses],
        "verifiedAfterLastEdit": [(a.get("verification") or {}).get("afterLastMutation") for a in analyses],
    }


def render_suite_report(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        f"# Coding-agent benchmark — {summary['provider']} / {summary['model'] or 'default'}",
        "",
        f"Ran {summary['ranAt']}. Score **{summary['score']}**" + (f" over {summary['repeat']} runs per task." if summary.get("repeat", 1) > 1 else "."),
        "",
    ]
    aggregate = summary.get("aggregate") or []
    if summary.get("repeat", 1) > 1 and aggregate:
        lines += [
            "Median (min–max) across runs:",
            "",
            "| task | pass | tool calls | model calls | peak input | billed input | redundant reads | search dumps | seconds | failed checks (runs) |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in aggregate:
            failed = ", ".join(f"{name} ({count})" for name, count in row["failedChecks"].items()) or "—"
            lines.append(
                f"| {row['id']} | {row['passes']}/{row['runs']} | {_spread_cell(row['toolCalls'])} | {_spread_cell(row['modelCalls'])} | {_spread_cell(row['peakInput'])} | "
                f"{_spread_cell(row['billedInput'])} | {_spread_cell(row['redundantReads'])} | {_spread_cell(row['searchDumps'])} | {_spread_cell(row['elapsedSec'])} | {failed} |"
            )
        lines += ["", "Every run:", ""]
    lines += [
        "| task | run | pass | turns | tool calls | model calls | peak input | total input | redundant reads | search dumps | receipted outputs | verified after last edit | failed checks |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in summary["tasks"]:
        lines.append(
            f"| {row['id']} | {row.get('repeat', 1)} | {'✓' if row['passed'] else '✗'} | {len(row['turns'])} | {row['toolCalls']} | {row['modelCalls']} | "
            f"{row['peakInput']} | {row['totalInput']} | {row['redundantReads']} | {row.get('searchDumps')} | {row.get('receiptedOutputs')} | {row['verifiedAfterLastEdit']} | {', '.join(row['failedChecks']) or '—'} |"
        )
    for result in results:
        run_label = f" — run {result['repeat']}" if summary.get("repeat", 1) > 1 else ""
        lines += ["", f"## {result['id']}{run_label} — {result['title']}", "", f"Capability: {result['capability']}", "", f"Session `{result['sessionKey']}`", ""]
        for turn in result["turns"]:
            lines.append(f"- turn {turn['turn']}: run `{turn['runId']}` {turn['status']} in {turn['elapsedSec']}s" + (f" — {turn['error']}" if turn.get("error") else ""))
        lines.append("")
        for check in result["checks"]:
            lines.append(f"- {'✓' if check['ok'] else '✗'} **{check['name']}** — {check['detail']}")
        for index, analysis in enumerate(result["analyses"], start=1):
            if not analysis or "error" in analysis and len(analysis) == 1:
                lines += ["", f"### turn {index} trace", "", f"(no analysis: {analysis.get('error') if analysis else 'no trace'})"]
                continue
            lines += ["", f"### turn {index} trace", "", render_markdown(analysis)]
    return "\n".join(lines) + "\n"
