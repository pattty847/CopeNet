from __future__ import annotations

import json
from pathlib import Path

from copenet.probes.runtime_bundle import (
    ProbeBundle,
    ProbeSpec,
    ProbeSummary,
    classify_probe_bundle,
    render_probe_report,
    validate_debug_copy_bundle,
    write_probe_bundle,
)


def test_classify_probe_bundle_distinguishes_runtime_shapes(tmp_path: Path) -> None:
    spec = ProbeSpec(name="repo_inspect", prompt="Inspect the repo")

    blocked = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [{"toolId": "files.list", "status": "blocked"}],
            "terminalReason": "tool_error_terminal",
            "outputSummary": "blocked",
        },
        transcript=[],
        artifacts=[],
        trace_path=None,
    )
    assert blocked["classification"] == "tool_blocked_terminal"

    batch = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolExecutionMode": "native",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok"},
                {"toolId": "files.read", "status": "ok"},
            ],
            "outputSummary": "two reads",
        },
        transcript=[],
        artifacts=[],
        trace_path=str(tmp_path / "missing.jsonl"),
    )
    assert batch["classification"] == "multi_tool_success"
    assert batch["tool_protocol"] == "native_tool_calls"

    true_batch = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolExecutionMode": "batch",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok", "batched": True},
                {"toolId": "files.read", "status": "ok", "batched": True},
            ],
            "outputSummary": "batched reads",
        },
        transcript=[],
        artifacts=[],
        trace_path=str(tmp_path / "missing-2.jsonl"),
    )
    assert true_batch["classification"] == "batch_success"

    malformed = classify_probe_bundle(
        probe=spec,
        run_record={"status": "ok", "toolSteps": [], "outputSummary": ""},
        transcript=[
            {"role": "assistant", "content": '{"tool_id":"files.read"} {"tool_id":"files.read"}'},
        ],
        artifacts=[],
        trace_path=None,
    )
    assert malformed["classification"] == "malformed_multi_tool_output"

    previous_bundle = ProbeBundle(
        provider="lm-studio",
        model="gemma",
        probe_name="seed",
        prompt="seed",
        session_key="alpha",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        tool_step_count=2,
    )
    drift = classify_probe_bundle(
        probe=ProbeSpec(name="repeat", prompt="repeat", session_group="repeat"),
        run_record={"status": "ok", "toolSteps": [], "outputSummary": "chat only"},
        transcript=[{"role": "assistant", "content": "chat only"}],
        artifacts=[],
        trace_path=None,
        previous_bundle=previous_bundle,
    )
    assert drift["classification"] == "session_resume_drift"

    corrected = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [{"toolId": "files.read", "status": "ok"}],
            "outputSummary": "corrected",
            "transitionReason": "tool_error_correction",
            "terminalReason": "completed",
            "oversizedToolArtifactIds": ["artifact-1"],
        },
        transcript=[],
        artifacts=[],
        trace_path=None,
    )
    assert corrected["classification"] == "tool_error_corrected"
    assert corrected["oversized_tool_artifact_ids"] == ["artifact-1"]

    partial = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "files.read", "status": "blocked", "ok": False},
            ],
            "outputSummary": "partial success",
            "terminalReason": "completed",
        },
        transcript=[],
        artifacts=[],
        trace_path=None,
    )
    assert partial["classification"] == "partial_tool_success_with_block"

    recovered = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [{"toolId": "tool.batch", "status": "blocked", "ok": False}],
            "outputSummary": "answered after block",
            "terminalReason": "completed",
        },
        transcript=[],
        artifacts=[],
        trace_path=None,
    )
    assert recovered["classification"] == "blocked_but_recovered"


def test_classify_probe_bundle_flags_ungrounded_repo_answer() -> None:
    spec = ProbeSpec(name="architecture_setup_probe", prompt="Explain architecture")

    listing_only = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "tool.batch", "status": "ok", "ok": True, "batched": True},
            ],
            "outputSummary": "The repo probably keeps the main logic in src/copenet and uses docs for setup.",
            "terminalReason": "completed",
        },
        transcript=[
            {
                "role": "assistant",
                "content": "The repo probably keeps the main logic in src/copenet and uses docs for setup.",
            }
        ],
        artifacts=[],
        trace_path=None,
    )

    assert listing_only["classification"] == "ungrounded_repo_answer"


