"""Shared helpers for builtin readonly tool handlers."""

from __future__ import annotations

import asyncio
import glob
import os
from pathlib import Path
import subprocess

from copenet.core.tools.contracts import ToolBlockedError, ToolExecutionContext


def _clip_with_marker(text: str, limit: int, stream: str) -> str:
    """Clip a stream to `limit` chars, appending a visible marker when truncated.

    Silent truncation makes a model treat a clipped `git log`/test run as
    complete. The marker rides the existing stdout/stderr fields to every loop
    path (native, Responses, prompted), so the model knows there is more.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[{stream} truncated at {limit} chars; {len(text)} total]"


async def run_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_sec: float,
    output_limit: int,
) -> tuple[int, str, str]:
    def invoke() -> tuple[int, str, str]:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        stdout_text = _clip_with_marker(proc.stdout or "", output_limit, "stdout")
        stderr_text = _clip_with_marker(proc.stderr or "", output_limit, "stderr")
        return proc.returncode, stdout_text, stderr_text

    try:
        return await asyncio.to_thread(invoke)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout_sec}s") from exc


async def run_shell_command(
    command: str,
    *,
    cwd: Path,
    timeout_sec: float,
    output_limit: int,
) -> tuple[int, str, str]:
    def invoke() -> tuple[int, str, str]:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            shell=True,
            executable="/bin/bash",
        )
        stdout_text = _clip_with_marker(proc.stdout or "", output_limit, "stdout")
        stderr_text = _clip_with_marker(proc.stderr or "", output_limit, "stderr")
        return proc.returncode, stdout_text, stderr_text

    try:
        return await asyncio.to_thread(invoke)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout_sec}s") from exc


def read_guidance(context: ToolExecutionContext) -> str:
    guidance_path = context.workdir / "AGENTS.md"
    if not guidance_path.is_file():
        return ""
    try:
        return guidance_path.read_text(encoding="utf-8")[: context.policy.guidance_char_limit]
    except OSError:
        return ""


def resolve_relative_path(raw_path: str | None, context: ToolExecutionContext) -> Path:
    path_str = (raw_path or ".").strip() or "."
    candidate = Path(path_str).expanduser()
    return (context.workdir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def scope_for_path(path: Path, context: ToolExecutionContext) -> str:
    try:
        path.resolve().relative_to(context.session_workspace_root.resolve())
        return "inside_workspace"
    except ValueError:
        return "outside_workspace"


def policy_decision_for_scope(scope: str) -> str:
    return "read_roam" if scope == "outside_workspace" else "allowed"


def file_access_metadata(path: Path, context: ToolExecutionContext) -> dict[str, str]:
    scope = scope_for_path(path, context)
    return {
        "target": display_path(path, context),
        "workspaceRoot": str(context.session_workspace_root),
        "scope": scope,
        "accessAction": "read",
        "policyDecision": policy_decision_for_scope(scope),
        "policySummary": "Read roamed outside the home workspace." if scope == "outside_workspace" else "Read stayed inside the home workspace.",
    }


def ensure_write_allowed(path: Path, context: ToolExecutionContext) -> None:
    scope = scope_for_path(path, context)
    if scope == "outside_workspace":
        target = display_path(path, context)
        raise ToolBlockedError(
            "writes outside the home workspace are blocked in v1",
            target=target,
            workspace_root=str(context.session_workspace_root),
            scope=scope,
            access_action="write",
            policy_decision="write_blocked",
            policy_summary="Write blocked outside the home workspace.",
        )


def display_path(path: Path, context: ToolExecutionContext) -> str:
    try:
        return str(path.resolve().relative_to(context.workdir.resolve()))
    except ValueError:
        return str(path.resolve())


def expand_shell_argv(argv: list[str]) -> list[str]:
    """Expand a small safe subset of shell conveniences without enabling a shell."""
    expanded: list[str] = []
    for token in argv:
        normalized = os.path.expandvars(os.path.expanduser(token))
        if glob.has_magic(normalized):
            matches = sorted(glob.glob(normalized))
            if matches:
                expanded.extend(matches)
                continue
        expanded.append(normalized)
    return expanded
