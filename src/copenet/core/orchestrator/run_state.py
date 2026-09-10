"""Derive durable session state and run context metadata."""

from __future__ import annotations

from typing import Any

from copenet.core.sessions import SessionStateRecord
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tools import (
    describe_available_tools,
)


def _evolve_session_state(
    *,
    session_state: SessionStateRecord,
    run_id: str,
    plan,
    task_prompt_id: str | None,
    created_artifact_ids: list[str],
) -> SessionStateRecord:
    """Update durable session state after a run.

    Phase 1 (HARNESS_REBUILD_V2) killed the keyword auto-mutation that used to
    synthesize task_summary / goals / active_entities / unresolved_questions /
    prior_decisions / topical_tags from conversation text. The transcript IS the
    context now (replayed via build_chat_messages), so we only track concrete
    artifact references plus a plan snapshot for the inspector.

    The remaining SessionStateRecord text fields are preserved as-is (not
    narrowed away yet) so Pulse / Merge — which still read and write them and
    are scheduled for a later rewire per the plan's deferral list — keep working
    and degrade gracefully rather than crashing on a removed attribute.
    """
    relevant_artifact_ids = _append_unique(
        session_state.relevant_artifact_ids,
        created_artifact_ids,
    )[-10:]
    agent_runtime = _build_agent_runtime_payload(
        session_key=session_state.session_key,
        task_prompt_id=task_prompt_id,
        session_state=session_state,
    )
    return SessionStateRecord(
        session_key=session_state.session_key,
        task_summary=session_state.task_summary,
        goals=list(session_state.goals),
        active_entities=list(session_state.active_entities),
        working_set_refs=list(session_state.working_set_refs),
        constraints=list(session_state.constraints),
        unresolved_questions=list(session_state.unresolved_questions),
        prior_decisions=list(session_state.prior_decisions),
        starter_intent=session_state.starter_intent,
        topical_tags=list(session_state.topical_tags),
        plan_snapshot={
            "runId": run_id,
            "toolExecutionMode": plan.tool_execution_mode,
            "willAttemptToolLoop": plan.will_attempt_tool_loop,
            "taskPromptId": task_prompt_id,
            **agent_runtime,
            "toolManifest": describe_available_tools(plan.tools),
        },
        relevant_asset_ids=list(session_state.relevant_asset_ids),
        relevant_artifact_ids=relevant_artifact_ids,
        merge_state=dict(session_state.merge_state),
        pulse_state=dict(session_state.pulse_state),
        created_at=session_state.created_at,
        updated_at=transcript_now(),
    )


def _append_unique(existing: list[str], incoming: list[str]) -> list[str]:
    rows = list(existing)
    for item in incoming:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _build_tool_visibility_summary(tools: list[Any]) -> dict[str, list[str]]:
    visible = [str(tool.id) for tool in tools]
    auto_allowed = [
        str(tool.id) for tool in tools if getattr(tool, "manifest_permission", lambda: "")() == "auto_allowed"
    ]
    policy_gated = [
        str(tool.id) for tool in tools if getattr(tool, "manifest_permission", lambda: "")() == "policy_gated"
    ]
    return {
        "visibleToolIds": visible,
        "autoAllowedToolIds": auto_allowed,
        "policyGatedToolIds": policy_gated,
    }


def _build_agent_runtime_payload(
    *,
    session_key: str,
    task_prompt_id: str | None,
    session_state: SessionStateRecord,
) -> dict[str, object]:
    raw_tasks = (
        session_state.plan_snapshot.get("delegatedTasks")
        if isinstance(session_state.plan_snapshot, dict)
        else []
    )
    delegated_tasks = [dict(item) for item in raw_tasks] if isinstance(raw_tasks, list) else []
    permission_mode = (
        "workspace_write" if (task_prompt_id or "").strip().lower() == "full-access" else "read_only"
    )
    return {
        "agentId": f"lead:{session_key}",
        "parentAgentId": None,
        "agentRole": "lead",
        "permissionMode": permission_mode,
        "planModeRequired": False,
        "delegatedTasks": delegated_tasks,
    }
