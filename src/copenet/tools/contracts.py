"""CopeNet-native tool contracts and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
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

    workdir: Any
    session_key: str | None
    provider_name: str | None
    model: str | None
    session_store: SessionStore
    transcript_store: TranscriptStore
    providers: dict[str, Provider]
    policy: Any
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
