"""Persist the canonical tool event shape without revalidating internal results."""

_OPTIONAL_FIELDS = (
    "callId", "error", "artifactId", "target", "workspaceRoot", "scope",
    "accessAction", "policyDecision", "policySummary",
)
_PREVIEW_FIELDS = ("arguments", "argumentsTruncated", "preview")


def normalize_tool_step(tool_payload: dict) -> dict:
    """Project an event from ToolExecutionResult.to_event_payload into a run row."""
    step = {
        "toolId": tool_payload["toolId"],
        "channel": tool_payload.get("channel", "tool"),
        "ok": tool_payload["ok"],
        "summary": tool_payload["summary"],
        **{key: tool_payload.get(key) for key in _OPTIONAL_FIELDS},
        "status": "blocked" if tool_payload["ok"] is False else "ok",
        "batched": tool_payload.get("channel") == "batch" or tool_payload["toolId"] == "tool.batch",
        "members": [dict(member) for member in tool_payload.get("members", [])],
    }
    for key in _PREVIEW_FIELDS:
        if key in tool_payload:
            step[key] = dict(tool_payload[key])
    return step