def test_classify_probe_bundle_requires_file_grounding_for_architecture_probe() -> None:
    spec = ProbeSpec(name="architecture_setup_probe", prompt="Explain architecture and setup")

    context_only = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "context.prepare", "status": "ok", "ok": True},
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "tool.batch", "status": "ok", "ok": True, "batched": True},
            ],
            "outputSummary": "CopeNet looks like a modular Python app with code under src/copenet.",
            "terminalReason": "completed",
        },
        transcript=[
            {
                "role": "assistant",
                "content": "CopeNet looks like a modular Python app with code under src/copenet.",
            }
        ],
        artifacts=[
            {
                "artifactId": "bundle-1",
                "metadata": {"toolIds": ["files.list", "git.status"]},
            }
        ],
        trace_path=None,
    )

    assert context_only["classification"] == "ungrounded_repo_answer"


def test_classify_probe_bundle_does_not_treat_listed_filenames_as_file_grounding() -> None:
    spec = ProbeSpec(name="patch_plan_probe", prompt="Produce a patch plan for runtime exploration")

    listing_backed = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "context.prepare", "status": "ok", "ok": True},
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "tool.batch", "status": "ok", "ok": True, "batched": True},
            ],
            "outputSummary": "Read README.md and pyproject.toml for a patch plan.",
            "terminalReason": "completed",
        },
        transcript=[
            {
                "role": "assistant",
                "content": "Read README.md and pyproject.toml for a patch plan.",
            }
        ],
        artifacts=[
            {
                "artifactId": "bundle-1",
                "metadata": {"toolIds": ["files.list", "git.status"]},
            }
        ],
        trace_path=None,
    )

    assert listing_backed["classification"] == "ungrounded_repo_answer"


def test_write_probe_bundle_creates_expected_files(tmp_path: Path) -> None:
    trace_path = tmp_path / "original-trace.jsonl"
    trace_path.write_text('{"event":"tool"}\n', encoding="utf-8")

    bundle = ProbeBundle(
        provider="codex-cli",
        model="gpt-5.4",
        probe_name="repo_inspect",
        prompt="Inspect the repo",
        session_key="alpha",
        run_id="run-123",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        session={"key": "alpha", "title": "Alpha"},
        run_record={"runId": "run-123", "status": "ok"},
        session_state={"task_summary": "Inspect the repo"},
        artifacts=[{"artifactId": "artifact-1"}],
        transcript=[{"role": "user", "content": "Inspect the repo"}],
        transcript_markdown="# hi\n",
        trace_path=str(trace_path),
        notes={"note": "value"},
        classification="single_tool_success",
        final_state="ok",
        tool_step_count=1,
        tool_ids=["files.read"],
        artifact_ids=["artifact-1"],
        trace_present=True,
        artifact_count=1,
        output_preview="preview",
        transition_reason="tool_followup",
        terminal_reason="completed",
        oversized_tool_artifact_ids=["artifact-1"],
    )

    bundle_dir = write_probe_bundle(tmp_path / "suite", bundle)
    expected = {
        "probe.json",
        "run_record.json",
        "session_state.json",
        "artifacts.json",
        "transcript.json",
        "transcript.md",
        "notes.json",
        "trace.jsonl",
    }
    assert expected <= {path.name for path in bundle_dir.iterdir()}
    notes = json.loads((bundle_dir / "notes.json").read_text(encoding="utf-8"))
    assert notes["tool_step_count"] == 1
    assert notes["transition_reason"] == "tool_followup"
    assert bundle.bundle_dir == str(bundle_dir)


def test_validate_debug_copy_bundle_and_report_handle_mismatch() -> None:
    validation = validate_debug_copy_bundle(
        original_transcript=[{"role": "user"}],
        original_artifacts=[{"artifactId": "a"}],
        original_runs=[{"runId": "r"}],
        original_state={"task_summary": "Inspect"},
        copied_session={"key": "copy-1"},
        copied_transcript=[],
        copied_artifacts=[],
        copied_runs=[],
        copied_state=None,
    )
    assert validation["ok"] is False
    assert "transcript_count" in validation["mismatches"]

    bundle = ProbeBundle(
        provider="lm-studio",
        model="gemma-2b",
        probe_name="debug_copy_validation_probe",
        prompt="Inspect",
        session_key="alpha",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        classification="single_tool_success",
        final_state="ok",
        tool_step_count=1,
        tool_ids=["files.read"],
        debug_copy_validation=validation,
    )
    summary = ProbeSummary(
        generated_at="2026-01-01T00:00:02+00:00",
        suite_dir="/tmp/probe_runs/demo",
        targets=[{"provider": "lm-studio", "model": "gemma-2b"}],
        results=[bundle],
    )
    report = render_probe_report(summary)
    assert "Runtime Probe Report" in report
    assert "Debug Copy Validation" in report
    assert "mismatch" in report
    summary_json = summary.to_json()
    assert summary_json["transition_reason_counts"] == {}


