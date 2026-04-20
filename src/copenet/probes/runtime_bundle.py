"""Runtime probe bundle helpers for live CopeNet evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_slug(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)
    return safe.strip("._") or fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _tool_steps(run_record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(run_record, dict):
        return []
    value = run_record.get("toolSteps")
    return [dict(step) for step in value] if isinstance(value, list) else []


def _tool_ids(tool_steps: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for step in tool_steps:
        tool_id = str(step.get("toolId") or "").strip()
        if tool_id:
            rows.append(tool_id)
    return rows


def _artifact_ids(artifacts: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for artifact in artifacts:
        artifact_id = str(artifact.get("artifactId") or "").strip()
        if artifact_id:
            rows.append(artifact_id)
    return rows


def _artifact_tool_ids(artifacts: list[dict[str, Any]]) -> set[str]:
    tool_ids: set[str] = set()
    for artifact in artifacts:
        metadata = artifact.get("metadata")
        if isinstance(metadata, dict):
            raw_tool_ids = metadata.get("toolIds")
            if isinstance(raw_tool_ids, list):
                for tool_id in raw_tool_ids:
                    text = str(tool_id or "").strip()
                    if text:
                        tool_ids.add(text)
            single_tool = str(metadata.get("toolId") or "").strip()
            if single_tool:
                tool_ids.add(single_tool)
    return tool_ids


def _last_assistant_content(transcript: list[dict[str, Any]]) -> str:
    for message in reversed(transcript):
        if str(message.get("role") or "").strip() == "assistant":
            return str(message.get("content") or "")
    return ""


def _looks_like_adjacent_tool_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return bool(re.search(r'\}\s*\{\s*"tool_id"', stripped))


def _is_repo_understanding_probe(probe: ProbeSpec) -> bool:
    name = probe.name.lower()
    prompt = probe.prompt.lower()
    return any(
        needle in name or needle in prompt
        for needle in {"repo", "repository", "architecture", "setup", "inspect", "patch", "bug", "relevant files"}
    )


def _requires_file_grounding(probe: ProbeSpec) -> bool:
    name = probe.name.lower()
    prompt = probe.prompt.lower()
    return any(
        needle in name or needle in prompt
        for needle in {"architecture", "setup", "patch", "bug", "relevant files"}
    )


def _has_file_grounding_tool(tool_ids: list[str], artifacts: list[dict[str, Any]]) -> bool:
    grounding_tools = {"files.read", "files.search"}
    if grounding_tools.intersection(tool_ids):
        return True
    return bool(grounding_tools.intersection(_artifact_tool_ids(artifacts)))


def _has_any_grounding_tool(tool_ids: list[str], artifacts: list[dict[str, Any]]) -> bool:
    if "context.prepare" in tool_ids or "context.prepare" in _artifact_tool_ids(artifacts):
        return True
    return _has_file_grounding_tool(tool_ids, artifacts)


def _cites_specific_file(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"\b(?:README|AGENTS|CLAUDE|GEMINI|TODO)\.md\b", stripped):
        return True
    if re.search(r"\b[\w./-]+\.(?:py|md|ts|tsx|toml|json|yml|yaml)\b", stripped):
        return True
    return False


def render_transcript_markdown(session: dict[str, Any] | None, messages: list[dict[str, Any]]) -> str:
    """Render a simple transcript markdown export from public message rows."""
    title = "Conversation Export"
    if isinstance(session, dict):
        label = str(session.get("title") or session.get("key") or "").strip()
        if label:
            title = f"Conversation Export: {label}"

    lines = [f"# {title}", ""]
    if isinstance(session, dict):
        lines.extend(
            [
                f"- Session key: `{session.get('key')}`",
                f"- Provider: `{session.get('provider')}`",
                f"- Model: `{session.get('model')}`",
                f"- Profile: `{session.get('systemPromptId')}`",
                f"- Task mode: `{session.get('taskPromptId')}`",
                "",
            ]
        )

    for message in messages:
        role = str(message.get("role") or "assistant").upper()
        timestamp = str(message.get("timestamp") or "")
        lines.append(f"## {role}")
        if timestamp:
            lines.extend(["", f"_Timestamp: {timestamp}_", ""])
        content = str(message.get("content") or "").strip()
        lines.append(content or "_No content_")
        tool_execution = message.get("toolExecution")
        if isinstance(tool_execution, dict) and tool_execution:
            lines.extend(["", "```json", json.dumps(tool_execution, ensure_ascii=False, indent=2), "```"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ProbeSpec:
    """One runtime probe scenario."""

    name: str
    prompt: str
    expects_tools: bool = True
    session_group: str | None = None
    validate_debug_copy: bool = False


@dataclass
class ProbeBundle:
    """Captured runtime truth for one live probe run."""

    provider: str
    model: str | None
    probe_name: str
    prompt: str
    session_key: str
    run_id: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    session: dict[str, Any] | None = None
    run_record: dict[str, Any] | None = None
    session_state: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    transcript_markdown: str = ""
    trace_path: str | None = None
    raw_final_payload: dict[str, Any] | None = None
    notes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    classification: str = "unclassified"
    final_state: str = "unknown"
    tool_step_count: int = 0
    tool_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    used_batch: bool = False
    used_context_prepare: bool = False
    trace_present: bool = False
    artifact_count: int = 0
    output_preview: str = ""
    transition_reason: str = ""
    terminal_reason: str = ""
    oversized_tool_artifact_ids: list[str] = field(default_factory=list)
    bundle_dir: str | None = None
    debug_copy_validation: dict[str, Any] | None = None

    def to_summary_row(self) -> dict[str, Any]:
        """Return the stable summary row for this run."""
        return {
            "provider": self.provider,
            "model": self.model,
            "probe_name": self.probe_name,
            "prompt": self.prompt,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "classification": self.classification,
            "status": self.status,
            "final_state": self.final_state,
            "tool_step_count": self.tool_step_count,
            "tool_ids": list(self.tool_ids),
            "artifact_ids": list(self.artifact_ids),
            "trace_path": self.trace_path,
            "bundle_dir": self.bundle_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "used_batch": self.used_batch,
            "used_context_prepare": self.used_context_prepare,
            "trace_present": self.trace_present,
            "artifact_count": self.artifact_count,
            "output_preview": self.output_preview,
            "transition_reason": self.transition_reason,
            "terminal_reason": self.terminal_reason,
            "oversized_tool_artifact_ids": list(self.oversized_tool_artifact_ids),
            "debug_copy_validation": dict(self.debug_copy_validation) if isinstance(self.debug_copy_validation, dict) else None,
        }


@dataclass
class ProbeSummary:
    """Suite-level probe results plus renderable summary metadata."""

    generated_at: str
    suite_dir: str
    targets: list[dict[str, Any]]
    results: list[ProbeBundle]

    def to_json(self) -> dict[str, Any]:
        rows = [result.to_summary_row() for result in self.results]
        classifications: dict[str, int] = {}
        transition_reasons: dict[str, int] = {}
        terminal_reasons: dict[str, int] = {}
        persisted_tool_output_count = 0
        for row in rows:
            key = str(row.get("classification") or "unknown")
            classifications[key] = classifications.get(key, 0) + 1
            transition = str(row.get("transition_reason") or "").strip()
            if transition:
                transition_reasons[transition] = transition_reasons.get(transition, 0) + 1
            terminal = str(row.get("terminal_reason") or "").strip()
            if terminal:
                terminal_reasons[terminal] = terminal_reasons.get(terminal, 0) + 1
            persisted_tool_output_count += len(list(row.get("oversized_tool_artifact_ids") or []))
        return {
            "generated_at": self.generated_at,
            "suite_dir": self.suite_dir,
            "targets": self.targets,
            "results": rows,
            "classification_counts": classifications,
            "transition_reason_counts": transition_reasons,
            "terminal_reason_counts": terminal_reasons,
            "persisted_tool_output_count": persisted_tool_output_count,
        }


def build_runtime_probe_specs() -> list[ProbeSpec]:
    """Return the default runtime probe suite."""
    return [
        ProbeSpec(
            name="repo_inspect_summary",
            prompt="Inspect the repository, use tools to learn where you are, then summarize what you found.",
        ),
        ProbeSpec(
            name="repo_tools_emphasis",
            prompt="Inspect the repository. Use tools deliberately to learn the layout first, then summarize the repo and mention which tools you used.",
        ),
        ProbeSpec(
            name="relevant_files_bug_probe",
            prompt="A bug report says session runtime state can drift after tool use. Use tools to identify the most relevant files to inspect first and explain why.",
        ),
        ProbeSpec(
            name="architecture_setup_probe",
            prompt="Use tools to inspect the repository and explain the architecture and setup path for CopeNet.",
        ),
        ProbeSpec(
            name="patch_plan_probe",
            prompt="Use tools to inspect the runtime code and produce a small patch plan for improving repository exploration behavior with smaller models.",
        ),
        ProbeSpec(
            name="same_session_seed_probe",
            prompt="Inspect the repository using tools and summarize the runtime-related files that look most important.",
            session_group="repeat-stability",
        ),
        ProbeSpec(
            name="same_session_repeat_probe",
            prompt="Inspect the repository again using tools, but keep your answer compact so we can verify same-session stability.",
            session_group="repeat-stability",
        ),
        ProbeSpec(
            name="debug_copy_validation_probe",
            prompt="Inspect the repository with tools, then summarize what you found so this run can be used to validate debug-copy fidelity.",
            validate_debug_copy=True,
        ),
    ]


def classify_probe_bundle(
    *,
    probe: ProbeSpec,
    run_record: dict[str, Any] | None,
    transcript: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    trace_path: str | None,
    previous_bundle: ProbeBundle | None = None,
) -> dict[str, Any]:
    """Classify one probe run from durable runtime state."""
    status = str((run_record or {}).get("status") or "missing").strip() or "missing"
    final_state = "ok" if status == "ok" else status
    tool_steps = _tool_steps(run_record)
    tool_ids = _tool_ids(tool_steps)
    used_batch = any(bool(step.get("batched")) for step in tool_steps) or len(tool_steps) > 1
    used_context_prepare = "context.prepare" in tool_ids
    artifact_count = len(artifacts)
    artifact_ids = _artifact_ids(artifacts)
    trace_present = bool(trace_path and Path(trace_path).exists())
    transition_reason = str((run_record or {}).get("transitionReason") or "").strip()
    terminal_reason = str((run_record or {}).get("terminalReason") or "").strip()
    oversized_tool_artifact_ids = [
        str(value).strip()
        for value in list((run_record or {}).get("oversizedToolArtifactIds") or [])
        if str(value).strip()
    ]
    output_preview = str((run_record or {}).get("outputSummary") or _last_assistant_content(transcript)).strip()
    if len(output_preview) > 240:
        output_preview = output_preview[:237] + "..."

    classification = "plain_chat_success"
    if status != "ok":
        classification = "runtime_error"
    elif used_batch:
        classification = "batch_success"
    elif len(tool_ids) > 1:
        classification = "multi_tool_success"
    elif len(tool_ids) == 1:
        classification = "single_tool_success"
    elif probe.expects_tools:
        classification = "no_tool_when_expected"

    assistant_content = _last_assistant_content(transcript)
    if classification == "no_tool_when_expected" and _looks_like_adjacent_tool_json(assistant_content):
        classification = "malformed_multi_tool_output"

    blocked_steps = [step for step in tool_steps if str(step.get("status") or "").strip() == "blocked"]
    ok_steps = [step for step in tool_steps if bool(step.get("ok"))]
    if blocked_steps:
        if ok_steps:
            classification = "partial_tool_success_with_block"
        elif terminal_reason == "completed":
            classification = "blocked_but_recovered"
        else:
            classification = "tool_blocked_terminal"
    elif transition_reason == "tool_error_correction":
        classification = "tool_error_corrected"
    elif terminal_reason == "tool_error_terminal":
        classification = "tool_error_terminal"
    elif transition_reason == "resume_followup":
        classification = "resume_followup_success"
    elif oversized_tool_artifact_ids:
        classification = "oversized_output_persisted"

    if previous_bundle is not None and previous_bundle.tool_step_count > 0 and len(tool_ids) == 0:
        classification = "session_resume_drift"

    if classification not in {
        "partial_tool_success_with_block",
        "blocked_but_recovered",
        "tool_blocked_terminal",
        "runtime_error",
        "session_resume_drift",
        "tool_error_corrected",
        "tool_error_terminal",
        "resume_followup_success",
        "oversized_output_persisted",
    }:
        if probe.expects_tools and len(tool_ids) == 1 and not used_context_prepare and not used_batch:
            classification = "premature_stop_after_one_tool"
        elif (
            _is_repo_understanding_probe(probe)
            and tool_ids
            and (
                (_requires_file_grounding(probe) and not _has_file_grounding_tool(tool_ids, artifacts))
                or (not _requires_file_grounding(probe) and not _has_any_grounding_tool(tool_ids, artifacts))
            )
            and (_requires_file_grounding(probe) or not _cites_specific_file(assistant_content))
        ):
            classification = "ungrounded_repo_answer"

    return {
        "status": status,
        "final_state": final_state,
        "classification": classification,
        "tool_step_count": len(tool_ids),
        "tool_ids": tool_ids,
        "used_batch": used_batch,
        "used_context_prepare": used_context_prepare,
        "trace_present": trace_present,
        "artifact_count": artifact_count,
        "artifact_ids": artifact_ids,
        "output_preview": output_preview,
        "transition_reason": transition_reason,
        "terminal_reason": terminal_reason,
        "oversized_tool_artifact_ids": oversized_tool_artifact_ids,
    }


def validate_debug_copy_bundle(
    *,
    original_transcript: list[dict[str, Any]],
    original_artifacts: list[dict[str, Any]],
    original_runs: list[dict[str, Any]],
    original_state: dict[str, Any] | None,
    copied_session: dict[str, Any] | None,
    copied_transcript: list[dict[str, Any]],
    copied_artifacts: list[dict[str, Any]],
    copied_runs: list[dict[str, Any]],
    copied_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare copied session runtime truth against the original session."""
    mismatches: list[str] = []
    if len(copied_transcript) < len(original_transcript):
        mismatches.append("transcript_count")
    if len(copied_artifacts) < len(original_artifacts):
        mismatches.append("artifact_count")
    if len(copied_runs) < len(original_runs):
        mismatches.append("run_count")
    original_summary = str((original_state or {}).get("task_summary") or "").strip()
    copied_summary = str((copied_state or {}).get("task_summary") or "").strip()
    if bool(original_state) != bool(copied_state) or (original_summary and copied_summary != original_summary):
        mismatches.append("session_state")
    if not isinstance(copied_session, dict) or not str(copied_session.get("key") or "").strip():
        mismatches.append("copied_session")
    return {
        "ok": not mismatches,
        "copied_session_key": str((copied_session or {}).get("key") or ""),
        "mismatches": mismatches,
        "original_counts": {
            "transcript": len(original_transcript),
            "artifacts": len(original_artifacts),
            "runs": len(original_runs),
        },
        "copied_counts": {
            "transcript": len(copied_transcript),
            "artifacts": len(copied_artifacts),
            "runs": len(copied_runs),
        },
    }


