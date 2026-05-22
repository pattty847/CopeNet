"""Context tool handlers."""

from __future__ import annotations

from copenet.core.tools.contracts import (
    ContextPack,
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

from ._shared import read_guidance


DESCRIPTORS = [
    ToolDescriptor(
        id="context.prepare",
        name="Prepare Context",
        description=(
            "Prepare a compact repo/session overview for orientation and prior-session guidance."
        ),
        category="context",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        capabilities=["session", "guidance", "transcript"],
        evidence_role="context",
        side_effect="none",
    ),
]


async def prepare_context(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    session_payload = None
    transcript = []
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
            transcript = context.transcript_store.read_history(
                session_id=session.session_id,
                limit=context.policy.transcript_limit,
            )

    pack = ContextPack(
        session=session_payload,
        transcript=transcript,
        guidance=read_guidance(context),
        runtime={
            "provider": context.provider_name,
            "model": context.model,
            "workdir": str(context.workdir),
            "permissions": _permission_manifest(context),
        },
        workdir=str(context.workdir),
    )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary="Prepared session and repo context.",
        output=pack.to_public_dict(),
    )


HANDLERS = {
    "context.prepare": prepare_context,
}


def _permission_manifest(context: ToolExecutionContext) -> dict[str, object]:
    policy = context.policy
    return {
        "allowedCategories": sorted(policy.allowed_categories),
        "repoWriteEnabled": "repo-write" in policy.allowed_categories,
        "shell": {
            "enabled": policy.allow_shell,
            "unrestricted": policy.unrestricted_shell,
            "allowlist": list(policy.shell_allowlist),
            "approvalPatterns": list(policy.shell_approval_patterns),
        },
        "testCommand": "uv run python scripts/permission_probe_matrix.py",
        "claimGuidance": (
            "Do not claim full access from one successful read command. Verify the specific lever: "
            "repo write tools, unrestricted shell syntax, and approval-gated commands are distinct."
        ),
    }
