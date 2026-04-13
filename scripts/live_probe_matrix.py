"""Live provider probe runner for CopeNet.

Runs a compact prompt matrix against real providers/models and records
structured results for later comparison.

Usage examples:
    COPNET_TRACE=1 uv run python scripts/live_probe_matrix.py --lm-model gemma-4-e4b-uncensored-hauhaucs-aggressive
    COPNET_TRACE=1 uv run python scripts/live_probe_matrix.py --providers codex-cli,lm-studio --lm-model qwen-small
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import time
import uuid
import os
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.client import GatewayClient, GatewayConfig


DEFAULT_WS_URL = "ws://127.0.0.1:17123/ws"
DEFAULT_TOKEN = "dev-token"


@dataclass(frozen=True)
class Target:
    provider: str
    model: str | None


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    prompt: str
    expectation: str
    expected_tool_id: str | None = None
    session_group: str | None = None


@dataclass
class ProbeResult:
    provider: str
    model: str | None
    probe_name: str
    session_key: str
    run_id: str | None
    final_state: str
    classification: str
    tool_execution_attached: bool
    tool_id: str | None
    tool_ok: bool | None
    error_message: str | None
    response_preview: str
    trace_path: str | None
    started_at: str
    finished_at: str
    duration_ms: int


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_trace_path(run_id: str | None) -> Path | None:
    if not run_id:
        return None
    data_root = Path(os.environ.get("COPNET_DATA_DIR", Path.home() / ".copenet"))
    trace_path = data_root / "logs" / "runs" / f"{run_id}.jsonl"
    return trace_path if trace_path.exists() else trace_path


def _artifact_dir() -> Path:
    root = Path.cwd() / "tmp" / "live_probe_results"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_model(model: str | None) -> str:
    if not model:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in model)


def _build_probe_specs() -> tuple[list[ProbeSpec], list[ProbeSpec]]:
    fresh = [
        ProbeSpec(
            name="basic_chat",
            prompt="Hello, we are testing CopeNet. Please reply with one short sentence only.",
            expectation="plain_chat",
        ),
        ProbeSpec(
            name="tool_files_list",
            prompt="Please use files.list on the current repo workspace and tell me briefly whether it worked.",
            expectation="tool_success",
            expected_tool_id="files.list",
        ),
        ProbeSpec(
            name="tool_files_read",
            prompt="Please use files.read on docs/tests/TEST_FILE.md and tell me the first line only.",
            expectation="tool_success",
            expected_tool_id="files.read",
        ),
        ProbeSpec(
            name="tool_git_status",
            prompt="Please run git.status and just say success if it worked.",
            expectation="tool_success",
            expected_tool_id="git.status",
        ),
        ProbeSpec(
            name="tool_blocked_parent",
            prompt="Please try files.list on .. and explain briefly what happened.",
            expectation="tool_block",
            expected_tool_id="files.list",
        ),
    ]
    resume = [
        ProbeSpec(
            name="resume_seed_tool",
            prompt="Please use files.list on the current repo workspace and tell me briefly whether it worked.",
            expectation="tool_success",
            expected_tool_id="files.list",
            session_group="resume",
        ),
        ProbeSpec(
            name="resume_follow_up_chat",
            prompt="Now answer normally in one short sentence so we can verify the session is still stable after tool use.",
            expectation="plain_chat",
            session_group="resume",
        ),
        ProbeSpec(
            name="resume_repeat_tool",
            prompt="Please use files.list on the current repo workspace again and say whether it worked.",
            expectation="resume_repeat_tool",
            expected_tool_id="files.list",
            session_group="resume",
        ),
    ]
    return fresh, resume


def _classify_result(spec: ProbeSpec, final_payload: dict[str, Any] | None, response_preview: str) -> str:
    payload = final_payload or {}
    state = str(payload.get("state") or "unknown")
    tool_execution = payload.get("toolExecution")
    tool_id = tool_execution.get("toolId") if isinstance(tool_execution, dict) else None
    tool_ok = tool_execution.get("ok") if isinstance(tool_execution, dict) else None

    if state in {"error", "aborted"}:
        return "transport/runtime error"

    if spec.expectation == "plain_chat":
        return "expected plain chat" if tool_execution is None else "unexpected tool attached"

    if spec.expectation == "tool_success":
        if tool_execution is None:
            return "no tool requested / prose fallback"
        if tool_id != spec.expected_tool_id:
            return "unexpected tool requested"
        if tool_ok is True:
            return "expected tool success"
        return "tool requested but failed"

    if spec.expectation == "tool_block":
        if tool_execution is None:
            return "no tool requested / prose fallback"
        if tool_id != spec.expected_tool_id:
            return "unexpected tool requested"
        if tool_ok is False:
            return "expected tool block"
        return "unexpected tool success"

    if spec.expectation == "resume_repeat_tool":
        if tool_execution is None:
            return "resumed-session drift observed"
        if tool_id != spec.expected_tool_id:
            return "unexpected tool requested"
        if tool_ok is True:
            return "resume stable"
        return "tool requested but failed"

    return "unclassified"


async def _resolve_targets(client: GatewayClient, providers_csv: str, lm_model: str | None) -> list[Target]:
    requested = [item.strip() for item in providers_csv.split(",") if item.strip()]
    provider_rows = await client.list_providers()
    available = {row["id"]: row for row in provider_rows if row.get("available", True)}

    targets: list[Target] = []
    for provider_id in requested:
        if provider_id not in available:
            print(f"Skipping unavailable provider: {provider_id}")
            continue
        if provider_id == "lm-studio":
            chosen_model = lm_model
            if not chosen_model:
                models = await client.list_models(provider="lm-studio")
                chosen_model = models[0]["id"] if models else None
            targets.append(Target(provider="lm-studio", model=chosen_model))
            continue
        targets.append(Target(provider=provider_id, model=None))
    return targets


async def _run_probe(
    *,
    client: GatewayClient,
    target: Target,
    spec: ProbeSpec,
    session_key: str,
) -> ProbeResult:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    final_payload: dict[str, Any] | None = None
    response_parts: list[str] = []
    run_id: str | None = None

    async def on_started(started_run_id: str) -> None:
        nonlocal run_id
        run_id = started_run_id

    async def on_event(payload: dict[str, Any]) -> None:
        nonlocal final_payload
        state = str(payload.get("state") or "")
        if state == "delta":
            message = payload.get("message")
            if isinstance(message, dict):
                response_parts.append(str(message.get("content") or ""))
        if state in {"final", "error", "aborted"}:
            final_payload = payload
            if state != "delta":
                message = payload.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str) and message["content"]:
                    response_parts.append(message["content"])

    error_message: str | None = None
    final_state = "unknown"
    try:
        send_result = await client.stream_chat(
            session_key=session_key,
            message=spec.prompt,
            idempotency_key=f"probe-{uuid.uuid4().hex[:10]}",
            provider=target.provider,
            model=target.model,
            on_event=on_event,
            on_started=on_started,
        )
        run_id = run_id or str(send_result.get("runId") or "")
        final_state = str((final_payload or {}).get("state") or send_result.get("status") or "unknown")
    except Exception as exc:
        error_message = str(exc)
        final_state = "client_error"

    finished_at = _now_iso()
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    payload = final_payload or {}
    tool_execution = payload.get("toolExecution") if isinstance(payload.get("toolExecution"), dict) else None
    preview = "".join(response_parts).strip()
    if len(preview) > 220:
        preview = preview[:217] + "..."

    if error_message is None:
        payload_error = payload.get("errorMessage")
        error_message = str(payload_error) if isinstance(payload_error, str) and payload_error.strip() else None

    classification = _classify_result(spec, final_payload, preview)
    trace_path = _default_trace_path(run_id)

    return ProbeResult(
        provider=target.provider,
        model=target.model,
        probe_name=spec.name,
        session_key=session_key,
        run_id=run_id,
        final_state=final_state,
        classification=classification,
        tool_execution_attached=tool_execution is not None,
        tool_id=str(tool_execution.get("toolId")) if tool_execution and tool_execution.get("toolId") else None,
        tool_ok=bool(tool_execution.get("ok")) if isinstance(tool_execution, dict) and "ok" in tool_execution else None,
        error_message=error_message,
        response_preview=preview,
        trace_path=str(trace_path) if trace_path is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


async def _run_target_matrix(client: GatewayClient, target: Target) -> list[ProbeResult]:
    fresh_specs, resume_specs = _build_probe_specs()
    results: list[ProbeResult] = []

    for spec in fresh_specs:
        session_key = f"probe-{target.provider}-{_sanitize_model(target.model)}-{spec.name}-{uuid.uuid4().hex[:6]}"
        results.append(await _run_probe(client=client, target=target, spec=spec, session_key=session_key))

    resume_session_key = f"probe-{target.provider}-{_sanitize_model(target.model)}-resume-{uuid.uuid4().hex[:6]}"
    for spec in resume_specs:
        results.append(await _run_probe(client=client, target=target, spec=spec, session_key=resume_session_key))

    return results


def _write_artifact(results: list[ProbeResult]) -> Path:
    artifact_path = _artifact_dir() / f"probe-matrix-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    payload = {
        "generatedAt": _now_iso(),
        "results": [asdict(result) for result in results],
    }
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact_path


def _print_summary(results: list[ProbeResult], artifact_path: Path) -> None:
    print("\n=== LIVE PROBE SUMMARY ===")
    print(f"{'provider':12s} {'model':28s} {'probe':24s} {'classification':30s} {'state':10s} {'tool':18s} {'ms':>6s}")
    print("-" * 140)
    for result in results:
        model = result.model or "(default)"
        tool = result.tool_id or "-"
        print(
            f"{result.provider[:12]:12s} "
            f"{model[:28]:28s} "
            f"{result.probe_name[:24]:24s} "
            f"{result.classification[:30]:30s} "
            f"{result.final_state[:10]:10s} "
            f"{tool[:18]:18s} "
            f"{result.duration_ms:6d}"
        )
    print(f"\nArtifact: {artifact_path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run live CopeNet provider/model probes.")
    parser.add_argument("--ws-url", default=os.environ.get("COPNET_WS_URL", DEFAULT_WS_URL))
    parser.add_argument("--token", default=os.environ.get("COPNET_TOKEN", DEFAULT_TOKEN))
    parser.add_argument("--providers", default="codex-cli,lm-studio")
    parser.add_argument("--lm-model", default=os.environ.get("COPNET_LM_MODEL"))
    args = parser.parse_args()

    client = GatewayClient(GatewayConfig(url=args.ws_url, token=args.token))
    targets = await _resolve_targets(client, args.providers, args.lm_model)
    if not targets:
        raise SystemExit("No runnable targets found. Check provider availability and --providers/--lm-model options.")

    print("Running live probe matrix:")
    for target in targets:
        model_label = target.model or "(default)"
        print(f"  - {target.provider} / {model_label}")

    results: list[ProbeResult] = []
    for target in targets:
        results.extend(await _run_target_matrix(client, target))

    artifact_path = _write_artifact(results)
    _print_summary(results, artifact_path)


if __name__ == "__main__":
    asyncio.run(main())
