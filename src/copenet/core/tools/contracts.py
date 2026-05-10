"""CopeNet-native tool contracts and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from copenet.providers import Provider
from copenet.core.sessions import SessionStore, TranscriptStore

if TYPE_CHECKING:
    from copenet.core.memory import MemoryService
    from copenet.core.profile import PatProfileService


ToolCategory = Literal["repo-read", "repo-write", "shell-read", "context", "artifact", "mcp"]
ToolSafetyLevel = Literal["safe", "guarded", "restricted"]
ToolAccessAction = Literal["read", "write", "unknown"]
ToolPolicyDecision = Literal["allowed", "read_roam", "write_blocked", "approval_required", "unsafe_unknown"]


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

    def to_openai_tool(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function tool schema."""
        schema = dict(self.input_schema) if isinstance(self.input_schema, dict) else {}
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": schema,
            },
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
    call_id: str | None = None
    channel: Literal["tool", "batch", "policy", "search"] = "tool"
    output: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    error: str | None = None
    artifact_id: str | None = None

    def to_prompt_payload(self) -> str:
        """Return a compact JSON payload suitable for feeding back to a model."""
        payload: dict[str, Any] = {
            "callId": self.call_id,
            "toolId": self.tool_id,
            "channel": self.channel,
            "ok": self.ok,
            "summary": self.summary,
            "body": self.body if self.body is not None else self.output,
        }
        if self.error:
            payload["error"] = self.error
        if self.artifact_id:
            payload["artifactId"] = self.artifact_id
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def to_event_payload(self) -> dict[str, Any]:
        """Return chat-event metadata for observability."""
        payload: dict[str, Any] = {
            "toolId": self.tool_id,
            "ok": self.ok,
            "summary": self.summary,
        }
        if self.call_id:
            payload["callId"] = self.call_id
        if self.channel:
            payload["channel"] = self.channel
        if self.error:
            payload["error"] = self.error
        if self.artifact_id:
            payload["artifactId"] = self.artifact_id
        body = self.body if self.body is not None else self.output
        if isinstance(body, dict):
            for key in ("target", "workspaceRoot", "scope", "accessAction", "policyDecision", "policySummary"):
                value = body.get(key)
                if value is not None:
                    payload[key] = value
        preview = _preview_payload(self.tool_id, self.body if self.body is not None else self.output)
        if preview is not None:
            payload["preview"] = preview
        members = _batch_member_payloads(self.body if self.body is not None else self.output)
        if members:
            payload["members"] = members
        return payload

    def to_runtime_input(self) -> dict[str, Any]:
        """Return the normalized follow-up payload consumed by the next loop pass."""
        payload: dict[str, Any] = {
            "callId": self.call_id,
            "toolId": self.tool_id,
            "channel": self.channel,
            "success": self.ok,
            "body": self.body if self.body is not None else self.output,
            "summary": self.summary,
        }
        if self.error:
            payload["error"] = self.error
        if self.artifact_id:
            payload["artifactId"] = self.artifact_id
        body = self.body if self.body is not None else self.output
        if isinstance(body, dict):
            for key in ("target", "workspaceRoot", "scope", "accessAction", "policyDecision", "policySummary"):
                value = body.get(key)
                if value is not None:
                    payload[key] = value
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
class FinalCandidateEnvelope:
    """Structured model-produced final answer candidate envelope."""

    state: Literal["FINAL_CANDIDATE"] = "FINAL_CANDIDATE"
    answer: str = ""
    evidence: list[str] = field(default_factory=list)
    done_conditions_met: list[str] = field(default_factory=list)
    remaining_uncertainty: list[str] = field(default_factory=list)


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
    session_workspace_root: Any
    session_key: str | None
    provider_name: str | None
    model: str | None
    session_store: SessionStore
    transcript_store: TranscriptStore
    providers: dict[str, Provider]
    policy: Any
    memory_service: MemoryService | None = None
    profile_service: PatProfileService | None = None
    artifact_store: Any | None = None
    task_prompt_id: str | None = None
    run_id: str | None = None
    trace: Callable[[str, dict[str, Any] | None], None] | None = None
    ephemeral: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]


class ToolBlockedError(RuntimeError):
    """Raised when a tool request is blocked by policy or path boundaries."""

    def __init__(
        self,
        message: str,
        *,
        target: str | None = None,
        workspace_root: str | None = None,
        scope: str | None = None,
        access_action: ToolAccessAction = "unknown",
        policy_decision: ToolPolicyDecision = "unsafe_unknown",
        policy_summary: str | None = None,
    ) -> None:
        super().__init__(message)
        self.target = target
        self.workspace_root = workspace_root
        self.scope = scope
        self.access_action = access_action
        self.policy_decision = policy_decision
        self.policy_summary = policy_summary or message


