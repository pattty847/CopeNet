"""user.remember — propose a durable USER.md identity delta for operator review.

Distinct from memory.write: memory holds granular work facts/preferences; USER.md is
the operator's narrative identity. The model proposes a section delta as a DRAFT; the
operator approves it (merged into USER.md) or discards it. Capped per day so the model
picks real deltas, not append-spam.
"""

from __future__ import annotations

from copenet.core.user_notes import UserNoteLimitReached

from ..contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

DESCRIPTORS = [
    ToolDescriptor(
        id="user.remember",
        name="Remember about the operator (propose USER.md edit)",
        description=(
            "Propose a durable, identity-level update to the operator's USER.md — who they are, what they're "
            "building, hard preferences, lasting constraints. Use this ONLY when you learn something stable that "
            "is absent from or contradicts USER.md; not for session trivia, and not for work conventions (use "
            "memory.write for those). This proposes a DRAFT — it is NOT written until the operator approves it, so "
            "propose freely but don't claim it's saved. There is a small daily limit, so pick the real deltas.\n"
            "- target_section: the USER.md '## ' section to update (e.g. 'Summary', 'Projects', 'Preferences'). "
            "Accumulate detail in body sections; only target 'Summary' when something belongs in every-turn "
            "context.\n"
            "- summary: one line for the operator on what/why you're proposing.\n"
            "- body: the markdown that should become that section's content (approval replaces the section).\n"
            "Never propose secrets, credentials, or sensitive personal data."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "target_section": {"type": "string"},
                "summary": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["target_section", "summary", "body"],
            "additionalProperties": False,
        },
        safety_level="guarded",
        capabilities=["continuity", "identity"],
        evidence_role="context",
        side_effect="write",
    ),
]


async def handle_user_remember(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    service = context.user_notes_service
    if service is None:
        raise ToolBlockedError(
            "user notes service unavailable",
            access_action="write",
            policy_summary="USER.md proposals are not configured for this session.",
        )
    target_section = str(request.arguments.get("target_section") or "").strip()
    summary = str(request.arguments.get("summary") or "").strip()
    body = str(request.arguments.get("body") or "").strip()
    if not target_section:
        raise ToolBlockedError(
            "user.remember requires a target_section",
            access_action="write",
            policy_summary="Name the USER.md section this delta belongs to.",
        )
    if not body:
        raise ToolBlockedError(
            "user.remember requires a body",
            access_action="write",
            policy_summary="A USER.md proposal needs the markdown body to merge.",
        )
    try:
        record = service.propose_user_note(
            target_section=target_section,
            summary=summary,
            body=body,
            last_session_key=context.session_key,
        )
    except UserNoteLimitReached as exc:
        raise ToolBlockedError(
            f"{exc} — ask the operator to raise it or try tomorrow.",
            access_action="write",
            policy_summary="Daily USER.md proposal limit reached; pick the most important delta.",
        )
    return ToolExecutionResult(
        tool_id="user.remember",
        ok=True,
        summary=f"Proposed a USER.md update to “{record.target_section}” — awaiting your approval.",
        output={
            "proposal": record.to_public_dict(),
            "scope": "operator_identity",
            "accessAction": "write",
            "policyDecision": "allowed",
            "policySummary": "Drafted a USER.md update. It won't be written until you approve it in Persona Home.",
        },
    )


HANDLERS = {
    "user.remember": handle_user_remember,
}
