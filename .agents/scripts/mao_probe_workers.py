#!/usr/bin/env python3
"""Probe worker CLI binaries for headless availability.

For each registered worker, the probe:
  1. Resolves the binary on PATH via shutil.which.
  2. Runs a minimal headless prompt with a tight timeout.
  3. Reports availability + responsiveness as a structured result.

The probe validates the round-trip (binary + auth + network), not response
content. A non-empty stdout from a successful exit is the signal.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


PROBE_PROMPT = "Reply with the single word: pong"
DEFAULT_TIMEOUT_SECONDS = 60
OUTPUT_PREVIEW_LIMIT = 200


@dataclass
class ProbeSpec:
    agent: str
    command: tuple[str, ...]
    timeout_seconds: int


WORKER_PROBES: Mapping[str, ProbeSpec] = {
    "claude": ProbeSpec(
        agent="claude",
        command=("claude", "-p", "--output-format", "text", PROBE_PROMPT),
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    ),
    "gemini": ProbeSpec(
        agent="gemini",
        command=("gemini", "-p", PROBE_PROMPT, "-o", "text"),
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    ),
}


@dataclass
class ProbeResult:
    agent: str
    available: bool
    responded: bool
    binary_path: str | None
    duration_ms: int | None
    error: str | None
    output_preview: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _truncate(text: str, limit: int = OUTPUT_PREVIEW_LIMIT) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def probe_worker(spec: ProbeSpec) -> ProbeResult:
    binary = shutil.which(spec.command[0])
    if binary is None:
        return ProbeResult(
            agent=spec.agent,
            available=False,
            responded=False,
            binary_path=None,
            duration_ms=None,
            error=f"binary not on PATH: {spec.command[0]}",
            output_preview=None,
        )

    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(spec.command),
            check=False,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(
            agent=spec.agent,
            available=True,
            responded=False,
            binary_path=binary,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=f"timed out after {spec.timeout_seconds}s",
            output_preview=None,
        )
    except OSError as exc:
        return ProbeResult(
            agent=spec.agent,
            available=True,
            responded=False,
            binary_path=binary,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=f"failed to invoke binary: {exc}",
            output_preview=None,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        return ProbeResult(
            agent=spec.agent,
            available=True,
            responded=False,
            binary_path=binary,
            duration_ms=duration_ms,
            error=f"exit {completed.returncode}: {_truncate(stderr) or 'no stderr'}",
            output_preview=_truncate(stdout) if stdout else None,
        )

    if not stdout:
        return ProbeResult(
            agent=spec.agent,
            available=True,
            responded=False,
            binary_path=binary,
            duration_ms=duration_ms,
            error="empty stdout",
            output_preview=None,
        )

    return ProbeResult(
        agent=spec.agent,
        available=True,
        responded=True,
        binary_path=binary,
        duration_ms=duration_ms,
        error=None,
        output_preview=_truncate(stdout),
    )


def probe_workers(agents: Sequence[str] | None = None) -> list[ProbeResult]:
    selected = list(agents) if agents else list(WORKER_PROBES.keys())
    results: list[ProbeResult] = []
    for agent in selected:
        spec = WORKER_PROBES.get(agent)
        if spec is None:
            results.append(
                ProbeResult(
                    agent=agent,
                    available=False,
                    responded=False,
                    binary_path=None,
                    duration_ms=None,
                    error=f"unknown agent: {agent}",
                    output_preview=None,
                )
            )
            continue
        results.append(probe_worker(spec))
    return results


def _format_human(results: Sequence[ProbeResult]) -> str:
    lines = []
    for result in results:
        status = "OK" if result.responded else ("MISSING" if not result.available else "FAIL")
        detail_parts = []
        if result.binary_path:
            detail_parts.append(result.binary_path)
        if result.duration_ms is not None:
            detail_parts.append(f"{result.duration_ms}ms")
        if result.error:
            detail_parts.append(f"error: {result.error}")
        if result.output_preview:
            detail_parts.append(f'reply: "{result.output_preview}"')
        detail = " | ".join(detail_parts) if detail_parts else "—"
        lines.append(f"[{status:>7}] {result.agent:<8} {detail}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe worker CLI binaries.")
    parser.add_argument(
        "--agent",
        action="append",
        choices=sorted(WORKER_PROBES.keys()),
        help="Probe a specific agent (repeatable). Defaults to all.",
    )
    parser.add_argument(
        "--require",
        action="append",
        choices=sorted(WORKER_PROBES.keys()),
        help="Exit non-zero if any required agent is unavailable or unresponsive.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    results = probe_workers(args.agent)

    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        print(_format_human(results))

    if args.require:
        required = set(args.require)
        for result in results:
            if result.agent in required and not result.responded:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
