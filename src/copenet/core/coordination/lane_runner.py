"""Isolated, tool-enabled provider lane turns.

The shared mechanism behind Fleet's dual-model rooms and Research Lab's
dual-analyst stages: a hidden session per participant, a reveal-barrier cursor
filter so a lane only sees committed peer content after its own turn, and a
single-turn executor that runs the normal harness tool loop via
`orchestrator.send_chat`.

This module owns none of Fleet's room semantics (single-active-room
enforcement, room event persistence, operator `@mention` targeting) and none
of Research Lab's stage sequencing (bounded supplement rounds, synthesis).
Callers own their own commit/persistence story; this module only runs one
lane's turn and tells the caller what happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LaneTurnSpec:
    """One lane's single-turn request. `idempotency_key` is optional so
    existing callers (Fleet) that don't pass one keep today's behavior."""

    session_key: str
    provider: str
    model: str | None
    prompt: str
    system_prompt_id: str = "default"
    task_prompt_id: str = "none"
    persona_privacy_tier: str = "private"
    idempotency_key: str | None = None


def select_lane_updates(
    events: list[dict[str, Any]], *, cursor: int, participant_id: str
) -> tuple[list[dict[str, Any]], int]:
    """Reveal-barrier filter: committed events after `cursor`, excluding this
    participant's own. This is the isolation mechanism itself — a lane never
    sees a peer's in-progress work, only what's already committed, and never
    sees its own prior turns played back to it as "peer" content."""
    delivered_through = max((int(event.get("seq") or 0) for event in events), default=cursor)
    updates = [
        event
        for event in events
        if int(event.get("seq") or 0) > cursor and event.get("author") != participant_id
    ]
    return updates, delivered_through


def render_event_block(events: list[dict[str, Any]]) -> str:
    """Turn a list of committed events into a plain-text block a lane can read.

    Callers wrap this in their own framing (Fleet's room-participant framing,
    Research Lab's evidence-snapshot framing, etc.) — this only handles the
    event-list -> text shape, not the intro/outro copy around it.
    """
    lines: list[str] = []
    for event in events:
        lines.extend(
            [
                f"--- event {event.get('seq')} ---",
                f"Author: {event.get('author')}",
                f"Kind: {event.get('kind')}",
                "Content:",
                str(event.get("content") or ""),
            ]
        )
    return "\n".join(lines)


def create_lane_sessions(
    orchestrator: Any,
    *,
    parent_key: str,
    session_type: str,
    title_prefix: str,
    participant_specs: dict[str, dict[str, Any]],
    workspace_root: str | None,
) -> dict[str, dict[str, Any]]:
    """Create one hidden lane session per participant; roll back all of them
    if any single creation fails partway through.

    `session_type` is the caller's hidden-type tag (e.g. "fleet_lane",
    "research_lane") — `SessionStore.list_sessions()` must already exclude it
    or the lane will leak into normal session listings.
    """
    participants: dict[str, dict[str, Any]] = {}
    created_lane_keys: list[str] = []
    try:
        for participant_id, spec in participant_specs.items():
            lane_key = f"{parent_key}-lane-{participant_id}"
            lane = orchestrator._session_store.create_session(
                session_key=lane_key,
                provider=spec["provider"],
                model=spec.get("model"),
                title=f"{title_prefix} · {participant_id}",
                system_prompt_id="default",
                task_prompt_id="none",
                persona_id="default",
                persona_privacy_tier="private",
                workspace_root=workspace_root,
                session_type=session_type,
                parent_session_key=parent_key,
                participant_id=participant_id,
            )
            created_lane_keys.append(lane.session_key)
            participants[participant_id] = {
                "participantId": participant_id,
                "provider": lane.provider,
                "model": lane.model,
                "laneSessionKey": lane.session_key,
            }
        return participants
    except Exception:
        # Session history is append-only, so failed setup lanes are retained
        # but archived rather than deleted or left visible as live work.
        for lane_key in created_lane_keys:
            orchestrator._session_store.set_archived(lane_key, True)
        raise


async def run_lane_turn(orchestrator: Any, spec: LaneTurnSpec) -> dict[str, Any]:
    """Run one lane's turn through the normal harness tool loop and collect
    its final text, run id, and tool receipts.

    No tool-call ceiling is enforced here — the harness's own MAX_TOOL_STEPS
    is the hard backstop. Callers with a soft budget (e.g. Research Lab's
    gathering lane) check the returned `toolCallCount` against their own
    target and log accordingly; V1 is a soft guard, not a hard cap.
    """
    from copenet.core.orchestrator.requests import ChatSendRequest

    lane = orchestrator._session_store.get(spec.session_key)
    text_chunks: list[str] = []
    final_text = ""
    tool_receipts: list[dict[str, Any]] = []
    tool_call_count = 0
    error_message: str | None = None

    async def capture(payload: dict[str, Any]) -> None:
        nonlocal final_text, tool_call_count, error_message
        state = payload.get("state")
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        content = str(message.get("content") or "")
        if state == "delta" and content:
            text_chunks.append(content)
        if state == "final" and content:
            final_text = content
        if state == "error":
            error_message = str(payload.get("errorMessage") or payload.get("error") or "unknown error")
        if state == "tool_result":
            tool_call_count += 1
            tool = payload.get("toolExecution") if isinstance(payload.get("toolExecution"), dict) else {}
            tool_receipts.append(
                {
                    "toolId": tool.get("toolId"),
                    "ok": tool.get("ok") is not False,
                    "summary": tool.get("summary"),
                    "preview": tool.get("preview"),
                }
            )

    result = await orchestrator.send_chat(
        ChatSendRequest(
            session_key=spec.session_key,
            message=spec.prompt,
            provider=spec.provider,
            model=spec.model,
            system_prompt_id=spec.system_prompt_id,
            task_prompt_id=spec.task_prompt_id,
            persona_id="default",
            persona_privacy_tier=spec.persona_privacy_tier,
            workspace_root=lane.workspace_root if lane is not None else None,
            idempotency_key=spec.idempotency_key,
        ),
        emit=capture,
    )
    if error_message:
        raise RuntimeError(f"lane {spec.session_key} failed: {error_message}")

    # The full raw tool output (url/title/text/wordCount for web.fetch, etc.)
    # never reaches the streaming `emit` callback — runtime.py reads it
    # internally (event.metadata["toolResult"]) but only persists it onto the
    # completed RunRecord, never re-emits it. `toolExecution`/receipts above
    # are deliberately lightweight (no body). So full bodies are read back
    # from the durable run record after send_chat returns, not captured live.
    tool_results: list[dict[str, Any]] = []
    run_id = result.get("runId")
    if run_id:
        run_record = orchestrator._run_store.get(spec.session_key, str(run_id))
        if run_record is not None:
            tool_results = list(run_record.tool_results)

    content = final_text or "".join(text_chunks).strip()
    if not content:
        raise RuntimeError(f"lane {spec.session_key} returned no assistant content")
    return {
        "content": content,
        "runId": run_id,
        "toolReceipts": tool_receipts,
        "toolResults": tool_results,
        "toolCallCount": tool_call_count,
    }
