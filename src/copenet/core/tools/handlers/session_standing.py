"""session.standing — the one line the model leaves about where the work stands.

The session list used to show a title generated once from the first exchange and
never again, so a thread that drifted carried a name from a conversation that no
longer existed. Everything else a row needs is a fact we already hold: the change
ledger has the files and the line counts, the run record has the tool counts and
the failed verification, git has the branch and whether it merged. The one thing
no fact answers is where the WORK stands, so that is the only thing we ask for.

The note becomes the row's title. It is stamped with the run that wrote it and
expires when a later run does not write one (see run_state._carry_standing),
because a stale standing line is worse than falling back to the plain title.
"""

from __future__ import annotations

from ..contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

# The row gives the title two lines before it truncates. Past this the operator reads
# an ellipsis, so cut here rather than letting a paragraph through.
STANDING_MAX_CHARS = 120

DESCRIPTORS = [
    ToolDescriptor(
        id="session.standing",
        name="Leave where the work stands",
        description=(
            "Leave one line saying where the work stands, as you would tell the operator if they walked in "
            "tomorrow having forgotten this thread. It becomes this session's title in their session list, "
            "replacing whatever was there before.\n"
            "- note: say what is true of the WORK, not what you did this turn — \"the fix is in, six tests still "
            "red on the fixture shape\" rather than \"edited fakeChart.ts and ran the suite\". If something is "
            "unresolved and only the operator can settle it, say what it is in the same line. Keep it under about "
            "90 characters, lower case, no trailing period.\n"
            "- done: set true ONLY when you believe nothing is left open. That offers the thread to the operator "
            "for closing, so leave it out while anything is pending.\n"
            "Call this once, as the last thing you do in a turn that changed anything or reached a conclusion. "
            "The file counts, tool counts, branch state and test results are already shown — do not repeat them."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "One line on where the work stands, under ~90 characters.",
                },
                "done": {
                    "type": "boolean",
                    "description": "True only when nothing is left open.",
                },
            },
            "required": ["note"],
            "additionalProperties": False,
        },
        capabilities=["context", "continuity"],
        evidence_role="none",
        side_effect="none",
    ),
]


async def leave_standing(
    request: ToolExecutionRequest, context: ToolExecutionContext
) -> ToolExecutionResult:
    """Persist the session's standing line so the session list can title the row with it."""
    store = context.session_state_store
    session_key = (context.session_key or "").strip()
    if store is None or not session_key:
        raise ToolBlockedError(
            "session state is unavailable for this run",
            access_action="write",
            policy_summary="This session cannot record a standing line.",
        )
    note = " ".join(str(request.arguments.get("note") or "").split())
    if not note:
        raise ToolBlockedError(
            "session.standing requires a note",
            access_action="write",
            policy_summary="Say where the work stands in one line.",
        )
    truncated = len(note) > STANDING_MAX_CHARS
    if truncated:
        note = note[: STANDING_MAX_CHARS - 1].rstrip() + "…"
    done = bool(request.arguments.get("done") or False)

    record = store.get_or_create(session_key)
    record.standing_note = note
    record.standing_done = done
    record.standing_run_id = context.run_id
    store.save(record)

    if context.trace is not None:
        context.trace(
            "session_standing_left",
            {"sessionKey": session_key, "chars": len(note), "done": done, "truncated": truncated},
        )

    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Left where this stands: “{note}”" + (" — offered for closing." if done else ""),
        output={"note": note, "done": done, "truncated": truncated},
    )


HANDLERS = {"session.standing": leave_standing}
