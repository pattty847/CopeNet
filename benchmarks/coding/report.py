"""Render the benchmark suite report as Markdown."""

from __future__ import annotations

from typing import Any

from benchmarks.coding.trace_analysis import render_markdown


def render_suite_report(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        f"# Coding-agent benchmark — {summary['provider']} / {summary['model'] or 'default'}",
        "",
        f"Ran {summary['ranAt']}. Score **{summary['score']}**.",
        "",
        "| task | pass | turns | tool calls | model calls | peak input | total input | redundant reads | search dumps | receipted outputs | verified after last edit | failed checks |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in summary["tasks"]:
        lines.append(
            f"| {row['id']} | {'✓' if row['passed'] else '✗'} | {len(row['turns'])} | {row['toolCalls']} | {row['modelCalls']} | "
            f"{row['peakInput']} | {row['totalInput']} | {row['redundantReads']} | {row.get('searchDumps')} | {row.get('receiptedOutputs')} | {row['verifiedAfterLastEdit']} | {', '.join(row['failedChecks']) or '—'} |"
        )
    for result in results:
        lines += ["", f"## {result['id']} — {result['title']}", "", f"Capability: {result['capability']}", "", f"Session `{result['sessionKey']}`", ""]
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
