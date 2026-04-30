"""Turn planning for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from copenet.providers import Provider
from copenet.core.tools import ToolDescriptor

from .capabilities import ModelCapabilityProfile, normalize_capabilities
from .final_gate import TaskContract


TraceRecorder = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    tools: list[ToolDescriptor] = field(default_factory=list)
    task_contract: TaskContract | None = None
    will_attempt_tool_loop: bool = False
    tool_execution_mode: Literal["none", "native", "single", "batch"] = "none"
    batch_read_allowed: bool = False


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
    task_contract = infer_task_contract(prompt=prompt, tools=all_tools) if all_tools else None
    allowed_ids = set(task_contract.allowed_tools) if task_contract is not None else {tool.id for tool in all_tools}
    tools = [tool for tool in all_tools if tool.id in allowed_ids]
    use_native_tools = bool(tools and profile.tool_calls)
    use_prompted_tools = bool(tools and not use_native_tools and profile.prompted_tool_use)
    plan = HarnessTurnPlan(
        provider=provider_name,
        model=model,
        capability_profile=profile,
        tools=tools,
        task_contract=task_contract,
        will_attempt_tool_loop=bool(use_native_tools or use_prompted_tools),
        tool_execution_mode="native" if use_native_tools else ("batch" if use_prompted_tools else "none"),
        batch_read_allowed=bool(use_prompted_tools),
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
                "availableToolIds": [tool.id for tool in tools],
                "taskContract": plan.task_contract.to_public_dict() if plan.task_contract else None,
            },
        )
    return plan


def infer_task_contract(*, prompt: str, tools: list[ToolDescriptor]) -> TaskContract | None:
    lowered = prompt.lower()
    if not any(
        token in lowered
        for token in {
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
        }
    ):
        return None
    if any(token in lowered for token in ["patch and verify", "apply patch", "run check", "run test"]):
        task_kind = "patch_apply_verify"
        goal = prompt.strip() or "Patch and verify the requested change."
        preferred = ["files.read", "patch.apply", "test.run"]
        required = ["grounded file evidence", "patch applied", "verification run"]
        done = ["patch applied", "verification run"]
    elif "patch plan" in lowered or ("patch" in lowered and "plan" in lowered):
        task_kind = "patch_plan"
        goal = prompt.strip() or "Produce a grounded patch plan."
        preferred = ["files.search", "files.read", "context.prepare"]
        required = ["grounded file evidence tied to the patch plan"]
        done = ["grounded evidence", "file path citation"]
    elif any(token in lowered for token in ["architecture", "setup", "explain the repo", "summarize the repo", "explain the architecture"]):
        task_kind = "repo_explain"
        goal = prompt.strip() or "Explain the repository with grounded evidence."
        preferred = ["files.read", "files.search", "context.prepare"]
        required = ["grounded file evidence"]
        done = ["grounded file evidence", "file path citation"]
    else:
        task_kind = "repo_explore"
        goal = prompt.strip() or "Explore the repository using tools."
        preferred = ["files.search", "files.read", "context.prepare"]
        required = ["at least one grounding action beyond files.list"]
        done = ["grounded evidence"]

    preferred_set = set(preferred)
    allowed_tools = [tool.id for tool in tools if tool.id in preferred_set or tool.id in {"files.list", "git.diff", "git.status"}]
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
