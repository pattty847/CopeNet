"""Plan / TODO tool — the model maintains a step-by-step task checklist.

Like Claude Code's TodoWrite: for any multi-step task the model lays out the
steps, then re-calls plan.write to flip them in_progress → completed as it goes.
The harness surfaces the latest plan as a live checklist in the chat so the
operator can watch the agent work the plan and never lose the thread.
"""

from __future__ import annotations

from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

_VALID_STATUS = {"pending", "in_progress", "completed"}


async def write_plan(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    raw_items = request.arguments.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("items is required (a non-empty list of {content, status})")
    items: list[dict[str, str]] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        status = str(entry.get("status") or "pending").strip().lower()
        if status not in _VALID_STATUS:
            status = "pending"
        items.append({"content": content, "status": status})
    if not items:
        raise ValueError("items must contain at least one {content, status}")

    completed = sum(1 for item in items if item["status"] == "completed")
    active = next((item["content"] for item in items if item["status"] == "in_progress"), None)
    summary = f"Plan: {completed}/{len(items)} done" + (f" — now: {active}" if active else "")
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output={"items": items, "total": len(items), "completed": completed},
    )


DESCRIPTORS = [
    ToolDescriptor(
        id="plan.write",
        name="Write Plan",
        description=(
            "Record or update your step-by-step plan as a checklist. Use this for any non-trivial, "
            "multi-step task (roughly 3+ steps): lay out the steps first, then call it again to update "
            "statuses as you go. Send the FULL current plan each time (not a delta). Each item is "
            "{content, status} where status is 'pending', 'in_progress', or 'completed'. Keep exactly ONE "
            "item 'in_progress' at a time, and mark an item 'completed' as soon as it is actually done. "
            "Skip this for trivial single-step requests."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "The full current plan — send the whole ordered list every time.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        },
                        "required": ["content", "status"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["items"],
            "additionalProperties": False,
        },
        capabilities=["planning"],
        evidence_role="context",
        side_effect="none",
    ),
]

HANDLERS = {"plan.write": write_plan}
