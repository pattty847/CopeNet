"""Working-set assembly for stateful CopeNet runs."""

from __future__ import annotations

from dataclasses import dataclass

from copenet.core.runtime import ArtifactStore
from copenet.core.sessions import SessionStateRecord


RECENT_TRANSCRIPT_LIMIT = 6
ARTIFACT_BODY_LIMIT = 2400


@dataclass(frozen=True)
class WorkingSetPackage:
    """Prompt-ready working set plus structured metadata."""

    prompt: str
    metadata: dict


def assemble_working_set(
    *,
    user_message: str,
    session_state: SessionStateRecord,
    transcript_window: list[dict],
    artifact_store: ArtifactStore,
    system_prompt: str | None,
    session_key: str,
) -> WorkingSetPackage:
    """Build a compact prompt package from active runtime state."""
    recent = transcript_window[-RECENT_TRANSCRIPT_LIMIT:]
    artifacts = [
        artifact_store.get(session_key, artifact_id)
        for artifact_id in session_state.relevant_artifact_ids[-4:]
    ]
    artifact_rows = [artifact for artifact in artifacts if artifact is not None]

    sections: list[str] = []
    if session_state.task_summary:
        sections.append(f"Current task summary:\n{session_state.task_summary}")
    if session_state.goals:
        sections.append("Goals:\n" + "\n".join(f"- {goal}" for goal in session_state.goals))
    if session_state.active_entities:
        sections.append(
            "Active entities:\n" + ", ".join(session_state.active_entities)
        )
    if session_state.constraints:
        sections.append(
            "Constraints:\n" + "\n".join(f"- {item}" for item in session_state.constraints)
        )
    if session_state.unresolved_questions:
        sections.append(
            "Unresolved questions:\n"
            + "\n".join(f"- {item}" for item in session_state.unresolved_questions)
        )
    if session_state.prior_decisions:
        sections.append(
            "Prior decisions:\n" + "\n".join(f"- {item}" for item in session_state.prior_decisions[-5:])
        )
    if session_state.relevant_asset_ids:
        sections.append(
            "Referenced asset ids:\n" + ", ".join(session_state.relevant_asset_ids[-5:])
        )
    if artifact_rows:
        sections.append(
            "Relevant artifacts:\n"
            + "\n\n".join(
                f"[{artifact.type}] {artifact.title}\n{artifact.body[:ARTIFACT_BODY_LIMIT]}"
                for artifact in artifact_rows
            )
        )
    if recent:
        transcript_rows = []
        for row in recent:
            role = str(row.get("role") or "unknown")
            content = str(row.get("content") or "").strip()
            if content:
                transcript_rows.append(f"{role}: {content}")
        if transcript_rows:
            sections.append("Recent relevant transcript:\n" + "\n".join(transcript_rows))

    sections.append(f"Current user request:\n{user_message.strip()}")
    prompt = "\n\n".join(section for section in sections if section.strip())
    metadata = {
        "systemPromptPresent": bool(system_prompt and system_prompt.strip()),
        "recentTranscriptCount": len(recent),
        "artifactIds": [artifact.artifact_id for artifact in artifact_rows],
        "assetIds": list(session_state.relevant_asset_ids),
        "workingSetRefs": list(session_state.working_set_refs),
    }
    return WorkingSetPackage(prompt=prompt, metadata=metadata)
