"""Built-in safe read/search tool handlers."""

from __future__ import annotations

import asyncio
import glob
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from .contracts import ContextPack, ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult


class BuiltinReadonlyTools:
    """Safe built-in tool implementations used by the default registry."""

    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                id="context.prepare",
                name="Prepare Context",
                description="Prepare compact repo/session context for answering a question.",
                category="context",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                capabilities=["session", "guidance", "transcript"],
            ),
            ToolDescriptor(
                id="files.list",
                name="List Files",
                description="List files or directories under the current workdir.",
                category="repo-read",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                capabilities=["filesystem", "read"],
            ),
            ToolDescriptor(
                id="files.read",
                name="Read File",
                description="Read a text file inside the current workdir.",
                category="repo-read",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                capabilities=["filesystem", "read"],
            ),
            ToolDescriptor(
                id="files.search",
                name="Search Files",
                description="Search file contents under the current workdir using a regex pattern.",
                category="repo-read",
                input_schema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}},
                capabilities=["filesystem", "search"],
            ),
            ToolDescriptor(
                id="git.status",
                name="Git Status",
                description="Inspect git status in the current workdir.",
                category="repo-read",
                input_schema={"type": "object", "properties": {}},
                capabilities=["git", "read"],
            ),
            ToolDescriptor(
                id="git.diff",
                name="Git Diff",
                description="Inspect git diff in the current workdir.",
                category="repo-read",
                input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
                capabilities=["git", "read"],
            ),
            ToolDescriptor(
                id="shell.exec",
                name="Shell Exec",
                description="Run an allowlisted read-only shell command in the current workdir.",
                category="shell-read",
                input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
                safety_level="guarded",
                capabilities=["shell", "read"],
            ),
        ]

    async def run(self, request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        handlers = {
            "context.prepare": self._context_prepare,
            "files.list": self._files_list,
            "files.read": self._files_read,
            "files.search": self._files_search,
            "git.status": self._git_status,
            "git.diff": self._git_diff,
            "shell.exec": self._shell_exec,
        }
        handler = handlers.get(request.tool_id)
        if handler is None:
            raise ToolBlockedError(f"unknown builtin tool: {request.tool_id}")
        return await handler(request, context)

    async def _run_command(
        self,
        argv: list[str],
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

    def _read_guidance(self, context: ToolExecutionContext) -> str:
        guidance_path = context.workdir / "AGENTS.md"
        if not guidance_path.is_file():
            return ""
        try:
            return guidance_path.read_text(encoding="utf-8")[: context.policy.guidance_char_limit]
        except OSError:
            return ""

    def _resolve_relative_path(self, raw_path: str | None, context: ToolExecutionContext) -> Path:
        path_str = (raw_path or ".").strip() or "."
        candidate = Path(path_str).expanduser()
        if not candidate.is_absolute():
            candidate = (context.workdir / candidate).resolve()
        else:
            candidate = candidate.resolve()
        try:
            candidate.relative_to(context.workdir)
        except ValueError as exc:
            raise ToolBlockedError("path escapes workdir") from exc
        return candidate

    async def _context_prepare(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        session_payload = None
        if context.session_key:
            session = context.session_store.get(context.session_key)
            if session is not None:
                session_payload = {
                    "key": session.session_key,
                    "title": session.title,
                    "provider": session.provider,
                    "model": session.model,
                    "systemPromptId": session.system_prompt_id,
                    "taskPromptId": session.task_prompt_id,
                    "providerSessionId": session.provider_session_id,
                    "inFlightRunId": session.in_flight_run_id,
                }

        transcript = []
        if context.session_key and session_payload is not None:
            transcript = context.transcript_store.read_history(
                session_id=session.session_id,
                limit=context.policy.transcript_limit,
            )

        runtime = {
            "provider": context.provider_name,
            "model": context.model,
            "workdir": str(context.workdir),
        }
        pack = ContextPack(
            session=session_payload,
            transcript=transcript,
            guidance=self._read_guidance(context),
            runtime=runtime,
            workdir=str(context.workdir),
        )
        summary = "Prepared session and repo context."
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=summary,
            output=pack.to_public_dict(),
        )

    async def _files_list(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        root = self._resolve_relative_path(str(request.arguments.get("path") or "."), context)
        if not root.exists():
            raise RuntimeError(f"path not found: {root}")
        rows = []
        for file_path in sorted(root.iterdir())[: context.policy.list_result_limit]:
            rows.append(
                {
                    "path": str(file_path.relative_to(context.workdir)),
                    "name": file_path.name,
                    "isDir": file_path.is_dir(),
                }
            )
        summary = f"Listed {len(rows)} entries under {root.relative_to(context.workdir) if root != context.workdir else '.'}."
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=summary,
            output={"entries": rows},
        )

    async def _files_read(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        path = self._resolve_relative_path(str(request.arguments.get("path") or ""), context)
        if not path.is_file():
            raise RuntimeError(f"file not found: {path}")
        text = path.read_text(encoding="utf-8")[: context.policy.file_output_limit]
        summary = f"Read file {path.relative_to(context.workdir)}."
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=summary,
            output={"path": str(path.relative_to(context.workdir)), "content": text},
        )

    async def _files_search(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        pattern = str(request.arguments.get("pattern") or "").strip()
        if not pattern:
            raise ValueError("pattern is required")
        root = self._resolve_relative_path(str(request.arguments.get("path") or "."), context)
        regex = re.compile(pattern, re.MULTILINE)
        hits = []
        for file_path in root.rglob("*"):
            if len(hits) >= context.policy.search_result_limit:
                break
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in regex.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                line = text.splitlines()[line_no - 1] if text.splitlines() else ""
                hits.append(
                    {
                        "path": str(file_path.relative_to(context.workdir)),
                        "line": line_no,
                        "text": line[:240],
                    }
                )
                if len(hits) >= context.policy.search_result_limit:
                    break
        summary = f"Found {len(hits)} matches for pattern."
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=summary,
            output={"matches": hits},
        )

    async def _git_status(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        code, stdout_text, stderr_text = await self._run_command(
            ["git", "status", "--short", "--branch"],
            cwd=context.workdir,
            timeout_sec=context.policy.shell_timeout_sec,
            output_limit=context.policy.file_output_limit,
        )
        if code != 0:
            raise RuntimeError(stderr_text or stdout_text or "git status failed")
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read git status.",
            output={"statusText": stdout_text},
        )

    async def _git_diff(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        target = str(request.arguments.get("target") or "").strip()
        argv = ["git", "diff", "--stat", "--patch", "--minimal"]
        if target:
            argv.append(target)
        code, stdout_text, stderr_text = await self._run_command(
            argv,
            cwd=context.workdir,
            timeout_sec=context.policy.shell_timeout_sec,
            output_limit=context.policy.file_output_limit,
        )
        if code != 0:
            raise RuntimeError(stderr_text or stdout_text or "git diff failed")
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read git diff.",
            output={"diffText": stdout_text},
        )

    async def _shell_exec(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        if not context.policy.allow_shell:
            raise ToolBlockedError("shell execution disabled by policy")
        command = str(request.arguments.get("command") or "").strip()
        if not command:
            raise ValueError("command is required")
        argv = self._expand_shell_argv(shlex.split(command))
        if not argv:
            raise ValueError("command is required")
        if argv[0] not in context.policy.shell_allowlist:
            raise ToolBlockedError(f"command not allowed: {argv[0]}")
        code, stdout_text, stderr_text = await self._run_command(
            argv,
            cwd=context.workdir,
            timeout_sec=context.policy.shell_timeout_sec,
            output_limit=context.policy.shell_output_limit,
        )
        if code != 0:
            raise RuntimeError(stderr_text or stdout_text or f"command failed with exit {code}")
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"Ran shell command: {argv[0]}",
            output={"command": command, "stdout": stdout_text, "stderr": stderr_text},
        )

    def _expand_shell_argv(self, argv: list[str]) -> list[str]:
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
