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


ToolCategory = Literal["repo-read", "repo-write", "shell-read", "shell-write", "context", "artifact", "browser", "web", "mcp"]
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
        if self.category == "repo-write":
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
            "body": self.body if self.body is not None else self.output,
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


# Inline inspector budget for a tool result that has no hand-written preview
# branch below. Kept at the harness spill threshold
# (tool_result_materialization.LARGE_TOOL_RESULT_CHAR_LIMIT, 4000) on purpose:
# anything larger is already persisted whole as a `tool_output` artifact, so
# pairing the two means every tool result is recoverable by one route or the
# other with no gap in between. Raising the spill threshold without raising this
# reopens that gap.
INSPECTOR_INLINE_BODY_CHARS = 4000


def _generic_preview(body: Any) -> dict[str, Any]:
    """Structural fallback so a tool with no bespoke branch is still inspectable.

    Every branch in `_preview_payload` is a hand-written lossy projection, which
    means a tool nobody wrote a branch for used to render as an empty row in the
    Inspect drawer — indistinguishable from a tool that returned nothing. This
    reports the real body plus an honest character count instead.
    """
    if isinstance(body, str):
        serialized = body
    else:
        serialized = json.dumps(body, ensure_ascii=False, indent=2, default=str)
    full_chars = len(serialized)
    if full_chars <= INSPECTOR_INLINE_BODY_CHARS:
        return {"type": "raw", "text": serialized, "fullChars": full_chars}
    return {
        "type": "raw",
        "text": serialized[:INSPECTOR_INLINE_BODY_CHARS].rstrip(),
        "fullChars": full_chars,
        "truncated": True,
    }


# Keys that mean "this body IS the policy decision, not a tool result".
_POLICY_ONLY_KEYS = {
    "target",
    "workspaceRoot",
    "scope",
    "accessAction",
    "policyDecision",
    "policySummary",
    "command",
    "error",
}


def _is_policy_only_body(body: dict[str, Any]) -> bool:
    """True when a blocked call's body carries nothing but its policy verdict.

    A blocked tool has no result to preview — the body is the refusal. Without
    this it fell through to `_generic_preview`, which JSON-dumped the whole
    policy object into the transcript beside a UI that already renders
    policyDecision, target, and policySummary as their own fields. The operator
    saw the same refusal twice, once as prose and once as a wall of JSON.
    """
    return bool(body) and set(body).issubset(_POLICY_ONLY_KEYS) and "policyDecision" in body


