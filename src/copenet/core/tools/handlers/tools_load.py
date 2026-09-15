"""tools.load — bring a deferred tool into the turn (and the session)."""

from __future__ import annotations

from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

DEFERRED_TOOLS_KEY = "deferred_tools"  # ephemeral: id -> ToolDescriptor the model may load
LOADED_TOOL_IDS_KEY = "loaded_tool_ids"  # ephemeral: ids loaded so far this turn, in order


async def load_tools(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    raw = request.arguments.get("tool_ids")
    if isinstance(raw, str):
        raw = [part for part in raw.replace(",", " ").split() if part]
    if not isinstance(raw, list) or not raw:
        raise ValueError("tool_ids is required (a non-empty list of tool ids from the deferred catalog)")
    requested: list[str] = []
    for item in raw:
        tool_id = str(item or "").strip()
        if tool_id and tool_id not in requested:
            requested.append(tool_id)

    deferred: dict[str, ToolDescriptor] = context.ephemeral.get(DEFERRED_TOOLS_KEY) or {}
    loaded: list[str] = context.ephemeral.setdefault(LOADED_TOOL_IDS_KEY, [])
    available_now = {tool.id for tool in context.available_tools} | set(loaded)

    newly = [tool_id for tool_id in requested if tool_id in deferred and tool_id not in loaded]
    already = [tool_id for tool_id in requested if tool_id in available_now]
    unknown = [tool_id for tool_id in requested if tool_id not in deferred and tool_id not in available_now]
    loaded.extend(newly)

    if newly and context.session_state_store is not None and context.session_key:
        # Sticky for the session: the next turn starts with these loaded. Finalization
        # writes the same union, so an aborted run still keeps what it loaded.
        record = context.session_state_store.get_or_create(context.session_key)
        merged = [tool_id for tool_id in record.loaded_tool_ids] + [t for t in newly if t not in record.loaded_tool_ids]
        if merged != record.loaded_tool_ids:
            record.loaded_tool_ids = merged
            context.session_state_store.save(record)

    if context.trace is not None and newly:
        context.trace("tools_loaded", {"toolIds": list(newly), "sessionLoadedCount": len(loaded)})

    if not newly and unknown and not already:
        catalog = ", ".join(sorted(deferred)) or "(nothing is deferred in this session)"
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"No such deferred tool: {', '.join(unknown)}.",
            error=f"unknown tool id(s): {', '.join(unknown)}. Loadable ids: {catalog}",
            output={"loaded": [], "alreadyAvailable": [], "unknown": unknown, "loadable": sorted(deferred)},
        )
    parts = []
    if newly:
        parts.append(f"Loaded {', '.join(newly)}; available from your next step and for the rest of this session.")
    if already:
        parts.append(f"Already available: {', '.join(already)}.")
    if unknown:
        parts.append(f"Unknown: {', '.join(unknown)}.")
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=" ".join(parts),
        output={"loaded": newly, "alreadyAvailable": already, "unknown": unknown},
    )


DESCRIPTORS = [
    ToolDescriptor(
        id="tools.load",
        name="Load Tools",
        description=(
            "Load one or more deferred tools listed in the <deferred_tools> catalog so you can call them. "
            "Loaded tools are usable from your next step and stay loaded for the rest of this session. "
            "Pass the exact ids from the catalog."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "tool_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact tool ids from the deferred catalog, e.g. [\"market.ticker\"].",
                },
            },
            "required": ["tool_ids"],
        },
        capabilities=["context"],
        evidence_role="none",
        side_effect="none",
    ),
]

HANDLERS = {"tools.load": load_tools}