def test_render_probe_report_separates_recoveries_from_failures() -> None:
    recovered = ProbeBundle(
        provider="lm-studio",
        model="gemma-2b",
        probe_name="repo_tools_emphasis",
        prompt="Inspect",
        session_key="alpha",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        classification="partial_tool_success_with_block",
        final_state="ok",
        tool_step_count=3,
        tool_ids=["files.list", "files.read", "tool.batch"],
    )
    failed = ProbeBundle(
        provider="codex-cli",
        model="gpt-5.4",
        probe_name="same_session_repeat_probe",
        prompt="Inspect again",
        session_key="beta",
        run_id="run-2",
        started_at="2026-01-01T00:00:02+00:00",
        finished_at="2026-01-01T00:00:03+00:00",
        duration_ms=1000,
        classification="tool_blocked_terminal",
        final_state="ok",
        tool_step_count=1,
        tool_ids=["tool.batch"],
    )
    summary = ProbeSummary(
        generated_at="2026-01-01T00:00:04+00:00",
        suite_dir="/tmp/probe_runs/demo",
        targets=[
            {"provider": "lm-studio", "model": "gemma-2b"},
            {"provider": "codex-cli", "model": "gpt-5.4"},
        ],
        results=[recovered, failed],
    )

    report = render_probe_report(summary)

    assert "## Recoveries" in report
    assert "### partial_tool_success_with_block" in report
    assert "## Failures" in report
    assert "### tool_blocked_terminal" in report


def test_render_probe_report_lists_ungrounded_answers_as_failures() -> None:
    bundle = ProbeBundle(
        provider="lm-studio",
        model="gemma-4",
        probe_name="architecture_setup_probe",
        prompt="Explain architecture",
        session_key="alpha",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        classification="ungrounded_repo_answer",
        final_state="ok",
        tool_step_count=3,
        tool_ids=["files.list", "files.list", "tool.batch"],
    )
    summary = ProbeSummary(
        generated_at="2026-01-01T00:00:02+00:00",
        suite_dir="/tmp/probe_runs/demo",
        targets=[{"provider": "lm-studio", "model": "gemma-4"}],
        results=[bundle],
    )

    report = render_probe_report(summary)

    assert "## Failures" in report
    assert "### ungrounded_repo_answer" in report


def test_classify_probe_bundle_flags_rejected_final_then_recovered() -> None:
    spec = ProbeSpec(name="architecture_setup_probe", prompt="Explain architecture")

    recovered = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "files.read", "status": "ok", "ok": True},
            ],
            "outputSummary": "README.md explains the architecture.",
            "terminalReason": "completed",
            "metadata": {
                "turnState": {
                    "finalRejectionCount": 1,
                    "lastFinalGateReasonCode": "missing_file_evidence",
                    "evidenceLedger": {
                        "groundingActions": ["files.read"],
                    },
                }
            },
        },
        transcript=[
            {
                "role": "assistant",
                "content": "README.md explains the architecture.",
            }
        ],
        artifacts=[],
        trace_path=None,
    )

    assert recovered["classification"] == "rejected_final_then_recovered"


def test_classify_probe_bundle_flags_missing_verification() -> None:
    spec = ProbeSpec(name="patch_verify_probe", prompt="Patch and verify the harness behavior")

    missing_verification = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "files.read", "status": "ok", "ok": True},
                {"toolId": "patch.apply", "status": "ok", "ok": True},
            ],
            "outputSummary": "Applied the patch.",
            "terminalReason": "completed",
            "metadata": {
                "turnState": {
                    "finalRejectionCount": 0,
                    "lastFinalGateReasonCode": "missing_verification",
                    "evidenceLedger": {
                        "groundingActions": ["files.read"],
                        "visitedTools": ["files.read", "patch.apply"],
                    },
                }
            },
        },
        transcript=[{"role": "assistant", "content": "Applied the patch."}],
        artifacts=[],
        trace_path=None,
    )

    assert missing_verification["classification"] == "missing_verification"
