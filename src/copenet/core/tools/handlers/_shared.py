"""Shared helpers for builtin readonly tool handlers."""

from __future__ import annotations

import asyncio
import glob
import os
from pathlib import Path
import subprocess

from copenet.core.tools.contracts import ToolExecutionContext


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
        stdout_text = (proc.stdout or "")[:output_limit]
        stderr_text = (proc.stderr or "")[:output_limit]
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
