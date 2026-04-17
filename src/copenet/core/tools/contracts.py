"""CopeNet-native tool contracts and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Awaitable, Callable, Literal

from copenet.providers import Provider
from copenet.core.sessions import SessionStore, TranscriptStore


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
class ToolBatchEnvelope:
    """Structured model-produced batched tool invocation envelope."""

    calls: list[ToolInvocationEnvelope] = field(default_factory=list)

    def to_requests(self) -> list[ToolExecutionRequest]:
        """Normalize into tool execution requests."""
        return [call.to_request() for call in self.calls]


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


def _candidate_json_objects(text: str) -> list[str]:
    candidate = text.strip()
    if not candidate:
        return []
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidate = "\n".join(lines[1:-1]).strip()

    objects: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            objects.append(value)

    add(candidate)

    decoder = json.JSONDecoder()
    index = 0
    length = len(candidate)
    while index < length:
        brace_index = candidate.find("{", index)
        if brace_index < 0:
            break
        try:
            parsed, end_index = decoder.raw_decode(candidate, brace_index)
        except json.JSONDecodeError:
            index = brace_index + 1
            continue
        if isinstance(parsed, dict):
            add(candidate[brace_index:end_index])
        index = end_index
    return objects


def extract_tool_invocation(text: str) -> ToolInvocationEnvelope | None:
    """Parse a tool invocation JSON object from model output."""
    for raw in _candidate_json_objects(text):
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


def extract_tool_batch_invocation(text: str) -> ToolBatchEnvelope | None:
    """Parse a batch tool invocation JSON object from model output."""
    adjacent_calls: list[ToolInvocationEnvelope] = []
    for raw in _candidate_json_objects(text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        calls_value = parsed.get("tool_calls") or parsed.get("toolCalls") or parsed.get("batch")
        if isinstance(calls_value, list) and len(calls_value) >= 2:
            calls: list[ToolInvocationEnvelope] = []
            for item in calls_value:
                if not isinstance(item, dict):
                    calls = []
                    break
                tool_id = str(
                    item.get("tool_id")
                    or item.get("toolId")
                    or item.get("tool_name")
                    or item.get("toolName")
                    or ""
                ).strip()
                arguments = item.get("arguments") or item.get("args") or {}
                if not tool_id or not isinstance(arguments, dict):
                    calls = []
                    break
                calls.append(ToolInvocationEnvelope(tool_id=tool_id, arguments=arguments))
            if len(calls) >= 2:
                return ToolBatchEnvelope(calls=calls)
        tool_id = str(
            parsed.get("tool_id")
            or parsed.get("toolId")
            or parsed.get("tool_name")
            or parsed.get("toolName")
            or ""
        ).strip()
        arguments = parsed.get("arguments") or parsed.get("args") or {}
        if tool_id and isinstance(arguments, dict):
            adjacent_calls.append(ToolInvocationEnvelope(tool_id=tool_id, arguments=arguments))
    if len(adjacent_calls) >= 2:
        return ToolBatchEnvelope(calls=adjacent_calls)
    return None


def build_tool_prompt_section(tools: list[ToolDescriptor]) -> str:
    """Return instructions for one-step prompted tool use."""
    if not tools:
        return ""
    lines = [
        "You may use one tool or one safe read-only tool batch before answering.",
        "If a single tool is needed, respond with only a JSON object in this shape:",
        '{"tool_id":"<tool id>","arguments":{}}',
        "If multiple independent read-only tools are needed, respond with only a JSON object in this shape:",
        '{"tool_calls":[{"tool_id":"<tool id>","arguments":{}},{"tool_id":"<tool id>","arguments":{}}]}',
        "Do not use markdown fences, prose, or extra keys around the JSON.",
        "If no tool is needed, answer normally.",
        "Available tools:",
    ]
    for tool in tools:
        lines.append(
            f"- {tool.id}: {tool.description} | category={tool.category} | input={json.dumps(tool.input_schema, ensure_ascii=False)}"
        )
    return "\n".join(lines)
