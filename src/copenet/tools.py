"""CopeNet-native tool contracts, policy, and v1 safe tool runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import glob
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any, Awaitable, Callable, Literal

from copenet.providers import Provider
from copenet.sessions import SessionStore, TranscriptStore


ToolCategory = Literal["repo-read", "repo-write", "shell-read", "context", "mcp"]
ToolSafetyLevel = Literal["safe", "guarded", "restricted"]


@dataclass(frozen=True)
class ToolDescriptor:
    """One CopeNet-native tool definition."""

    id: str
    name: str
    description: str
    category: ToolCategory
    input_schema: dict[str, Any] = field(default_factory=dict)
    safety_level: ToolSafetyLevel = "safe"
    capabilities: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly descriptor for RPC clients."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "inputSchema": self.input_schema,
            "safetyLevel": self.safety_level,
            "capabilities": list(self.capabilities),
        }


ToolSpec = ToolDescriptor


@dataclass(frozen=True)
class ToolExecutionRequest:
    """Normalized request to execute a tool."""

    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)


ToolCallRequest = ToolExecutionRequest


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized result from one tool invocation."""

    tool_id: str
    ok: bool
    summary: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_prompt_payload(self) -> str:
        """Return a compact JSON payload suitable for feeding back to a model."""
        payload: dict[str, Any] = {
            "toolId": self.tool_id,
            "ok": self.ok,
            "summary": self.summary,
            "output": self.output,
        }
        if self.error:
            payload["error"] = self.error
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def to_event_payload(self) -> dict[str, Any]:
        """Return chat-event metadata for observability."""
        payload = {
            "toolId": self.tool_id,
            "ok": self.ok,
            "summary": self.summary,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class ToolPolicy:
    """Safety policy for the v1 tool runtime."""

    allowed_categories: set[ToolCategory] = field(
        default_factory=lambda: {"repo-read", "shell-read", "context"}
    )
    allow_shell: bool = True
    shell_allowlist: tuple[str, ...] = ("git", "rg", "ls", "pwd", "find")
    shell_timeout_sec: float = 5.0
    shell_output_limit: int = 8000
    file_output_limit: int = 12000
    search_result_limit: int = 80
    list_result_limit: int = 200
    transcript_limit: int = 8
    guidance_char_limit: int = 6000


@dataclass(frozen=True)
class ToolInvocationEnvelope:
    """Structured model-produced tool invocation envelope."""

    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_request(self) -> ToolExecutionRequest:
        """Normalize into a tool execution request."""
        return ToolExecutionRequest(tool_id=self.tool_id, arguments=dict(self.arguments))


@dataclass(frozen=True)
class ContextPack:
    """Context payload prepared for safe repo inspection."""

    session: dict[str, Any] | None
    transcript: list[dict[str, Any]]
    guidance: str
    runtime: dict[str, Any]
    workdir: str

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly context pack."""
        return {
            "session": self.session,
            "transcript": self.transcript,
            "guidance": self.guidance,
            "runtime": self.runtime,
            "workdir": self.workdir,
        }


@dataclass(frozen=True)
class ToolExecutionContext:
    """Execution context shared across tool handlers."""

    workdir: Path
    session_key: str | None
    provider_name: str | None
    model: str | None
    session_store: SessionStore
    transcript_store: TranscriptStore
    providers: dict[str, Provider]
    policy: ToolPolicy
    trace: Callable[[str, dict[str, Any] | None], None] | None = None


ToolHandler = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]


class ToolBlockedError(RuntimeError):
    """Raised when a tool request is blocked by policy or path boundaries."""


def extract_tool_invocation(text: str) -> ToolInvocationEnvelope | None:
    """Parse a tool invocation JSON object from model output."""
    candidate = text.strip()
    if not candidate:
        return None
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidate = "\n".join(lines[1:-1]).strip()

    objects = [candidate]
    for match in re.finditer(r"\{[\s\S]*\}", candidate):
        objects.append(match.group(0))

    for raw in objects:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        tool_id = str(
            parsed.get("tool_id")
            or parsed.get("toolId")
            or parsed.get("tool_name")
            or parsed.get("toolName")
            or ""
        ).strip()
        arguments = parsed.get("arguments") or parsed.get("args") or {}
        if tool_id and isinstance(arguments, dict):
            return ToolInvocationEnvelope(tool_id=tool_id, arguments=arguments)
    return None


def build_tool_prompt_section(tools: list[ToolDescriptor]) -> str:
    """Return instructions for one-step prompted tool use."""
    if not tools:
        return ""
    lines = [
        "You may use at most one tool before answering.",
        "If a tool is needed, respond with only a JSON object in this shape:",
        '{"tool_id":"<tool id>","arguments":{}}',
        "Do not use markdown fences, prose, or extra keys around the JSON.",
        "If no tool is needed, answer normally.",
        "Available tools:",
    ]
    for tool in tools:
        lines.append(
            f"- {tool.id}: {tool.description} | category={tool.category} | input={json.dumps(tool.input_schema, ensure_ascii=False)}"
        )
    return "\n".join(lines)


class ToolRegistry:
    """Central v1 tool registry and safe execution runtime."""

    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self._policy = policy or ToolPolicy()
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._register_defaults()

    @property
    def policy(self) -> ToolPolicy:
        """Return the active tool policy."""
        return self._policy

    def list_tools(self) -> list[ToolDescriptor]:
        """Return all registered tools."""
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def list_public_tools(self) -> list[dict[str, Any]]:
        """Return public tool descriptors for RPC clients."""
        return [descriptor.to_public_dict() for descriptor in self.list_tools()]

    async def execute(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute one tool request under the current policy."""
        descriptor = self._descriptors.get(request.tool_id)
        if descriptor is None:
            self._trace(context, "tool_blocked", {"toolId": request.tool_id, "reason": "unknown tool"})
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Unknown tool: {request.tool_id}",
                error="unknown tool",
            )
        if descriptor.category not in context.policy.allowed_categories:
            self._trace(
                context,
                "tool_blocked",
                {
                    "toolId": request.tool_id,
                    "category": descriptor.category,
                    "reason": "tool category not allowed",
                },
            )
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Tool category not allowed: {descriptor.category}",
                error="tool category not allowed",
            )
        handler = self._handlers[request.tool_id]
        try:
            result = await handler(request, context)
            self._trace(
                context,
                "tool_executed",
                {
                    "toolId": request.tool_id,
                    "ok": result.ok,
                    "summary": result.summary,
                    "error": result.error,
                },
            )
            return result
        except ToolBlockedError as exc:
            self._trace(
                context,
                "tool_blocked",
                {
                    "toolId": request.tool_id,
                    "reason": str(exc),
                },
            )
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Tool blocked: {request.tool_id}",
                error=str(exc),
            )
        except Exception as exc:
            self._trace(
                context,
                "tool_executed",
                {
                    "toolId": request.tool_id,
                    "ok": False,
                    "summary": f"Tool execution failed: {request.tool_id}",
                    "error": str(exc),
                },
            )
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Tool execution failed: {request.tool_id}",
                error=str(exc),
            )

    def _trace(self, context: ToolExecutionContext, event: str, payload: dict[str, Any]) -> None:
        if context.trace is None:
            return
        context.trace(event, payload)

    def _register(self, descriptor: ToolDescriptor, handler: ToolHandler) -> None:
        self._descriptors[descriptor.id] = descriptor
        self._handlers[descriptor.id] = handler

    def _register_defaults(self) -> None:
        self._register(
            ToolDescriptor(
                id="context.prepare",
                name="Context Prepare",
                description="Prepare focused repo, session, and runtime context for the current conversation.",
                category="context",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                capabilities=["context", "session"],
            ),
            self._context_prepare,
        )
        self._register(
            ToolDescriptor(
                id="files.list",
                name="Files List",
                description="List files or directories under the current workdir.",
                category="repo-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                },
                capabilities=["read", "filesystem"],
            ),
            self._files_list,
        )
        self._register(
            ToolDescriptor(
                id="files.read",
                name="Files Read",
                description="Read a UTF-8 text file relative to the current workdir.",
                category="repo-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
                capabilities=["read", "filesystem"],
            ),
            self._files_read,
        )
        self._register(
            ToolDescriptor(
                id="files.search",
                name="Files Search",
                description="Search file contents with ripgrep-style matching.",
                category="repo-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
                capabilities=["read", "search"],
            ),
            self._files_search,
        )
        self._register(
            ToolDescriptor(
                id="git.status",
                name="Git Status",
                description="Show concise git working tree status for the current workdir.",
                category="shell-read",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                capabilities=["git", "shell"],
            ),
            self._git_status,
        )
        self._register(
            ToolDescriptor(
                id="git.diff",
                name="Git Diff",
                description="Show a bounded git diff summary for the current workdir.",
                category="shell-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                    },
                },
                capabilities=["git", "shell"],
            ),
            self._git_diff,
        )
        self._register(
            ToolDescriptor(
                id="shell.exec",
                name="Shell Exec",
                description="Run a safe inspection-oriented shell command from the allowlist.",
                category="shell-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                    "required": ["command"],
                },
                safety_level="guarded",
                capabilities=["shell", "inspect"],
            ),
            self._shell_exec,
        )

    def _resolve_relative_path(self, raw_path: str | None, workdir: Path) -> Path:
        candidate = (raw_path or ".").strip() or "."
        resolved = (workdir / candidate).resolve()
        try:
            resolved.relative_to(workdir.resolve())
        except ValueError as exc:
            raise ToolBlockedError("path escapes workdir") from exc
        return resolved

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...[truncated]"

    async def _run_command(
        self,
        argv: list[str],
        *,
        cwd: Path,
        timeout_sec: float,
        output_limit: int,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("command timed out")
        stdout_text = self._truncate_text(stdout.decode("utf-8", errors="replace"), output_limit)
        stderr_text = self._truncate_text(stderr.decode("utf-8", errors="replace"), output_limit)
        return proc.returncode, stdout_text, stderr_text

    async def _context_prepare(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        entry = context.session_store.get(context.session_key or "") if context.session_key else None
        transcript: list[dict[str, Any]] = []
        if entry is not None:
            transcript = context.transcript_store.read_history(
                session_id=entry.session_id,
                limit=context.policy.transcript_limit,
            )
        guidance_path = context.workdir / "AGENTS.md"
        guidance = ""
        if guidance_path.is_file():
            guidance = guidance_path.read_text(encoding="utf-8")
            guidance = self._truncate_text(guidance, context.policy.guidance_char_limit)
        runtime = {
            "provider": context.provider_name,
            "model": context.model,
            "providerAvailable": context.provider_name in context.providers if context.provider_name else False,
        }
        pack = ContextPack(
            session={
                "key": entry.session_key,
                "title": entry.title,
                "provider": entry.provider,
                "model": entry.model,
                "systemPromptId": entry.system_prompt_id,
                "taskPromptId": entry.task_prompt_id,
            }
            if entry is not None
            else None,
            transcript=transcript,
            guidance=guidance,
            runtime=runtime,
            workdir=str(context.workdir),
        )
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Prepared focused session and repo context.",
            output=pack.to_public_dict(),
        )

    async def _files_list(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        root = self._resolve_relative_path(str(request.arguments.get("path") or "."), context.workdir)
        if not root.exists():
            raise ValueError("path does not exist")
        if root.is_file():
            entries = [{"path": str(root.relative_to(context.workdir)), "type": "file"}]
        else:
            rows: list[dict[str, Any]] = []
            for idx, child in enumerate(sorted(root.iterdir(), key=lambda item: item.name.lower())):
                if idx >= context.policy.list_result_limit:
                    break
                rows.append(
                    {
                        "path": str(child.relative_to(context.workdir)),
                        "type": "dir" if child.is_dir() else "file",
                    }
                )
            entries = rows
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"Listed {len(entries)} path(s).",
            output={"entries": entries},
        )

    async def _files_read(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        raw_path = str(request.arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("path is required")
        path = self._resolve_relative_path(raw_path, context.workdir)
        if not path.is_file():
            raise ValueError("path is not a file")
        content = path.read_text(encoding="utf-8")
        content = self._truncate_text(content, context.policy.file_output_limit)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"Read {path.relative_to(context.workdir)}.",
            output={"path": str(path.relative_to(context.workdir)), "content": content},
        )

    async def _files_search(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        pattern = str(request.arguments.get("pattern") or "").strip()
        if not pattern:
            raise ValueError("pattern is required")
        root = self._resolve_relative_path(str(request.arguments.get("path") or "."), context.workdir)
        if not root.exists():
            raise ValueError("search root does not exist")
        rg = shutil.which("rg")
        if rg:
            argv = [
                rg,
                "--line-number",
                "--color",
                "never",
                "--max-count",
                str(context.policy.search_result_limit),
                pattern,
                str(root),
            ]
            code, stdout_text, stderr_text = await self._run_command(
                argv,
                cwd=context.workdir,
                timeout_sec=context.policy.shell_timeout_sec,
                output_limit=context.policy.file_output_limit,
            )
            if code not in {0, 1}:
                raise RuntimeError(stderr_text or stdout_text or "search failed")
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=True,
                summary="Searched files with ripgrep.",
                output={"pattern": pattern, "matchesText": stdout_text},
            )

        matches: list[str] = []
        regex = re.compile(pattern)
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(f"{file_path.relative_to(context.workdir)}:{line_no}:{line}")
                    if len(matches) >= context.policy.search_result_limit:
                        break
            if len(matches) >= context.policy.search_result_limit:
                break
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"Found {len(matches)} match(es).",
            output={"pattern": pattern, "matchesText": "\n".join(matches)},
        )

    async def _git_status(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        code, stdout_text, stderr_text = await self._run_command(
            ["git", "status", "--short"],
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