def _preview_payload(tool_id: str, body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    if tool_id == "files.read":
        path = body.get("path")
        content = body.get("content")
        if isinstance(path, str) and isinstance(content, str):
            return {"path": path, "content": content.rstrip()[:240]}
    if tool_id in {"files.search", "files.rg"}:
        matches = body.get("matches")
        if isinstance(matches, list):
            preview_matches: list[dict[str, Any]] = []
            for item in matches[:5]:
                if not isinstance(item, dict):
                    continue
                preview_item = {
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "text": item.get("text"),
                }
                if item.get("column") is not None:
                    preview_item["column"] = item.get("column")
                preview_matches.append(preview_item)
            return {"matches": preview_matches}
    if "artifactId" in body and "preview" in body:
        return {"artifactId": body.get("artifactId"), "preview": body.get("preview")}
    if tool_id == "artifact.create" and isinstance(body.get("title"), str):
        return {
            "artifactId": body.get("artifactId"),
            "preview": body.get("preview") or body.get("title"),
        }
    return None


def _batch_member_payloads(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    results = body.get("results")
    if not isinstance(results, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("toolId") or "")
        payload = {
            "toolId": tool_id,
            "ok": bool(item.get("ok")),
            "summary": str(item.get("summary") or ""),
            "error": str(item.get("error")).strip() if item.get("error") is not None else None,
        }
        output = item.get("output")
        if isinstance(output, dict):
            for key in ("target", "workspaceRoot", "scope", "accessAction", "policyDecision", "policySummary"):
                value = output.get(key)
                if value is not None:
                    payload[key] = value
        preview = _preview_payload(tool_id, item.get("output"))
        if preview is not None:
            payload["preview"] = preview
        rows.append(payload)
    return rows


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
        calls_value = parsed.get("tool_calls") or parsed.get("toolCalls")
        if isinstance(calls_value, list) and len(calls_value) == 1 and isinstance(calls_value[0], dict):
            parsed = dict(calls_value[0])
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


def extract_final_candidate(text: str) -> FinalCandidateEnvelope | None:
    """Parse a structured final answer candidate JSON object from model output."""
    def _unwrap_candidate_payload(parsed: dict[str, Any]) -> dict[str, Any] | None:
        if (parsed.get("state") or parsed.get("type")) == "FINAL_CANDIDATE":
            return parsed
        nested = parsed.get("FINAL_CANDIDATE")
        if isinstance(nested, dict):
            merged = dict(nested)
            merged.setdefault("state", "FINAL_CANDIDATE")
            return merged
        return None

    for raw in _candidate_json_objects(text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        candidate = _unwrap_candidate_payload(parsed)
        if not isinstance(candidate, dict):
            continue
        answer = candidate.get("answer")
        if not isinstance(answer, str):
            answer = candidate.get("content")
        if not isinstance(answer, str):
            answer = candidate.get("message")
        if not isinstance(answer, str):
            answer = candidate.get("response")
        if not isinstance(answer, str) or not answer.strip():
            continue

        def _normalize_str_list(value: Any) -> list[str] | None:
            if value is None:
                return []
            if not isinstance(value, list):
                return None
            normalized: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    return None
                stripped = item.strip()
                if stripped:
                    normalized.append(stripped)
            return normalized

        evidence = _normalize_str_list(candidate.get("evidence"))
        done_conditions_met = _normalize_str_list(candidate.get("done_conditions_met"))
        remaining_uncertainty = _normalize_str_list(candidate.get("remaining_uncertainty"))
        if evidence is None or done_conditions_met is None or remaining_uncertainty is None:
            continue
        return FinalCandidateEnvelope(
            answer=answer.strip(),
            evidence=evidence,
            done_conditions_met=done_conditions_met,
            remaining_uncertainty=remaining_uncertainty,
        )
    return None


def build_tool_prompt_section(tools: list[ToolDescriptor], *, context: ToolExecutionContext | None = None) -> str:
    """Return instructions for one-step prompted tool use."""
    if not tools:
        return ""
    tool_mode = (context.task_prompt_id or "none").strip() if context is not None else "none"
    workspace_root = str(context.session_workspace_root) if context is not None else "(unknown)"
    shell_allowlist = ", ".join(sorted(getattr(context.policy, "shell_allowlist", ()) or ())) if context is not None else "(unknown)"
    available_ids = ", ".join(tool.id for tool in tools) or "(none)"
    available_categories = {tool.category for tool in tools}
    unavailable_categories = [
        category
        for category in ("repo-write", "artifact", "shell-read")
        if category not in available_categories
    ]
    unavailable_text = ", ".join(unavailable_categories) if unavailable_categories else "(none)"
    artifact_support = "available via artifact.create" if "artifact.create" in {tool.id for tool in tools} else "not available in this session"
    lines = [
        "Respond with exactly one legal JSON action: TOOL_CALL, TOOL_BATCH, or FINAL_CANDIDATE.",
        "Capability manifest:",
        f"- Workspace root: {workspace_root}",
        f"- Tool mode: {tool_mode}",
        f"- Available tool ids: {available_ids}",
        f"- Unavailable capability classes: {unavailable_text}",
        f"- Shell constraints: allowlisted read-only commands only ({shell_allowlist})",
        f"- Artifact support: {artifact_support}",
        "- Sequence normal work as: inspect -> edit/write if available -> verify/read shell -> create artifact if asked.",
        "- Shallow orientation is not enough for repo/code claims: files.list and context.prepare should lead to files.rg or files.read, not to early finalization.",
        "If a single tool is needed, respond with only a JSON object in this shape:",
        '{"tool_id":"<tool id>","arguments":{}}',
        "If multiple independent read-only repo/context tools are needed, respond with only a JSON object in this shape:",
        '{"tool_calls":[{"tool_id":"<tool id>","arguments":{}},{"tool_id":"<tool id>","arguments":{}}]}',
        "TOOL_BATCH only supports read-only repo/context work. Request writes, patches, or shell commands as individual TOOL_CALL actions after you inspect the needed files.",
        "If you are ready to finalize, respond with only a JSON object in this shape:",
        '{"state":"FINAL_CANDIDATE","answer":"...","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}',
        "No markdown fences. No prose outside JSON. No extra wrapper keys.",
        "Available tools:",
    ]
    for tool in tools:
        lines.append(
            f"- {tool.id}: {tool.description} | category={tool.category} | input={json.dumps(tool.input_schema, ensure_ascii=False)}"
        )
    return "\n".join(lines)


def build_openai_tool_schemas(tools: list[ToolDescriptor]) -> list[dict[str, Any]]:
    """Return OpenAI-compatible function tool schemas for provider-native tool calling."""
    return [tool.to_openai_tool() for tool in tools]