def _preview_payload(tool_id: str, body: Any) -> dict[str, Any] | None:
    if body is None:
        return None
    if not isinstance(body, dict):
        return _generic_preview(body)
    if _is_policy_only_body(body):
        return None
    if tool_id == "plan.write":
        items = body.get("items")
        if isinstance(items, list):
            clean = [
                {"content": str(i.get("content") or ""), "status": str(i.get("status") or "pending")}
                for i in items
                if isinstance(i, dict) and i.get("content")
            ]
            if clean:
                return {"type": "plan", "items": clean}
    if tool_id == "web.search":
        results = body.get("results")
        if isinstance(results, list):
            clean = [
                {
                    "title": str(r.get("title") or ""),
                    "url": str(r.get("url") or ""),
                    "snippet": str(r.get("snippet") or ""),
                }
                for r in results
                if isinstance(r, dict) and r.get("url")
            ]
            return {"type": "web_search", "query": str(body.get("query") or ""), "results": clean[:8]}
    if tool_id == "web.fetch":
        text = body.get("text")
        if isinstance(text, str):
            return {
                "type": "web_doc",
                "url": str(body.get("url") or ""),
                "title": str(body.get("title") or ""),
                "wordCount": int(body.get("wordCount") or 0),
                "text": text.rstrip()[:600],
            }
    if tool_id == "market.dashboard":
        regime = ((body.get("regime") or {}).get("data") or {}).get("current")
        briefing = (body.get("briefing") or {}).get("data") or {}
        return {
            "type": "market_dashboard",
            "regime": regime,
            "headline": briefing.get("headline") if isinstance(briefing, dict) else None,
        }
    if tool_id == "market.ticker":
        return {
            "type": "market_ticker",
            "symbol": body.get("symbol"),
            "last": body.get("last"),
            "change": body.get("change"),
        }
    if tool_id == "market.compare":
        rows = body.get("rows")
        symbols = [row.get("symbol") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        return {"type": "market_compare", "symbols": symbols}
    if tool_id == "market.evidence":
        evidence = body.get("evidence")
        return {
            "type": "market_evidence",
            "symbol": body.get("symbol"),
            "asOf": body.get("asOf"),
            "evidenceCount": body.get("evidenceCount"),
            "insiderNet": body.get("insiderNet"),
            "headlines": [row.get("headline") for row in evidence[:5] if isinstance(row, dict)]
            if isinstance(evidence, list)
            else [],
        }
    if tool_id == "market.financials":
        observations = body.get("observations")
        return {
            "type": "market_financials",
            "symbol": body.get("symbol"),
            "metric": body.get("metric"),
            "frequency": body.get("frequency"),
            "observationCount": len(observations) if isinstance(observations, list) else 0,
            "warnings": body.get("warnings"),
        }
    if tool_id == "files.read":
        path = body.get("path")
        content = body.get("content")
        if isinstance(path, str) and isinstance(content, str):
            # Carry what the MODEL actually read (bounded by file_output_limit) so
            # the Inspect drawer can show the full read; the inline transcript caps
            # the DISPLAY to a 200-line teaser. Not a 240-char receipt anymore.
            preview_content = content.rstrip()[:24000]
            return {
                "path": path,
                "content": preview_content,
                "startLine": body.get("startLine", 1),
                # Number of lines actually carried in this preview, not the
                # whole file. Inline "more lines" must never promise content
                # the Inspect drawer does not have.
                "totalLines": preview_content.count("\n") + 1,
            }
    if tool_id in {"files.write", "files.edit"}:
        diff = body.get("diff")
        if isinstance(diff, str) and diff.strip():
            return {
                "type": "diff",
                "path": str(body.get("path") or body.get("target") or ""),
                "diff": diff,
                "linesAdded": int(body.get("linesAdded") or 0),
                "linesRemoved": int(body.get("linesRemoved") or 0),
                "truncated": bool(body.get("diffTruncated")),
                "created": bool(body.get("created")),
                # Digest the edit left the file at — the revert key (operator can
                # undo this exact edit while the file is still in this state).
                "afterDigest": str(body.get("digest") or ""),
            }
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
    if tool_id == "shell.exec":
        stdout = body.get("stdout")
        stderr = body.get("stderr")
        command = body.get("command")
        parts: list[str] = []
        if isinstance(command, str) and command.strip():
            parts.append(f"$ {command.strip()}")
        if isinstance(stdout, str) and stdout.strip():
            parts.append(stdout.strip())
        if isinstance(stderr, str) and stderr.strip():
            parts.append(stderr.strip())
        if parts:
            return {"preview": "\n".join(parts)[:1000]}
    if tool_id == "artifact.create" and isinstance(body.get("title"), str):
        return {
            "artifactId": body.get("artifactId"),
            "preview": body.get("preview") or body.get("title"),
        }
    return _generic_preview(body)


def _arguments_payload(arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Return the call arguments for the inspector, plus a map of what got clipped.

    Arguments are the half of a tool call the run record never carried: it could
    show that `files.rg` ran but not what it searched for. Keys and structure are
    always preserved so the shape of the call is never in doubt; only an oversized
    string value (a `files.write` body, a pasted blob) is clipped, and the second
    return value names every key that was and its true length — so the drawer can
    say "clipped from 91,204 chars" instead of quietly showing a partial value.
    """
    payload: dict[str, Any] = {}
    truncated: dict[str, int] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > INSPECTOR_INLINE_BODY_CHARS:
            payload[key] = value[:INSPECTOR_INLINE_BODY_CHARS].rstrip()
            truncated[key] = len(value)
            continue
        payload[key] = value
    return payload, truncated


def _batch_member_payloads(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    results = body.get("results")
    if not isinstance(results, list):
        return []
    # Only a real tool batch — where each row is itself a tool result — should
    # expand into members. Other tools (e.g. web.search) legitimately return a
    # "results" list of plain data rows; those carry no "toolId" and must NOT be
    # mistaken for failed sub-tools.
    if not any(isinstance(item, dict) and item.get("toolId") for item in results):
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


def build_tool_effect_payload(
    *,
    result: ToolExecutionResult,
    arguments: dict[str, Any],
    descriptor: ToolDescriptor | None,
    turn_id: str,
    decision_id: str | None = None,
    evidence_role: ToolEvidenceRole | None = None,
) -> dict[str, Any]:
    """Return versioned UI metadata describing one completed tool effect."""
    body = result.body if result.body is not None else result.output
    role = evidence_role or (descriptor.evidence_role if descriptor is not None else "none")
    return {
        "schema_version": "tool_effect.v1",
        "effect_id": f"effect-{result.call_id}" if result.call_id else f"effect-{result.tool_id}",
        "decision_id": decision_id,
        "turn_id": turn_id,
        "tool_id": result.tool_id,
        "kind": _tool_effect_kind(result.tool_id),
        "target": _tool_effect_target(arguments=arguments, body=body),
        "preview": _preview_payload(result.tool_id, body),
        "artifact_id": result.artifact_id,
        "evidence_role": role,
    }


def _tool_effect_kind(tool_id: str) -> ToolEffectKind:
    if tool_id == "files.read":
        return "file_read"
    if tool_id in {"files.search", "files.rg", "files.list", "git.status", "git.diff", "repo.map", "test.discover"}:
        return "repo_search"
    if tool_id == "shell.exec":
        return "shell_command"
    if tool_id == "files.write":
        return "file_write"
    if tool_id == "files.edit":
        return "file_edit"
    if tool_id == "artifact.create":
        return "artifact"
    if tool_id == "web.search":
        return "web_search"
    if tool_id == "web.fetch":
        return "web_fetch"
    if tool_id in {"context.prepare", "memory.read", "memory.write", "market.dashboard", "market.ticker", "market.compare", "market.evidence", "market.financials"}:
        return "context"
    return "raw"


def _tool_effect_target(*, arguments: dict[str, Any], body: Any) -> str | None:
    for key in ("path", "target", "command", "query", "url", "pattern", "title", "symbol"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(body, dict):
        for key in ("path", "target", "command", "query", "url", "pattern", "title"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
