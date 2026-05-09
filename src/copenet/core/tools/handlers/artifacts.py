"""Artifact creation tool handlers."""

from __future__ import annotations

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult


DESCRIPTORS = [
    ToolDescriptor(
        id="artifact.create",
        name="Create Artifact",
        description=(
            "Persist a durable runtime artifact for this session. "
            "Use this when the user asks you to produce or save an explicit artifact."
        ),
        category="artifact",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "artifact_type": {"type": "string"},
            },
            "required": ["title", "body"],
        },
        capabilities=["artifact", "write"],
    ),
]


async def create_artifact(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    if context.artifact_store is None or not context.session_key or not context.run_id:
        raise ToolBlockedError(
            "artifact creation is unavailable in this session",
            workspace_root=str(context.session_workspace_root),
            access_action="write",
            policy_decision="unsafe_unknown",
            policy_summary="Artifact creation requires a live session, run id, and artifact store.",
        )
    title = str(request.arguments.get("title") or "").strip()
    body = request.arguments.get("body")
    artifact_type = str(request.arguments.get("artifact_type") or "summary").strip() or "summary"
    if not title:
        raise ValueError("title is required")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body is required")
    artifact = context.artifact_store.create(
        session_key=context.session_key,
        run_id=context.run_id,
        artifact_type=artifact_type,
        title=title,
        body=body,
        metadata={"createdByTool": "artifact.create"},
    )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Created artifact {artifact.title}.",
        artifact_id=artifact.artifact_id,
        output={
            "artifactId": artifact.artifact_id,
            "artifactType": artifact.type,
            "title": artifact.title,
            "preview": body[:240],
            "workspaceRoot": str(context.session_workspace_root),
            "accessAction": "write",
            "policyDecision": "allowed",
            "policySummary": "Artifact persisted for this session.",
        },
    )


HANDLERS = {
    "artifact.create": create_artifact,
}