def write_probe_bundle(root_dir: Path, bundle: ProbeBundle) -> Path:
    """Write one per-run probe bundle directory."""
    run_slug = _safe_slug(bundle.run_id, "no-run-id")
    bundle_dir = root_dir / (
        f"{_safe_slug(bundle.provider, 'provider')}__"
        f"{_safe_slug(bundle.model, 'default')}__"
        f"{_safe_slug(bundle.probe_name, 'probe')}__"
        f"{run_slug}"
    )
    bundle_dir.mkdir(parents=True, exist_ok=True)

    probe_payload = {
        "provider": bundle.provider,
        "model": bundle.model,
        "probe_name": bundle.probe_name,
        "prompt": bundle.prompt,
        "session_key": bundle.session_key,
        "run_id": bundle.run_id,
        "started_at": bundle.started_at,
        "finished_at": bundle.finished_at,
        "duration_ms": bundle.duration_ms,
        "status": bundle.status,
        "final_state": bundle.final_state,
        "classification": bundle.classification,
        "trace_path": bundle.trace_path,
    }
    (bundle_dir / "probe.json").write_text(_json_dumps(probe_payload), encoding="utf-8")
    (bundle_dir / "run_record.json").write_text(_json_dumps(bundle.run_record or {}), encoding="utf-8")
    (bundle_dir / "session_state.json").write_text(_json_dumps(bundle.session_state or {}), encoding="utf-8")
    (bundle_dir / "artifacts.json").write_text(_json_dumps(bundle.artifacts), encoding="utf-8")
    (bundle_dir / "transcript.json").write_text(_json_dumps(bundle.transcript), encoding="utf-8")
    (bundle_dir / "transcript.md").write_text(
        bundle.transcript_markdown or render_transcript_markdown(bundle.session, bundle.transcript),
        encoding="utf-8",
    )
    notes_payload = dict(bundle.notes)
    notes_payload.update(
        {
            "tool_step_count": bundle.tool_step_count,
            "tool_ids": bundle.tool_ids,
            "artifact_count": bundle.artifact_count,
            "artifact_ids": bundle.artifact_ids,
            "used_batch": bundle.used_batch,
            "used_context_prepare": bundle.used_context_prepare,
            "trace_present": bundle.trace_present,
            "output_preview": bundle.output_preview,
            "transition_reason": bundle.transition_reason,
            "terminal_reason": bundle.terminal_reason,
            "oversized_tool_artifact_ids": bundle.oversized_tool_artifact_ids,
        }
    )
    if bundle.debug_copy_validation is not None:
        notes_payload["debug_copy_validation"] = bundle.debug_copy_validation
    (bundle_dir / "notes.json").write_text(_json_dumps(notes_payload), encoding="utf-8")
    if isinstance(bundle.raw_final_payload, dict):
        (bundle_dir / "final_payload.json").write_text(_json_dumps(bundle.raw_final_payload), encoding="utf-8")
    if bundle.trace_path and Path(bundle.trace_path).exists():
        shutil.copyfile(bundle.trace_path, bundle_dir / "trace.jsonl")

    bundle.bundle_dir = str(bundle_dir)
    return bundle_dir


