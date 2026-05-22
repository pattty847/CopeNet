"""Memory read/write tools for user-visible continuity."""

from __future__ import annotations

from copenet.core.memory import MemoryCategory

from ..contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

_ALLOWED_CATEGORIES: set[MemoryCategory] = {"preference", "project_convention", "ongoing_priority", "fact"}

DESCRIPTORS = [
    ToolDescriptor(
        id="memory.read",
        name="Read Memory",
        description="Read user-visible memory items by query or category so the assistant can recall preferences, conventions, priorities, and durable facts.",
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string", "enum": sorted(_ALLOWED_CATEGORIES)},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                "include_archived": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        capabilities=["continuity", "preferences", "identity"],
        evidence_role="context",
        side_effect="read",
    ),
    ToolDescriptor(
        id="memory.write",
        name="Write Memory",
        description="Create or update one user-visible memory item when a durable low-risk preference, convention, priority, or fact should be remembered.",
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "category": {"type": "string", "enum": sorted(_ALLOWED_CATEGORIES)},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "detail": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            },
            "required": ["category", "title", "summary"],
            "additionalProperties": False,
        },
        safety_level="guarded",
        capabilities=["continuity", "preferences", "identity"],
        evidence_role="context",
        side_effect="write",
    ),
]


async def handle_memory_read(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.memory_service
    if service is None:
        raise ToolBlockedError(
            "memory service unavailable",
            access_action="read",
            policy_summary="Memory service is not configured for this session.",
        )
    category = str(request.arguments.get("category") or "").strip() or None
    query = str(request.arguments.get("query") or "").strip()
    limit = int(request.arguments.get("limit") or 5)
    include_archived = bool(request.arguments.get("include_archived"))
    if query:
        rows = service.select_relevant(query=query, limit=max(1, min(limit, 10)))
        if category:
            rows = [item for item in rows if item.category == category]
    else:
        rows = service.list_memory(
            include_archived=include_archived,
            category=category if category in _ALLOWED_CATEGORIES else None,
            limit=max(1, min(limit, 10)),
        )
    return ToolExecutionResult(
        tool_id="memory.read",
        ok=True,
        summary=f"Loaded {len(rows)} memory item{'s' if len(rows) != 1 else ''}.",
        output={
            "items": [item.to_public_dict() for item in rows],
            "count": len(rows),
            "query": query or None,
            "category": category,
            "workspaceRoot": str(context.session_workspace_root),
            "scope": "identity_memory",
            "accessAction": "read",
            "policyDecision": "allowed",
            "policySummary": "Memory is a user-visible continuity layer.",
        },
    )


async def handle_memory_write(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.memory_service
    if service is None:
        raise ToolBlockedError(
            "memory service unavailable",
            access_action="write",
            policy_summary="Memory service is not configured for this session.",
        )
    category = str(request.arguments.get("category") or "").strip()
    if category not in _ALLOWED_CATEGORIES:
        raise ToolBlockedError(
            "memory category must be one of preference, project_convention, ongoing_priority, fact",
            access_action="write",
            policy_summary="Only known memory categories are allowed.",
        )
    title = str(request.arguments.get("title") or "").strip()
    summary = str(request.arguments.get("summary") or "").strip()
    if not title or not summary:
        raise ToolBlockedError(
            "memory.write requires title and summary",
            access_action="write",
            policy_summary="Memory writes must include a concise title and summary.",
        )
    detail = str(request.arguments.get("detail") or "").strip() or None
    tags_arg = request.arguments.get("tags")
    tags = [str(item).strip() for item in tags_arg] if isinstance(tags_arg, list) else []
    record = service.upsert_memory(
        memory_id=str(request.arguments.get("id") or "").strip() or None,
        category=category,
        title=title,
        summary=summary,
        detail=detail,
        tags=[tag for tag in tags if tag],
        source="tool_call",
        confidence=0.85,
        last_session_key=context.session_key,
    )
    return ToolExecutionResult(
        tool_id="memory.write",
        ok=True,
        summary=f"Saved memory: {record.title}.",
        output={
            "item": record.to_public_dict(),
            "workspaceRoot": str(context.session_workspace_root),
            "scope": "identity_memory",
            "accessAction": "write",
            "policyDecision": "allowed",
            "policySummary": "Memory writes stay user-visible and editable.",
        },
    )


HANDLERS = {
    "memory.read": handle_memory_read,
    "memory.write": handle_memory_write,
}
