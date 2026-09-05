"""CopeNet-native tool contracts and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from copenet.providers import Provider
from copenet.core.sessions import SessionStore, TranscriptStore

if TYPE_CHECKING:
    from copenet.core.memory import MemoryService
    from copenet.core.persona import PersonaHomeService
    from copenet.core.user_notes import UserNotesService
    from copenet.core.workspace_intel import WorkspaceIntelService
    from copenet.core.market.chart_workspace.models import MarketTurnContext


ToolCategory = Literal["repo-read", "repo-write", "shell-read", "shell-write", "context", "artifact", "browser", "web", "mcp", "chart-write"]
ToolSafetyLevel = Literal["safe", "guarded", "restricted"]
ToolAccessAction = Literal["read", "write", "unknown"]
ToolPolicyDecision = Literal["allowed", "read_roam", "write_blocked", "approval_required", "egress_blocked", "unsafe_unknown"]
ToolEvidenceRole = Literal["none", "discovery", "grounding", "mutation", "verification", "context", "artifact"]
ToolSideEffect = Literal["none", "read", "write", "external"]
ToolEffectKind = Literal["file_read", "repo_search", "shell_command", "file_write", "file_edit", "artifact", "context", "web_search", "web_fetch", "raw"]


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
    evidence_role: ToolEvidenceRole = "none"
    side_effect: ToolSideEffect = "none"
    requires_confirmation: bool = False

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
            "riskClass": self.manifest_risk(),
            "approvalMode": self.manifest_permission(),
            "evidenceRole": self.evidence_role,
            "sideEffect": self.side_effect,
            "requiresConfirmation": self.requires_confirmation,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """Return an OpenAI-compatible (Chat Completions) function tool schema."""
        schema = dict(self.input_schema) if isinstance(self.input_schema, dict) else {}
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": schema,
            },
        }

    def to_responses_tool(self) -> dict[str, Any]:
        """Return a Responses-API function tool schema (flat shape, per PASS-7).

        The Responses endpoint expects {type, name, description, parameters} at
        the top level (not nested under "function" like Chat Completions). We do
        NOT set strict=True: our tools carry optional params (offset/limit/...)
        and strict mode requires every property to be required + additionalProperties
        false, which would reject those calls.
        """
        schema = dict(self.input_schema) if isinstance(self.input_schema, dict) else {"type": "object", "properties": {}}
        return {
            "type": "function",
            # Responses function names must match ^[a-zA-Z0-9_-]+$ (no dots).
            "name": responses_safe_tool_name(self.id),
            "description": self.description,
            "parameters": schema,
        }

    def manifest_risk(self) -> str:
        """Return a compact risk label for the tool manifest."""
        if self.category == "repo-read":
            return "read"
        if self.category == "context":
            return "context"
        if self.category == "shell-read":
            return "shell"
        if self.category == "shell-write":
            return "shell-write"
        if self.category in {"repo-write", "chart-write"}:
            return "write"
        if self.category == "artifact":
            return "artifact"
        return "external"

    def manifest_permission(self) -> str:
        """Return the high-level approval posture for the tool manifest."""
        if self.category in {"repo-read", "context", "web"} and self.safety_level == "safe":
            return "auto_allowed"
        return "policy_gated"


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
    # Presentation for the model only; events/artifacts retain the structured body.
    model_body: str | None = None

    def to_model_payload(self) -> dict[str, Any]:
        """The one model-facing tool-result shape, identical on every tool loop.

        Prompted, native Chat Completions, and Responses all send this. Before it
        existed the native paths sent only `body`, so a policy-blocked call with an
        explicit reason reached the model as `{}` and it simply retried. `ok`,
        `summary`, and `error` are what make a failure actionable.
        """
        payload: dict[str, Any] = {
            "callId": self.call_id,
            "toolId": self.tool_id,
            "channel": self.channel,
            "ok": self.ok,
            "summary": self.summary,
            "body": self.model_body if self.model_body is not None else self.body if self.body is not None else self.output,
        }
        if self.error:
            payload["error"] = self.error
        if self.artifact_id:
            payload["artifactId"] = self.artifact_id
        return payload

    def to_prompt_payload(self) -> str:
        """Return a compact JSON payload suitable for feeding back to a model."""
        return json.dumps(self.to_model_payload(), ensure_ascii=False, indent=2)

    def to_event_payload(
        self,
        *,
        turn_id: str | None = None,
        decision_id: str | None = None,
        arguments: dict[str, Any] | None = None,
        evidence_role: ToolEvidenceRole = "none",
    ) -> dict[str, Any]:
        """Return chat-event metadata for observability."""
        from .projection import _arguments_payload, _preview_payload, _batch_member_payloads, build_tool_effect_payload

        payload: dict[str, Any] = {
            "toolId": self.tool_id,
            "ok": self.ok,
            "summary": self.summary,
        }
        if turn_id:
            payload["turnId"] = turn_id
        if decision_id:
            payload["decisionId"] = decision_id
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
        if arguments:
            call_arguments, argument_truncation = _arguments_payload(arguments)
            payload["arguments"] = call_arguments
            if argument_truncation:
                payload["argumentsTruncated"] = argument_truncation
        preview = _preview_payload(self.tool_id, self.body if self.body is not None else self.output)
        if preview is not None:
            payload["preview"] = preview
        members = _batch_member_payloads(self.body if self.body is not None else self.output)
        if members:
            payload["members"] = members
        if turn_id:
            payload["effect"] = build_tool_effect_payload(
                result=self,
                arguments=arguments or {},
                descriptor=None,
                turn_id=turn_id,
                decision_id=decision_id,
                evidence_role=evidence_role,
            )
        return payload

    def to_runtime_input(self) -> dict[str, Any]:
        """Return the normalized follow-up payload consumed by the next loop pass."""
        payload: dict[str, Any] = {
            "callId": self.call_id,
            "toolId": self.tool_id,
            "channel": self.channel,
            "success": self.ok,
            "body": self.model_body if self.model_body is not None else self.body if self.body is not None else self.output,
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
    available_tools: list[ToolDescriptor] = field(default_factory=list)
    memory_service: MemoryService | None = None
    workspace_intel_service: WorkspaceIntelService | None = None
    persona_service: PersonaHomeService | None = None
    user_notes_service: UserNotesService | None = None
    artifact_store: Any | None = None
    edit_backup_store: Any | None = None
    # Global operator shell allowlist (Brick E). The shell handler consults it as a
    # standing approval; the approval-gated executor adds to it on "approved_always".
    permission_store: Any | None = None
    task_prompt_id: str | None = None
    run_id: str | None = None
    trace: Callable[[str, dict[str, Any] | None], None] | None = None
    market_context: MarketTurnContext | None = None
    chart_store: Any | None = None
    allowed_tool_ids: frozenset[str] | None = None
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


def describe_available_tools(
    tools: list[ToolDescriptor],
    *,
    tool_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return structured detail for one or more tools."""
    requested = {tool_id.strip() for tool_id in tool_ids or [] if tool_id and tool_id.strip()}
    selected = [tool for tool in tools if not requested or tool.id in requested]
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "riskClass": tool.manifest_risk(),
            "approvalMode": tool.manifest_permission(),
            "inputSchema": dict(tool.input_schema),
            "safetyLevel": tool.safety_level,
            "capabilities": list(tool.capabilities),
            "evidenceRole": tool.evidence_role,
            "sideEffect": tool.side_effect,
            "requiresConfirmation": tool.requires_confirmation,
        }
        for tool in selected
    ]


_RESPONSES_NAME_INVALID = re.compile(r"[^a-zA-Z0-9_-]")


def responses_safe_tool_name(name: str) -> str:
    """Map a CopeNet tool id to a Responses-API-legal function name.

    The Responses API requires function names to match ^[a-zA-Z0-9_-]+$ — dots
    are rejected (confirmed live: HTTP 400 'input[k].name does not match
    pattern'). CopeNet ids are dotted (files.read, shell.exec, ...), so we
    replace any illegal char with '_'. The reverse map back to the real tool id
    is rebuilt from the active tool descriptors at the responses tool loop, so
    this need not be invertible on its own.
    """
    return _RESPONSES_NAME_INVALID.sub("_", name)


def build_openai_tool_schemas(tools: list[ToolDescriptor]) -> list[dict[str, Any]]:
    """Return OpenAI-compatible function tool schemas for provider-native tool calling."""
    return [tool.to_openai_tool() for tool in tools]


def build_responses_tool_schemas(tools: list[ToolDescriptor]) -> list[dict[str, Any]]:
    """Return Responses-API function tool schemas (flat shape, per PASS-7)."""
    return [tool.to_responses_tool() for tool in tools]
