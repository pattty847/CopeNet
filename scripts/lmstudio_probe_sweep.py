#!/usr/bin/env python3
"""Run the focused live probe subset across LM Studio chat models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib import request


REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_PROBE_SCRIPT = REPO_ROOT / "scripts" / "live_probe_matrix.py"
DEFAULT_BASE_URL = "http://127.0.0.1:1234"
DEFAULT_PROBES = "repo_inspect_summary,patch_plan_probe,same_session_seed_probe,same_session_repeat_probe"


def _parse_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def fetch_lmstudio_models(base_url: str) -> list[dict]:
    """Return LM Studio native model catalog rows."""
    url = f"{base_url.rstrip('/')}/api/v1/models"
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    rows = data.get("models") if isinstance(data, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)]


def select_chat_models(
    rows: list[dict],
    *,
    requested_models: list[str],
    limit: int | None,
) -> list[str]:
    """Select LM Studio LLM model keys, preserving requested order when provided."""
    available = [
        str(row.get("key") or row.get("id") or "").strip()
        for row in rows
        if str(row.get("type") or "").strip().lower() == "llm" and str(row.get("key") or row.get("id") or "").strip()
    ]
    if requested_models:
        available_set = set(available)
        selected = [model for model in requested_models if model in available_set]
    else:
        selected = available
    return selected[:limit] if limit is not None and limit >= 0 else selected


def build_probe_command(
    *,
    model: str,
    probes: str,
    output_dir: Path,
    repeats: int,
    expect_trace: bool,
) -> list[str]:
    """Build one live probe command for an LM Studio model."""
    command = [
        sys.executable,
        str(LIVE_PROBE_SCRIPT),
        "--providers",
        "lm-studio",
        "--lm-model",
        model,
        "--probes",
        probes,
        "--output-dir",
        str(output_dir),
        "--repeats",
        str(repeats),
    ]
    if expect_trace:
        command.append("--expect-trace")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run focused live probes across LM Studio chat models.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--models", default=None, help="Comma-separated LM Studio model ids. Defaults to all LLM models.")
    parser.add_argument("--limit", type=int, default=None, help="Limit selected models after filtering.")
    parser.add_argument("--probes", default=DEFAULT_PROBES)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "tmp" / "probe_runs"))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--expect-trace", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    rows = fetch_lmstudio_models(args.base_url)
    models = select_chat_models(rows, requested_models=_parse_csv(args.models), limit=args.limit)
    if not models:
        print("No LM Studio LLM models selected.", file=sys.stderr)
        return 2

    for model in models:
        command = build_probe_command(
            model=model,
            probes=args.probes,
            output_dir=Path(args.output_dir),
            repeats=max(args.repeats, 1),
            expect_trace=bool(args.expect_trace),
        )
        print("\n$", " ".join(command), flush=True)
        if args.dry_run:
            continue
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
