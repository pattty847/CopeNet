"""Artifact tool handlers: read a persisted session artifact, create one."""

from __future__ import annotations

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

# Same ceiling files.read honors for an explicit limit.
ARTIFACT_READ_ABSOLUTE_MAX = 500_000


DESCRIPTORS = [
    ToolDescriptor(
        id="artifact.read",
        name="Read Artifact",
        description=(
            "Read a persisted artifact from this session by id: the full output of an earlier tool call "
            "(a result that said `saved as artifact <id>`, or an `artifactId` in a replayed receipt), or an "
            "artifact created with artifact.create. Pass offset (0-based char) and limit (chars) to page; a "
            "truncated read tells you the next offset. Only this session's artifacts are readable."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0, "description": "0-based character offset."},
                "limit": {"type": "integer", "minimum": 1, "description": "Max characters to return."},
            },
            "required": ["artifact_id"],
        },
        capabilities=["artifact", "read"],
        evidence_role="grounding",
        side_effect="read",
    ),
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
        evidence_role="artifact",
        side_effect="write",
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


async def read_artifact(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    if context.artifact_store is None or not context.session_key:
        raise ToolBlockedError(
            "artifact reads are unavailable in this session",
            workspace_root=str(context.session_workspace_root),
            access_action="read",
            policy_decision="unsafe_unknown",
            policy_summary="Artifact reads require a live session and artifact store.",
        )
    artifact_id = str(request.arguments.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id is required")
    artifact = context.artifact_store.get(context.session_key, artifact_id)
    if artifact is None:
        raise RuntimeError(f"no artifact {artifact_id} in this session")
    offset = max(int(request.arguments.get("offset") or 0), 0)
    requested_limit = int(request.arguments.get("limit") or 0)
    effective_limit = min(requested_limit, ARTIFACT_READ_ABSOLUTE_MAX) if requested_limit > 0 else context.policy.file_output_limit
    body = artifact.body
    text = body[offset : offset + effective_limit]
    next_offset = offset + len(text)
    truncated = next_offset < len(body)
    if truncated:
        text = f"{text}\n\n[Artifact read truncated at char {next_offset} of {len(body)}. Use offset={next_offset} to continue.]"
    source_tool_id = str((artifact.metadata or {}).get("toolId") or "") or None
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Read artifact {artifact.title} chars {offset}-{next_offset} of {len(body)}.",
        artifact_id=artifact.artifact_id,
        output={
            "artifactId": artifact.artifact_id,
            "artifactType": artifact.type,
            "title": artifact.title,
            "runId": artifact.run_id,
            **({"sourceToolId": source_tool_id} if source_tool_id else {}),
            "content": text,
            "offset": offset,
            "limit": effective_limit,
            "totalChars": len(body),
            "truncated": truncated,
            **({"nextOffset": next_offset} if truncated else {}),
            "target": artifact.artifact_id,
            "workspaceRoot": str(context.session_workspace_root),
            "accessAction": "read",
            "policyDecision": "allowed",
            "policySummary": "Read a persisted artifact of this session.",
        },
    )


HANDLERS = {
    "artifact.read": read_artifact,
    "artifact.create": create_artifact,
}
