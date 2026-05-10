from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest


def _load_probe_module() -> ModuleType:
    if "mao_probe_workers" in sys.modules:
        return sys.modules["mao_probe_workers"]
    root = Path(__file__).resolve().parents[2]
    module_path = root / ".agents" / "scripts" / "mao_probe_workers.py"
    spec = importlib.util.spec_from_file_location("mao_probe_workers", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mao_probe_workers"] = module
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _spec(probe, agent: str = "claude", timeout_seconds: int = 60):
    return probe.ProbeSpec(
        agent=agent,
        command=(agent, "-p", "ping"),
        timeout_seconds=timeout_seconds,
    )


def test_probe_reports_missing_when_binary_not_on_path() -> None:
    probe = _load_probe_module()
    spec = _spec(probe)
    with mock.patch.object(probe.shutil, "which", return_value=None):
        result = probe.probe_worker(spec)

    assert result.available is False
    assert result.responded is False
    assert result.binary_path is None
    assert "not on PATH" in (result.error or "")


def test_probe_reports_responded_on_clean_exit_with_stdout() -> None:
    probe = _load_probe_module()
    spec = _spec(probe)
    with mock.patch.object(probe.shutil, "which", return_value="/fake/bin/claude"), mock.patch.object(
        probe.subprocess, "run", return_value=_completed(stdout="pong\n")
    ):
        result = probe.probe_worker(spec)

    assert result.available is True
    assert result.responded is True
    assert result.binary_path == "/fake/bin/claude"
    assert result.error is None
    assert result.output_preview == "pong"
    assert result.duration_ms is not None and result.duration_ms >= 0


def test_probe_reports_failure_on_nonzero_exit() -> None:
    probe = _load_probe_module()
    spec = _spec(probe)
    with mock.patch.object(probe.shutil, "which", return_value="/fake/bin/claude"), mock.patch.object(
        probe.subprocess, "run", return_value=_completed(stdout="", stderr="auth required", returncode=2)
    ):
        result = probe.probe_worker(spec)

    assert result.available is True
    assert result.responded is False
    assert "exit 2" in (result.error or "")
    assert "auth required" in (result.error or "")


def test_probe_reports_failure_on_empty_stdout() -> None:
    probe = _load_probe_module()
    spec = _spec(probe)
    with mock.patch.object(probe.shutil, "which", return_value="/fake/bin/claude"), mock.patch.object(
        probe.subprocess, "run", return_value=_completed(stdout="   \n")
    ):
        result = probe.probe_worker(spec)

    assert result.responded is False
    assert result.error == "empty stdout"


def test_probe_reports_failure_on_timeout() -> None:
    probe = _load_probe_module()
    spec = _spec(probe, timeout_seconds=3)

    def _raise(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=spec.command, timeout=spec.timeout_seconds)

    with mock.patch.object(probe.shutil, "which", return_value="/fake/bin/claude"), mock.patch.object(
        probe.subprocess, "run", side_effect=_raise
    ):
        result = probe.probe_worker(spec)

    assert result.available is True
    assert result.responded is False
    assert "timed out" in (result.error or "")


def test_probe_reports_failure_when_invocation_raises_oserror() -> None:
    probe = _load_probe_module()
    spec = _spec(probe)
    with mock.patch.object(probe.shutil, "which", return_value="/fake/bin/claude"), mock.patch.object(
        probe.subprocess, "run", side_effect=OSError("permission denied")
    ):
        result = probe.probe_worker(spec)

    assert result.available is True
    assert result.responded is False
    assert "permission denied" in (result.error or "")


def test_probe_workers_handles_unknown_agent() -> None:
    probe = _load_probe_module()
    results = probe.probe_workers(["definitely-not-a-real-agent"])

    assert len(results) == 1
    assert results[0].agent == "definitely-not-a-real-agent"
    assert results[0].available is False
    assert "unknown agent" in (results[0].error or "")


def test_probe_workers_defaults_to_all_registered_agents() -> None:
    probe = _load_probe_module()
    with mock.patch.object(probe, "probe_worker", side_effect=lambda spec: probe.ProbeResult(
        agent=spec.agent,
        available=True,
        responded=True,
        binary_path="/fake/bin",
        duration_ms=10,
        error=None,
        output_preview="pong",
    )):
        results = probe.probe_workers()

    agents = {r.agent for r in results}
    assert agents == set(probe.WORKER_PROBES.keys())


def test_main_require_flag_returns_nonzero_when_required_agent_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    probe = _load_probe_module()
    with mock.patch.object(
        probe,
        "probe_workers",
        return_value=[
            probe.ProbeResult(
                agent="claude",
                available=False,
                responded=False,
                binary_path=None,
                duration_ms=None,
                error="binary not on PATH: claude",
                output_preview=None,
            )
        ],
    ):
        exit_code = probe.main(["--agent", "claude", "--require", "claude"])

    assert exit_code == 1


def test_main_require_flag_returns_zero_when_all_required_agents_respond() -> None:
    probe = _load_probe_module()
    with mock.patch.object(
        probe,
        "probe_workers",
        return_value=[
            probe.ProbeResult(
                agent="claude",
                available=True,
                responded=True,
                binary_path="/fake",
                duration_ms=10,
                error=None,
                output_preview="pong",
            )
        ],
    ):
        exit_code = probe.main(["--agent", "claude", "--require", "claude"])

    assert exit_code == 0


def test_main_emits_json_when_flag_set(capsys: pytest.CaptureFixture[str]) -> None:
    import json as json_mod

    probe = _load_probe_module()
    with mock.patch.object(
        probe,
        "probe_workers",
        return_value=[
            probe.ProbeResult(
                agent="claude",
                available=True,
                responded=True,
                binary_path="/fake",
                duration_ms=42,
                error=None,
                output_preview="pong",
            )
        ],
    ):
        probe.main(["--json"])

    captured = capsys.readouterr().out
    payload = json_mod.loads(captured)
    assert isinstance(payload, list)
    assert payload[0]["agent"] == "claude"
    assert payload[0]["responded"] is True


def test_truncate_collapses_whitespace_and_caps_length() -> None:
    probe = _load_probe_module()
    long_text = "pong\n\n  followed by  lots of   words " * 30
    out = probe._truncate(long_text, limit=50)
    assert len(out) <= 50
    assert "  " not in out


@pytest.mark.skipif(
    os.environ.get("MAO_LIVE_PROBE") != "1",
    reason="Set MAO_LIVE_PROBE=1 to run live worker probes (incurs API calls).",
)
def test_live_probe_claude_responds() -> None:
    probe = _load_probe_module()
    spec = probe.WORKER_PROBES["claude"]
    result = probe.probe_worker(spec)
    assert result.available, f"claude binary not found: {result.error}"
    assert result.responded, f"claude probe failed: {result.error}"


@pytest.mark.skipif(
    os.environ.get("MAO_LIVE_PROBE") != "1",
    reason="Set MAO_LIVE_PROBE=1 to run live worker probes (incurs API calls).",
)
def test_live_probe_gemini_responds() -> None:
    probe = _load_probe_module()
    spec = probe.WORKER_PROBES["gemini"]
    result = probe.probe_worker(spec)
    assert result.available, f"gemini binary not found: {result.error}"
    assert result.responded, f"gemini probe failed: {result.error}"
