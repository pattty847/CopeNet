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
            "outputSummary": "blocked",
        },
        transcript=[],
        artifacts=[],
        trace_path=None,
    )
    assert blocked["classification"] == "tool_blocked"

    batch = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
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
    assert batch["classification"] == "batch_success"

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
