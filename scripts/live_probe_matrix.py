"""Live runtime probe runner for CopeNet."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time
import uuid

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.client import GatewayClient, GatewayConfig
from copenet.probes import (
    ProbeBundle,
    ProbeSummary,
    build_runtime_probe_specs,
    classify_probe_bundle,
    render_probe_report,
    write_probe_bundle,
)
from copenet.probes.runtime_bundle import validate_debug_copy_bundle


DEFAULT_WS_URL = "ws://127.0.0.1:17123/ws"
DEFAULT_TOKEN = "dev-token"


@dataclass(frozen=True)
class Target:
    provider: str
    model: str | None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _suite_dir(base_dir: str | Path) -> Path:
    root = Path(base_dir)
    suite_dir = root / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suite_dir.mkdir(parents=True, exist_ok=True)
    return suite_dir


def _sanitize_label(value: str | None, fallback: str = "default") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)


def _default_trace_path(run_id: str | None) -> Path | None:
    if not run_id:
        return None
    data_root = Path(os.environ.get("COPNET_DATA_DIR", Path.home() / ".copenet"))
    path = data_root / "logs" / "runs" / f"{run_id}.jsonl"
    return path if path.exists() else None


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


async def _wait_for_run_record(client: GatewayClient, session_key: str, run_id: str | None) -> dict | None:
    if not run_id:
        return None
    for _ in range(40):
        record = await client.resolve_session_run(session_key, run_id)
        if isinstance(record, dict) and record:
            return record
        await asyncio.sleep(0.1)
    return None


async def _collect_runtime_truth(
    client: GatewayClient,
    *,
    session_key: str,
    run_id: str | None,
) -> tuple[dict | None, dict | None, list[dict], list[dict], dict]:
    session = await client.resolve_session(session_key)
    state = await client.resolve_session_state(session_key)
    artifacts = await client.list_session_artifacts(session_key, limit=100)
    transcript = await client.history(session_key, limit=500)
    exported = await client.export_session(session_key)
    run_record = await _wait_for_run_record(client, session_key, run_id)
    return session, state, artifacts, transcript, {"exported": exported, "run_record": run_record}


async def _run_probe(
    client: GatewayClient,
    *,
    target: Target,
    probe_name: str,
    prompt: str,
    session_key: str,
) -> tuple[str | None, str, str, int, dict[str, object] | None]:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    final_payload: dict[str, object] | None = None
    run_id: str | None = None

    async def on_started(started_run_id: str) -> None:
        nonlocal run_id
        run_id = started_run_id

    async def on_event(payload: dict[str, object]) -> None:
        nonlocal final_payload
        state = str(payload.get("state") or "")
        if state in {"final", "error", "aborted"}:
            final_payload = payload

    try:
        send_result = await client.stream_chat(
            session_key=session_key,
            message=prompt,
            idempotency_key=f"probe-{probe_name}-{uuid.uuid4().hex[:10]}",
            provider=target.provider,
            model=target.model,
            on_event=on_event,
            on_started=on_started,
        )
        run_id = run_id or str(send_result.get("runId") or "").strip() or None
        final_state = str((final_payload or {}).get("state") or send_result.get("status") or "unknown")
    except Exception as exc:
        final_state = "client_error"
        final_payload = {"errorMessage": str(exc)}

    finished_at = _now_iso()
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return run_id, started_at, finished_at, duration_ms, final_payload


def _selected_probe_names(filter_value: str | None) -> set[str] | None:
    if not filter_value:
        return None
    names = {item.strip() for item in filter_value.split(",") if item.strip()}
    return names or None


async def _execute_probe_suite(
    client: GatewayClient,
    *,
    targets: list[Target],
    suite_dir: Path,
    selected_names: set[str] | None,
    repeats: int,
    expect_trace: bool,
) -> ProbeSummary:
    bundles: list[ProbeBundle] = []
    specs = build_runtime_probe_specs()

    for target in targets:
        print(f"\nRunning probes for {target.provider} / {target.model or '(default)'}")
        for repeat_index in range(repeats):
            session_groups: dict[str, str] = {}
            previous_in_group: dict[str, ProbeBundle] = {}
            for spec in specs:
                if selected_names is not None and spec.name not in selected_names:
                    continue
                if spec.session_group:
                    session_key = session_groups.setdefault(
                        spec.session_group,
                        f"probe-{target.provider}-{_sanitize_label(target.model)}-{spec.session_group}-{repeat_index + 1}-{uuid.uuid4().hex[:6]}",
                    )
                    previous_bundle = previous_in_group.get(spec.session_group)
                else:
                    session_key = (
                        f"probe-{target.provider}-{_sanitize_label(target.model)}-{spec.name}-{repeat_index + 1}-{uuid.uuid4().hex[:6]}"
                    )
                    previous_bundle = None

                run_id, started_at, finished_at, duration_ms, final_payload = await _run_probe(
                    client,
                    target=target,
                    probe_name=spec.name,
                    prompt=spec.prompt,
                    session_key=session_key,
                )
                session, state, artifacts, transcript, runtime = await _collect_runtime_truth(
                    client,
                    session_key=session_key,
                    run_id=run_id,
                )
                exported = runtime["exported"] if isinstance(runtime, dict) else {}
                run_record = runtime.get("run_record") if isinstance(runtime, dict) else None
                trace_path = str(_default_trace_path(run_id)) if _default_trace_path(run_id) is not None else None

                classification = classify_probe_bundle(
                    probe=spec,
                    run_record=run_record if isinstance(run_record, dict) else None,
                    transcript=transcript,
                    artifacts=artifacts,
                    trace_path=trace_path,
                    previous_bundle=previous_bundle,
                )

                bundle = ProbeBundle(
                    provider=target.provider,
                    model=target.model,
                    probe_name=spec.name,
                    prompt=spec.prompt,
                    session_key=session_key,
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    session=session,
                    run_record=run_record if isinstance(run_record, dict) else None,
                    session_state=state,
                    artifacts=artifacts,
                    transcript=transcript,
                    transcript_markdown=str((exported or {}).get("markdown") or ""),
                    trace_path=trace_path,
                    raw_final_payload=final_payload,
                    notes={"repeat_index": repeat_index + 1},
                    **classification,
                )

                if spec.validate_debug_copy:
                    copied_session = await client.debug_copy_session(session_key)
                    copied_history = await client.history(copied_session["key"], limit=500)
                    copied_state = await client.resolve_session_state(copied_session["key"])
                    copied_artifacts = await client.list_session_artifacts(copied_session["key"], limit=100)
                    copied_runs = await client.list_session_runs(copied_session["key"], limit=100)
                    bundle.debug_copy_validation = validate_debug_copy_bundle(
                        original_transcript=transcript,
                        original_artifacts=artifacts,
                        original_runs=await client.list_session_runs(session_key, limit=100),
                        original_state=state,
                        copied_session=copied_session,
                        copied_transcript=copied_history,
                        copied_artifacts=copied_artifacts,
                        copied_runs=copied_runs,
                        copied_state=copied_state,
                    )

                if expect_trace and not bundle.trace_present:
                    bundle.classification = "runtime_error"
                    bundle.status = "missing_trace"

                write_probe_bundle(suite_dir, bundle)
                print(
                    f"  - {spec.name}: {bundle.classification} "
                    f"({bundle.tool_step_count} steps, {bundle.duration_ms}ms)"
                )
                bundles.append(bundle)
                if spec.session_group:
                    previous_in_group[spec.session_group] = bundle

    summary = ProbeSummary(
        generated_at=_now_iso(),
        suite_dir=str(suite_dir),
        targets=[{"provider": target.provider, "model": target.model} for target in targets],
        results=bundles,
    )
    (suite_dir / "summary.json").write_text(json.dumps(summary.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (suite_dir / "report.md").write_text(render_probe_report(summary), encoding="utf-8")
    return summary


def _print_summary(summary: ProbeSummary) -> None:
    print("\n=== RUNTIME PROBE SUMMARY ===")
    print(f"{'provider':12s} {'model':28s} {'probe':28s} {'classification':30s} {'steps':>5s} {'ms':>6s}")
    print("-" * 128)
    for row in summary.to_json()["results"]:
        model = row["model"] or "(default)"
        print(
            f"{row['provider'][:12]:12s} "
            f"{model[:28]:28s} "
            f"{row['probe_name'][:28]:28s} "
            f"{row['classification'][:30]:30s} "
            f"{row['tool_step_count']:5d} "
            f"{row['duration_ms']:6d}"
        )
    print(f"\nBundle root: {summary.suite_dir}")
    print(f"Summary: {Path(summary.suite_dir) / 'summary.json'}")
    print(f"Report: {Path(summary.suite_dir) / 'report.md'}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run live CopeNet runtime probes and export durable bundle artifacts.")
    parser.add_argument("--ws-url", default=os.environ.get("COPNET_WS_URL", DEFAULT_WS_URL))
    parser.add_argument("--token", default=os.environ.get("COPNET_TOKEN", DEFAULT_TOKEN))
    parser.add_argument("--providers", default="codex-cli,lm-studio")
    parser.add_argument("--lm-model", default=os.environ.get("COPNET_LM_MODEL"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "tmp" / "probe_runs"))
    parser.add_argument("--probes", default=None, help="Comma-separated subset of probe names to run.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--expect-trace", action="store_true", help="Treat missing trace files as a runtime error.")
    args = parser.parse_args()

    client = GatewayClient(GatewayConfig(url=args.ws_url, token=args.token))
    targets = await _resolve_targets(client, args.providers, args.lm_model)
    if not targets:
        raise SystemExit("No runnable targets found. Check provider availability and --providers/--lm-model options.")

    suite_dir = _suite_dir(args.output_dir)
    selected_names = _selected_probe_names(args.probes)
    summary = await _execute_probe_suite(
        client,
        targets=targets,
        suite_dir=suite_dir,
        selected_names=selected_names,
        repeats=max(args.repeats, 1),
        expect_trace=bool(args.expect_trace),
    )
    _print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main())
