from __future__ import annotations

import os
from pathlib import Path

from copenet.core.observability import ObservabilityStore
from copenet.core.tracing import RunTraceWriter


def _writer(tmp_path: Path, *, debug: bool, run_id: str = "run-1", max_bytes: int = 0) -> RunTraceWriter:
    return RunTraceWriter(
        run_id=run_id,
        session_key="session-1",
        provider="fake",
        model="model-a",
        enabled=True,
        debug=debug,
        root_dir=tmp_path,
        max_bytes=max_bytes or 8 * 1024 * 1024,
    )


def test_observability_settings_use_env_default_until_operator_updates(tmp_path: Path) -> None:
    store = ObservabilityStore(
        settings_path=tmp_path / "observability.json",
        trace_root=tmp_path / "runs",
        default_debug_capture=True,
    )

    assert store.load_settings().debug_capture is True
    store.update_settings(debug_capture=False)
    assert store.load_settings().debug_capture is False


def test_debug_trace_redacts_credentials_without_redacting_token_metrics(tmp_path: Path) -> None:
    writer = RunTraceWriter(
        run_id="run-1",
        session_key="session-1",
        provider="fake",
        model="model-a",
        enabled=True,
        debug=True,
        root_dir=tmp_path,
    )
    writer.record_debug(
        "model_input_snapshot",
        {
            "accessToken": "private",
            "nested": {"password": "private", "inputTokenEstimate": 123},
        },
    )

    store = ObservabilityStore(
        settings_path=tmp_path / "settings.json",
        trace_root=tmp_path,
    )
    payload = store.list_trace_events("run-1")[0]["payload"]
    assert payload["accessToken"] == "[redacted]"
    assert payload["nested"]["password"] == "[redacted]"
    assert payload["nested"]["inputTokenEstimate"] == 123


def test_lifecycle_events_write_with_debug_capture_off(tmp_path: Path) -> None:
    """The whole point of workstream 1: a run stays auditable without Debug capture."""
    writer = _writer(tmp_path, debug=False)
    writer.record("run_started", {"taskMode": "full-access"})
    writer.record_debug("model_input_snapshot", {"instructions": "secret prompt"})

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=tmp_path)
    events = store.list_trace_events("run-1")
    assert [event["event"] for event in events] == ["run_started"]
    assert events[0]["tier"] == "lifecycle"


def test_debug_tier_events_route_to_debug_even_through_record(tmp_path: Path) -> None:
    """The harness loops hold a bare callable, so the writer owns the tier decision."""
    off = _writer(tmp_path, debug=False, run_id="run-off")
    off.record("tool_requested", {"toolId": "files.read"})
    off.record("tool_arguments", {"toolId": "files.read", "arguments": {"path": "a.py"}})

    on = _writer(tmp_path, debug=True, run_id="run-on")
    on.record("tool_requested", {"toolId": "files.read"})
    on.record("tool_arguments", {"toolId": "files.read", "arguments": {"path": "a.py"}})

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=tmp_path)
    assert [event["event"] for event in store.list_trace_events("run-off")] == ["tool_requested"]
    on_events = store.list_trace_events("run-on")
    assert [event["event"] for event in on_events] == ["tool_requested", "tool_arguments"]
    assert on_events[1]["tier"] == "debug"


def test_a_runaway_run_stops_at_the_size_cap(tmp_path: Path) -> None:
    writer = _writer(tmp_path, debug=True, max_bytes=1_500)
    for index in range(50):
        writer.record("tool_executed", {"toolId": "files.read", "summary": "x" * 200, "index": index})

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=tmp_path)
    events = store.list_trace_events("run-1")
    assert events[-1]["event"] == "trace_truncated"
    assert events[-1]["payload"]["maxBytes"] == 1_500
    assert (tmp_path / "run-1.jsonl").stat().st_size <= 1_500 + 400
    assert sum(1 for event in events if event["event"] == "trace_truncated") == 1


def test_prune_removes_oldest_traces_until_under_the_ceiling(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.mkdir()
    for index, name in enumerate(["oldest", "middle", "newest"]):
        path = root / f"{name}.jsonl"
        path.write_text("x" * 400, encoding="utf-8")
        os.utime(path, (1_000 + index * 100, 1_000 + index * 100))

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=root)
    assert store.trace_storage_stats() == {"fileCount": 3, "totalBytes": 1_200}

    result = store.prune_traces(max_total_bytes=900, max_files=100)
    assert result == {"removedFileCount": 1, "freedBytes": 400}
    assert sorted(path.stem for path in root.glob("*.jsonl")) == ["middle", "newest"]


def test_prune_also_enforces_the_file_count_ceiling(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.mkdir()
    for index in range(5):
        path = root / f"run-{index}.jsonl"
        path.write_text("x", encoding="utf-8")
        os.utime(path, (1_000 + index, 1_000 + index))

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=root)
    store.prune_traces(max_total_bytes=10_000_000, max_files=2)
    assert sorted(path.stem for path in root.glob("*.jsonl")) == ["run-3", "run-4"]


def test_purge_clears_every_trace(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.mkdir()
    (root / "a.jsonl").write_text("x" * 10, encoding="utf-8")
    (root / "b.jsonl").write_text("y" * 20, encoding="utf-8")

    store = ObservabilityStore(settings_path=tmp_path / "settings.json", trace_root=root)
    assert store.purge_traces() == {"removedFileCount": 2, "freedBytes": 30}
    assert store.trace_storage_stats() == {"fileCount": 0, "totalBytes": 0}
