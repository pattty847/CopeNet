"""Memory read/write tools for user-visible continuity."""

from __future__ import annotations

from copenet.core.memory import MemoryCategory

from ..contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

_ALLOWED_CATEGORIES: set[MemoryCategory] = {
    "preference",
    "project_convention",
    "ongoing_priority",
    "fact",
    "market_thesis",
}

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
        name="Remember (propose memory)",
        description=(
            "Propose a durable memory about the operator or this work. Use when the operator says to "
            "remember something, or when you learn a lasting preference, convention, priority, or fact "
            "worth carrying into future sessions. This proposes a DRAFT — it is NOT used until the "
            "operator approves it in the Memory surface, so propose freely but don't claim it's saved.\n"
            "Categories: preference (how they like things), project_convention (a rule for this codebase), "
            "ongoing_priority (a current goal), fact (a stable fact about them or their setup), "
            "market_thesis (why the operator holds or watches a specific ticker, and what would prove "
            "that reasoning wrong).\n"
            "For market_thesis: title '<SYMBOL> thesis', tags MUST include 'symbol:<SYMBOL>' (uppercase) "
            "so market.ticker can surface it automatically on future mentions, summary is the one-line "
            "thesis, and detail should cover why you hold/watch it and what would change your mind — for "
            "example: 'Why: <reasons>. Invalidated if: <conditions>. Add zone: <price/condition>. Trim "
            "zone: <price/condition>.' Only propose one when there's a real signal this ticker matters: "
            "market.ticker's intelligence.portfolio is non-null (it's held), intelligence.assetRole is "
            "'holding'/'watch'/'spec' (it's on the tracked list), or the operator states their own "
            "reasoning for it out loud. Do NOT draft a thesis for a random one-off ticker mention with "
            "none of those signals — that's noise in the operator's memory queue, not continuity.\n"
            "Keep title short, summary one clear sentence, extra nuance in detail. Never propose secrets, "
            "credentials, or sensitive personal data."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": sorted(_ALLOWED_CATEGORIES)},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "detail": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            },
            "required": ["category", "summary"],
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
    summary = str(request.arguments.get("summary") or "").strip()
    if not summary:
        raise ToolBlockedError(
            "memory.write requires a summary",
            access_action="write",
            policy_summary="A memory needs at least a one-sentence summary.",
        )
    title = str(request.arguments.get("title") or "").strip() or summary[:80]
    detail = str(request.arguments.get("detail") or "").strip() or None
    tags_arg = request.arguments.get("tags")
    tags = [str(item).strip() for item in tags_arg] if isinstance(tags_arg, list) else []
    # Draft-first: the model proposes, the operator approves in the Memory surface.
    record = service.propose_memory(
        category=category,
        title=title,
        summary=summary,
        detail=detail,
        tags=[tag for tag in tags if tag],
        last_session_key=context.session_key,
    )
    return ToolExecutionResult(
        tool_id="memory.write",
        ok=True,
        summary=f"Proposed a memory draft: “{record.title}” — awaiting your approval.",
        output={
            "item": record.to_public_dict(),
            "workspaceRoot": str(context.session_workspace_root),
            "scope": "identity_memory",
            "accessAction": "write",
            "policyDecision": "allowed",
            "policySummary": "Drafted a memory. It won't be used until you approve it in the Memory surface.",
        },
    )


HANDLERS = {
    "memory.read": handle_memory_read,
    "memory.write": handle_memory_write,
}
