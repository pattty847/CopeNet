"""Task contracts and final-answer gating for the CopeNet harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from copenet.core.tools import FinalCandidateEnvelope

TaskKind = Literal[
    "repo_explore",
    "repo_explain",
    "patch_plan",
    "patch_apply_verify",
    "repo_edit",
    "artifact_workflow",
]


@dataclass(frozen=True)
class TaskContract:
    """Small generic controller contract for one harness turn."""

    goal: str
    task_kind: TaskKind
    allowed_tools: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    done_conditions: list[str] = field(default_factory=list)
    preferred_next_actions: list[str] = field(default_factory=list)
    final_answer_rules: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "taskKind": self.task_kind,
            "allowedTools": list(self.allowed_tools),
            "requiredEvidence": list(self.required_evidence),
            "doneConditions": list(self.done_conditions),
            "preferredNextActions": list(self.preferred_next_actions),
            "finalAnswerRules": list(self.final_answer_rules),
        }


@dataclass(frozen=True)
class FinalGateDecision:
    ok: bool
    missing_requirements: list[str] = field(default_factory=list)
    recommended_next_action_type: str | None = None
    reason_code: str | None = None


def final_gate_evaluate(
    *,
    contract: TaskContract | dict[str, Any],
    turn_state: Any,
    candidate: FinalCandidateEnvelope,
) -> FinalGateDecision:
    if isinstance(contract, TaskContract):
        task_kind = contract.task_kind
        done_conditions = contract.done_conditions
    else:
        task_kind = str(contract.get("taskKind") or contract.get("task_kind") or "repo_explore").strip() or "repo_explore"
        done_conditions = list(contract.get("doneConditions") or contract.get("done_conditions") or [])

    ledger = getattr(turn_state, "evidence_ledger", {}) or {}
    visited_tools = list(ledger.get("visitedTools") or [])
    visited_paths = list(ledger.get("visitedPaths") or [])
    grounding_actions = list(ledger.get("groundingActions") or [])
    evidence_items = list(ledger.get("evidenceItems") or [])
    has_grounding = bool(grounding_actions)
    has_directional = any(item.get("category") == "directional" for item in evidence_items)
    has_contextual = any(item.get("category") == "contextual" for item in evidence_items)
    shallow_reconnaissance_count = sum(
        1 for item in evidence_items if item.get("category") in {"reconnaissance", "contextual"}
    )
    has_patch = any(tool_id in {"patch.apply", "files.edit", "files.write"} for tool_id in visited_tools)
    has_verification = any(tool_id in {"test.run", "shell.exec", "git.diff"} for tool_id in visited_tools)
    has_artifact = any(tool_id == "artifact.create" for tool_id in visited_tools)

    candidate_answer = candidate.answer.strip()
    candidate_evidence = list(candidate.evidence)
    candidate_done = list(candidate.done_conditions_met)

    missing: list[str] = []
    reason_code: str | None = None
    next_action = "files.read"

    if not candidate_answer:
        missing.append("non-empty final answer")
        reason_code = "empty_final_answer"

    if task_kind in {"repo_explore", "repo_explain", "patch_plan", "patch_apply_verify", "repo_edit", "artifact_workflow"} and not candidate_evidence:
        missing.append("grounded evidence list")

    unknown_paths = [path for path in candidate_evidence if path not in visited_paths]
    if unknown_paths:
        missing.append("evidence references visited paths only")
        reason_code = reason_code or "unknown_evidence_path"

    unsupported_done_conditions = [condition for condition in candidate_done if condition not in done_conditions]
    if unsupported_done_conditions:
        missing.append("done conditions must be drawn from the active contract")
        reason_code = reason_code or "unsupported_done_condition"

    supported_done = set(done_conditions)
    if "grounded evidence" in supported_done and not has_grounding:
        missing.append("grounded evidence")
        reason_code = reason_code or "missing_grounding"
    if "file path citation" in supported_done and not candidate_evidence and has_grounding:
        missing.append("file path citation")
        reason_code = reason_code or "missing_path_citation"
    if "patch applied" in supported_done and not has_patch:
        missing.append("patch applied")
        reason_code = reason_code or "missing_patch_evidence"
        next_action = "patch.apply"
    if "verification run" in supported_done and not has_verification:
        missing.append("verification run")
        reason_code = reason_code or "missing_verification"
        next_action = "shell.exec"
    if "artifact created" in supported_done and not has_artifact:
        missing.append("artifact created")
        reason_code = reason_code or "missing_artifact"
        next_action = "artifact.create"

    if task_kind == "repo_explore":
        if not has_grounding:
            missing.append("grounded file evidence")
            reason_code = reason_code or (
                "reconnaissance_saturation"
                if shallow_reconnaissance_count >= 2
                else ("contextual_only_evidence" if has_contextual else "missing_grounding")
            )
            next_action = "files.read" if visited_paths else "files.search"
    elif task_kind == "repo_explain":
        if not has_grounding:
            missing.append("grounded file evidence")
            reason_code = reason_code or (
                "reconnaissance_saturation"
                if shallow_reconnaissance_count >= 2
                else ("contextual_only_evidence" if has_contextual else "missing_file_evidence")
            )
            next_action = "files.read" if visited_paths else "files.search"
        elif not candidate_evidence:
            missing.append("file path citation")
            reason_code = reason_code or "finalized_before_threshold"
            next_action = "files.read"
    elif task_kind == "patch_plan":
        if not has_grounding:
            missing.append("grounded file evidence tied to the patch plan")
            if shallow_reconnaissance_count >= 2:
                reason_code = reason_code or "reconnaissance_saturation"
                next_action = "files.read" if visited_paths else "files.search"
            else:
                reason_code = reason_code or ("contextual_only_evidence" if has_contextual else "missing_patch_evidence")
                next_action = "files.read" if has_directional else "files.search"
        elif not candidate_evidence:
            missing.append("file path citation")
            reason_code = reason_code or "finalized_before_threshold"
            next_action = "files.read"
    elif task_kind == "patch_apply_verify":
        if not has_grounding:
            missing.append("grounded file evidence")
            reason_code = reason_code or ("contextual_only_evidence" if has_contextual else "missing_grounding")
            next_action = "files.read"
        elif not has_patch:
            missing.append("patch applied")
            reason_code = reason_code or "missing_patch_evidence"
            next_action = "files.edit"
        elif not has_verification:
            missing.append("verification run")
            reason_code = reason_code or "missing_verification"
            next_action = "shell.exec"
    elif task_kind == "repo_edit":
        if not has_grounding:
            missing.append("grounded file evidence")
            reason_code = reason_code or ("contextual_only_evidence" if has_contextual else "missing_grounding")
            next_action = "files.read" if visited_paths else "files.search"
        elif not has_patch:
            missing.append("patch applied")
            reason_code = reason_code or "missing_patch_evidence"
            next_action = "files.edit"
    elif task_kind == "artifact_workflow":
        if not has_grounding:
            missing.append("grounded file evidence")
            reason_code = reason_code or (
                "reconnaissance_saturation"
                if shallow_reconnaissance_count >= 2
                else ("contextual_only_evidence" if has_contextual else "missing_grounding")
            )
            next_action = "files.read" if visited_paths else "files.search"
        elif not has_artifact:
            missing.append("artifact created")
            reason_code = reason_code or "missing_artifact"
            next_action = "artifact.create"

    if missing:
        deduped_missing = list(dict.fromkeys(missing))
        return FinalGateDecision(
            ok=False,
            missing_requirements=deduped_missing,
            recommended_next_action_type=next_action,
            reason_code=reason_code,
        )
    return FinalGateDecision(ok=True)