def render_probe_report(summary: ProbeSummary) -> str:
    """Render one compact suite markdown report."""
    rows = [result.to_summary_row() for result in summary.results]
    targets_label = ", ".join(
        f"{row['provider']} / {row.get('model') or '(default)'}" for row in summary.targets
    )
    lines = [
        "# Runtime Probe Report",
        "",
        f"- Generated at: `{summary.generated_at}`",
        f"- Suite dir: `{summary.suite_dir}`",
        f"- Targets: {targets_label}",
        "",
        "## Runs",
        "",
        "| Provider | Model | Probe | Classification | Steps | Tools | ms |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['provider']} | {row.get('model') or '(default)'} | {row['probe_name']} | "
            f"{row['classification']} | {row['tool_step_count']} | "
            f"{', '.join(row['tool_ids']) or '-'} | {row['duration_ms']} |"
        )

    failures: dict[str, list[dict[str, Any]]] = {}
    recoveries: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        classification = str(row["classification"])
        if classification.endswith("success"):
            continue
        if classification in {
            "partial_tool_success_with_block",
            "blocked_but_recovered",
            "tool_error_corrected",
            "resume_followup_success",
            "oversized_output_persisted",
        }:
            recoveries.setdefault(classification, []).append(row)
            continue
        failures.setdefault(classification, []).append(row)
    if recoveries:
        lines.extend(["", "## Recoveries", ""])
        for classification, items in sorted(recoveries.items()):
            lines.append(f"### {classification}")
            lines.append("")
            for item in items:
                lines.append(
                    f"- `{item['provider']}` / `{item.get('model') or '(default)'}` / `{item['probe_name']}`"
                )
            lines.append("")
    if failures:
        lines.extend(["", "## Failures", ""])
        for classification, items in sorted(failures.items()):
            lines.append(f"### {classification}")
            lines.append("")
            for item in items:
                lines.append(
                    f"- `{item['provider']}` / `{item.get('model') or '(default)'}` / `{item['probe_name']}`"
                )
            lines.append("")

    copy_rows = [row for row in rows if isinstance(row.get("debug_copy_validation"), dict)]
    if copy_rows:
        lines.extend(["## Debug Copy Validation", ""])
        for row in copy_rows:
            validation = row["debug_copy_validation"]
            label = "ok" if validation.get("ok") else "mismatch"
            mismatch_text = ", ".join(validation.get("mismatches") or []) or "none"
            lines.append(
                f"- `{row['provider']}` / `{row.get('model') or '(default)'}` / `{row['probe_name']}`: "
                f"{label} (mismatches: {mismatch_text})"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
