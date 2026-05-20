from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "lmstudio_probe_sweep.py"
SPEC = importlib.util.spec_from_file_location("lmstudio_probe_sweep", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
lmstudio_probe_sweep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lmstudio_probe_sweep
SPEC.loader.exec_module(lmstudio_probe_sweep)

LIVE_PROBE_PATH = REPO_ROOT / "scripts" / "live_probe_matrix.py"
LIVE_PROBE_SPEC = importlib.util.spec_from_file_location("live_probe_matrix", LIVE_PROBE_PATH)
assert LIVE_PROBE_SPEC is not None and LIVE_PROBE_SPEC.loader is not None
live_probe_matrix = importlib.util.module_from_spec(LIVE_PROBE_SPEC)
sys.modules[LIVE_PROBE_SPEC.name] = live_probe_matrix
LIVE_PROBE_SPEC.loader.exec_module(live_probe_matrix)


def test_select_chat_models_filters_embeddings_and_honors_limit() -> None:
    rows = [
        {"type": "llm", "key": "google/gemma-4-e4b"},
        {"type": "embedding", "key": "text-embedding-nomic-embed-text-v1.5"},
        {"type": "llm", "key": "qwen/qwen3.5-9b"},
        {"type": "llm", "key": "nvidia/nemotron-3-nano-4b"},
    ]

    selected = lmstudio_probe_sweep.select_chat_models(rows, requested_models=[], limit=2)

    assert selected == ["google/gemma-4-e4b", "qwen/qwen3.5-9b"]


def test_select_chat_models_keeps_requested_order() -> None:
    rows = [
        {"type": "llm", "key": "google/gemma-4-e4b"},
        {"type": "llm", "key": "qwen/qwen3.5-9b"},
    ]

    selected = lmstudio_probe_sweep.select_chat_models(
        rows,
        requested_models=["qwen/qwen3.5-9b", "missing/model", "google/gemma-4-e4b"],
        limit=None,
    )

    assert selected == ["qwen/qwen3.5-9b", "google/gemma-4-e4b"]


def test_build_probe_command_targets_one_lmstudio_model() -> None:
    command = lmstudio_probe_sweep.build_probe_command(
        model="google/gemma-4-e4b",
        probes="repo_inspect_summary,patch_plan_probe",
        output_dir=Path("/tmp/probe-runs"),
        repeats=2,
        expect_trace=True,
    )

    assert command[:2] == [lmstudio_probe_sweep.sys.executable, str(lmstudio_probe_sweep.LIVE_PROBE_SCRIPT)]
    assert "--providers" in command
    assert command[command.index("--providers") + 1] == "lm-studio"
    assert command[command.index("--lm-model") + 1] == "google/gemma-4-e4b"
    assert command[command.index("--probes") + 1] == "repo_inspect_summary,patch_plan_probe"
    assert command[command.index("--output-dir") + 1] == "/tmp/probe-runs"
    assert command[command.index("--repeats") + 1] == "2"
    assert "--expect-trace" in command


def test_live_probe_default_frontier_baseline_uses_oauth_codex() -> None:
    assert live_probe_matrix.DEFAULT_PROVIDERS == "openai-codex,lm-studio"
