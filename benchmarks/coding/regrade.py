"""Re-analyze saved traces and re-grade kept workspaces for one benchmark run.

    uv run python -m benchmarks.coding.regrade tmp/coding_bench/<run-dir>

Useful after the analyzer or a grader changes: nothing is re-run against a
model. Needs the workspaces kept (`--keep`) for the workspace checks; without
them only the trace-derived fields are refreshed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from benchmarks.coding import trace_analysis  # noqa: E402
from benchmarks.coding.report import render_suite_report  # noqa: E402
from benchmarks.coding.tasks import TASKS_BY_ID, GradeContext  # noqa: E402
from dataclasses import asdict  # noqa: E402


def regrade(run_dir: Path) -> int:
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"provider": "?", "model": None, "ranAt": run_dir.name, "tasks": []}
    results = []
    for result_path in sorted(run_dir.glob("*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        task = TASKS_BY_ID[result["id"]]
        task_dir = result_path.parent
        analyses = []
        final_texts = []
        for turn in result["turns"]:
            index = turn["turn"]
            trace_path = task_dir / f"turn{index}.trace.jsonl"
            analyses.append(trace_analysis.analyze(trace_analysis.load_rows(trace_path)) if trace_path.exists() else {})
            final_path = task_dir / f"turn{index}.final.md"
            final_texts.append(final_path.read_text(encoding="utf-8") if final_path.exists() else "")
            (task_dir / f"turn{index}.analysis.json").write_text(json.dumps(analyses[-1], indent=1, default=str), encoding="utf-8")
        workdir = Path(result["workspace"])
        if workdir.exists():
            checks = task.grade(workdir, GradeContext(final_texts=final_texts, analyses=analyses))
            result["checks"] = [asdict(check) for check in checks]
        result["analyses"] = analyses
        result["passed"] = all(check["ok"] for check in result["checks"]) and all(turn["status"] == "ok" for turn in result["turns"])
        result_path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        results.append(result)
    summary["score"] = f"{sum(1 for r in results if r['passed'])}/{len(results)}"
    summary["tasks"] = [
        {
            "id": r["id"],
            "passed": r["passed"],
            "sessionKey": r["sessionKey"],
            "turns": r["turns"],
            "failedChecks": [c["name"] for c in r["checks"] if not c["ok"]],
            "toolCalls": [a.get("toolCalls") for a in r["analyses"]],
            "modelCalls": [a.get("modelCalls") for a in r["analyses"]],
            "peakInput": [(a.get("tokens") or {}).get("providerReported", {}).get("peakInputTokens") for a in r["analyses"]],
            "totalInput": [(a.get("tokens") or {}).get("providerReported", {}).get("inputTokensTotal") for a in r["analyses"]],
            "redundantReads": [(a.get("reads") or {}).get("redundantReadCount") for a in r["analyses"]],
            "verifiedAfterLastEdit": [(a.get("verification") or {}).get("afterLastMutation") for a in r["analyses"]],
        }
        for r in results
    ]
    summary_path.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(render_suite_report(summary, results), encoding="utf-8")
    print(f"regraded {len(results)} task(s): score {summary['score']} → {run_dir / 'REPORT.md'}")
    for row in summary["tasks"]:
        print(f"  {'✓' if row['passed'] else '✗'} {row['id']:<26} failed={row['failedChecks']}")
    return 0


if __name__ == "__main__":
    sys.exit(regrade(Path(sys.argv[1])))
