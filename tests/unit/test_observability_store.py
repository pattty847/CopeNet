from __future__ import annotations

from pathlib import Path

from copenet.core.observability import ObservabilityStore
from copenet.core.tracing import RunTraceWriter


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
