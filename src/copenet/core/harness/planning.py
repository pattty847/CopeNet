"""Turn planning for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Literal

from copenet.providers import Provider
from copenet.core.tools import ToolDescriptor

from .capabilities import ModelCapabilityProfile, normalize_capabilities
from .final_gate import TaskContract


TraceRecorder = Callable[[str, dict[str, Any] | None], None]
InteractionClass = Literal["casual", "advisory", "agent", "risky"]
PromptFrame = Literal["light", "full"]


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    interaction_class: InteractionClass = "casual"
    prompt_frame: PromptFrame = "light"
    tools: list[ToolDescriptor] = field(default_factory=list)
    task_contract: TaskContract | None = None
    will_attempt_tool_loop: bool = False
    tool_execution_mode: Literal["none", "native", "single", "batch"] = "none"
    batch_read_allowed: bool = False
    tool_loop_suppressed_reason: str | None = None


async def plan_turn(
    *,
    provider: Provider,
    provider_name: str,
    model: str | None,
    prompt: str = "",
    available_tools: list[ToolDescriptor] | None = None,
    trace: TraceRecorder | None = None,
) -> HarnessTurnPlan:
    """Build a normalized turn plan from provider metadata and available tools."""
    all_tools = available_tools or []
    provider_meta = await provider.describe()
    caps = normalize_capabilities(provider_meta if isinstance(provider_meta, dict) else {})
    if model:
        try:
            models = await provider.list_models()
        except Exception:
            models = []
        matched = next((row for row in models if row.id == model), None)
        if matched is not None and isinstance(matched.capabilities, dict):
            for key, value in matched.capabilities.items():
                caps[key] = value
    profile = ModelCapabilityProfile(
        provider=provider_name,
        model=model,
        chat=caps.get("chat", True),
        embeddings=caps.get("embeddings", False),
        tool_calls=caps.get("toolCalls", False),
        streaming=caps.get("streaming", True),
        resume=caps.get("resume", False),
        prompted_tool_use=caps.get("promptedToolUse", caps.get("toolCalls", False)),
    )
    interaction_class = classify_interaction(prompt=prompt)
    tool_intent = interaction_class in {"agent", "risky"}
    task_contract = infer_task_contract(prompt=prompt, tools=all_tools) if all_tools and tool_intent else None
    allowed_ids = set(task_contract.allowed_tools) if task_contract is not None else {tool.id for tool in all_tools}
    tools = [tool for tool in all_tools if tool.id in allowed_ids]
    use_native_tools = bool(tool_intent and tools and profile.tool_calls)
    use_prompted_tools = bool(tool_intent and tools and not use_native_tools and profile.prompted_tool_use)
    suppressed_reason: str | None = None
    if not tool_intent and tools:
        suppressed_reason = f"interaction_class_{interaction_class}"
    elif tool_intent and tools and not (use_native_tools or use_prompted_tools):
        suppressed_reason = "provider_tool_loop_unavailable"
    plan = HarnessTurnPlan(
        provider=provider_name,
        model=model,
        capability_profile=profile,
        interaction_class=interaction_class,
        prompt_frame="full" if interaction_class in {"agent", "risky"} else "light",
        tools=tools,
        task_contract=task_contract,
        will_attempt_tool_loop=bool(use_native_tools or use_prompted_tools),
        tool_execution_mode="native" if use_native_tools else ("batch" if use_prompted_tools else "none"),
        batch_read_allowed=bool(use_prompted_tools),
        tool_loop_suppressed_reason=suppressed_reason,
    )
    if trace is not None:
        trace(
            "harness_planned",
            {
                "capabilityProfile": {
                    "provider": profile.provider,
                    "model": profile.model,
                    "chat": profile.chat,
                    "embeddings": profile.embeddings,
                    "toolCalls": profile.tool_calls,
                    "streaming": profile.streaming,
                    "resume": profile.resume,
                    "promptedToolUse": profile.prompted_tool_use,
                },
                "willAttemptToolLoop": plan.will_attempt_tool_loop,
                "toolExecutionMode": plan.tool_execution_mode,
                "batchReadAllowed": plan.batch_read_allowed,
                "interactionClass": plan.interaction_class,
                "promptFrame": plan.prompt_frame,
                "toolLoopSuppressedReason": plan.tool_loop_suppressed_reason,
                "availableToolIds": [tool.id for tool in tools],
                "taskContract": plan.task_contract.to_public_dict() if plan.task_contract else None,
            },
        )
    return plan


def classify_interaction(*, prompt: str) -> InteractionClass:
    lowered = prompt.lower()

    def has_phrase(*phrases: str) -> bool:
        for phrase in phrases:
            normalized = phrase.strip().lower()
            if not normalized:
                continue
            if any(char in normalized for char in "/._-"):
                if normalized in lowered:
                    return True
                continue
            pattern = r"(?<!\w)" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?!\w)"
            if re.search(pattern, lowered):
                return True
        return False

    has_repo_hint = has_phrase(
        "repo",
        "repository",
        "codebase",
        "harness",
        "source file",
        "workspace",
        "architecture",
        "docs/",
        "src/",
        ".py",
        ".ts",
        ".tsx",
        ".md",
    )
    has_file_hint = has_phrase(
        "file",
        "files",
        "directory",
        "folder",
        "readme",
        "desktop",
        "downloads",
        "documents",
        "docs/",
        "src/",
    )
    has_risky = has_phrase(
        "delete",
        "remove file",
        "rm",
        "reset",
        "rebase",
        "push",
        "clean the repo",
        "install dependency",
        "install dependencies",
        "npm install",
        "pnpm install",
        "pip install",
        "uv add",
        "poetry add",
        "send message",
        "telegram",
        "slack",
        "secret",
        "secrets",
        "token",
        "credential",
        "env var",
        "environment variable",
        "authenticate",
        "log in",
        "login",
    )
    if has_risky:
        return "risky"

    has_agent_action = has_phrase(
        "use a tool",
        "use tools",
        "inspect",
        "debug",
        "implement",
        "make the change",
        "change the ui",
        "fix",
        "edit",
        "rewrite",
        "patch",
        "update the file",
        "read the file",
        "read the files",
        "search the repo",
        "search the repository",
        "search for",
        "open the repo",
        "check the code",
        "run test",
        "run tests",
        "run command",
        "run ls",
        "grep",
        "ripgrep",
        "which files",
        "what files",
        "grounded evidence",
        "cite the file",
        "produce an artifact",
    )
    has_file_workflow = has_phrase(
        "read",
        "inspect",
        "open",
        "edit",
        "write",
        "rewrite",
        "change",
        "update",
        "fix",
        "command",
        "run",
        "verify",
        "artifact",
        "save this",
    )
    if (has_repo_hint or has_file_hint) and has_file_workflow:
        return "agent"
    if has_agent_action:
        return "agent"

    has_advisory = has_phrase(
        "what do you think",
        "thoughts",
        "feedback",
        "tradeoff",
        "tradeoff analysis",
        "should we",
        "would you",
        "opinion",
        "vibe",
        "brainstorm",
        "riff",
        "does this make sense",
        "direction",
        "future direction",
        "critique",
        "review this idea",
    )
    if has_advisory or has_repo_hint or has_file_hint:
        return "advisory"
    return "casual"


def infer_task_contract(*, prompt: str, tools: list[ToolDescriptor]) -> TaskContract | None:
    lowered = prompt.lower()

    def has_phrase(*phrases: str) -> bool:
        for phrase in phrases:
            normalized = phrase.strip().lower()
            if not normalized:
                continue
            if any(char in normalized for char in "/._-"):
                if normalized in lowered:
                    return True
                continue
            pattern = r"(?<!\w)" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?!\w)"
            if re.search(pattern, lowered):
                return True
        return False

    has_repo_hint = has_phrase(
        "repo",
        "repository",
        "architecture",
        "setup",
        "patch",
        "runtime code",
        "source file",
        "bug",
        "relevant files",
        "codebase",
    )
    has_file_hint = has_phrase(
        "file",
        "files",
        "directory",
        "folder",
        "docs/",
        "src/",
        "readme",
        ".py",
        ".ts",
        ".tsx",
        ".md",
    )
    has_read = has_phrase("read", "inspect", "open", "check the files", "look at")
    has_write = has_phrase("edit", "write", "rewrite", "change", "update", "fix")
    has_command = has_phrase("command", "run", "ls", "pwd", "verify", "check")
    has_artifact = has_phrase("artifact", "summary file", "produce a note", "save this")

    if not has_repo_hint and not (has_file_hint and (has_read or has_write or has_command or has_artifact)):
        return None

    if has_phrase("patch and verify", "apply patch", "run check", "run test") or (has_write and has_command):
        task_kind = "patch_apply_verify"
        goal = prompt.strip() or "Patch and verify the requested change."
        preferred = ["files.read", "files.edit", "files.write", "git.diff", "shell.exec"]
        required = ["grounded file evidence", "patch applied", "verification run"]
        done = ["grounded file evidence", "patch applied", "verification run"]
    elif has_phrase("patch plan") or (has_phrase("patch") and has_phrase("plan")):
        task_kind = "patch_plan"
        goal = prompt.strip() or "Produce a grounded patch plan."
        preferred = ["files.rg", "files.read", "context.prepare"]
        required = ["grounded file evidence tied to the patch plan"]
        done = ["grounded evidence", "file path citation"]
    elif has_artifact and (has_read or has_write or has_command):
        task_kind = "artifact_workflow"
        goal = prompt.strip() or "Complete the requested work and persist an artifact."
        preferred = ["files.read", "files.edit", "files.write", "shell.exec", "artifact.create"]
        required = ["grounded file evidence", "artifact created"]
        done = ["grounded evidence", "artifact created"]
    elif has_write:
        task_kind = "repo_edit"
        goal = prompt.strip() or "Make a grounded repository edit."
        preferred = ["files.read", "files.edit", "files.write", "git.diff"]
        required = ["grounded file evidence", "patch applied"]
        done = ["grounded evidence", "patch applied"]
    elif has_phrase("architecture", "setup", "explain the repo", "summarize the repo", "explain the architecture"):
        task_kind = "repo_explain"
        goal = prompt.strip() or "Explain the repository with grounded evidence."
        preferred = ["files.rg", "files.read", "context.prepare"]
        required = ["grounded file evidence"]
        done = ["grounded file evidence", "file path citation"]
    else:
        task_kind = "repo_explore"
        goal = prompt.strip() or "Explore the repository using tools."
        preferred = ["files.rg", "files.read", "context.prepare", "shell.exec"] if has_command else ["files.rg", "files.read", "context.prepare"]
        required = ["at least one grounding action beyond files.list"]
        done = ["grounded evidence"]

    preferred_set = set(preferred)
    always_allowed = {"files.list", "git.diff", "git.status", "artifact.create"}
    allowed_tools = [tool.id for tool in tools if tool.id in preferred_set or tool.id in always_allowed]
    if not allowed_tools:
        allowed_tools = [tool.id for tool in tools]
    return TaskContract(
        goal=goal,
        task_kind=task_kind,
        allowed_tools=allowed_tools,
        required_evidence=required,
        done_conditions=done,
        preferred_next_actions=preferred,
        final_answer_rules=["Do not finalize until the contract is satisfied.", "Cite grounded file evidence when making non-trivial claims."],
    )
