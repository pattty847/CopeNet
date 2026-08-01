"""Trace scenario runner for CopeNet trace inspection.

Exercises a small scenario pack against a running CopeNet server and prints
the run id for each scenario so traces can be located quickly.

Usage:
    cd /path/to/CopeNet
    uv run python scripts/trace_scenarios.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
import os

import websockets

WS_URL = "ws://127.0.0.1:17123/ws"
TOKEN = "dev-token"


async def _connect(ws: websockets.WebSocketClientProtocol) -> None:
    while True:
        raw = await ws.recv()
        frame = json.loads(raw)
        if frame.get("event") == "connect.challenge":
            req_id = f"connect-{uuid.uuid4().hex[:6]}"
            await ws.send(
                json.dumps(
                    {
                        "type": "req",
                        "id": req_id,
                        "method": "connect",
                        "params": {"auth": {"token": TOKEN}},
                    }
                )
            )
        if frame.get("type") == "res" and frame.get("ok") is True:
            return
        if frame.get("type") == "res" and frame.get("ok") is False:
            raise RuntimeError(f"connect failed: {frame}")


async def run_scenario(
    name: str,
    provider: str,
    message: str,
    session_key: str | None = None,
    model: str | None = None,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Run one chat scenario and return a compact summary."""
    session_key = session_key or f"trace-{uuid.uuid4().hex[:8]}"
    run_id = f"trace-run-{uuid.uuid4().hex[:10]}"

    print(f"\n[{name}]")
    print(f"  provider={provider}  session={session_key}  run_id={run_id}")
    print(f"  message: {message[:80]!r}")

    actual_run_id = run_id
    response_parts: list[str] = []
    final_state = "unknown"
    error_msg: str | None = None

    try:
        async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024) as ws:
            await _connect(ws)

            send_id = f"send-{uuid.uuid4().hex[:6]}"
            params: dict[str, Any] = {
                "sessionKey": session_key,
                "message": message,
                "idempotencyKey": run_id,
                "provider": provider,
            }
            if model:
                params["model"] = model

            await ws.send(
                json.dumps(
                    {
                        "type": "req",
                        "id": send_id,
                        "method": "chat.send",
                        "params": params,
                    }
                )
            )

            async def collect() -> None:
                nonlocal actual_run_id, final_state, error_msg
                async for raw in ws:
                    frame = json.loads(raw)
                    frame_type = frame.get("type")

                    if frame_type == "res" and frame.get("id") == send_id:
                        payload = frame.get("payload") or {}
                        if isinstance(payload, dict):
                            actual_run_id = payload.get("runId") or run_id
                            status = payload.get("status", "")
                            if status in {"in_flight", "cached"}:
                                final_state = status
                                return
                        if frame.get("ok") is False:
                            error_msg = (frame.get("error") or {}).get("message", "unknown error")
                            final_state = "rpc_error"
                            return
                        continue

                    if frame_type == "event" and frame.get("event") == "chat":
                        payload = frame.get("payload") or {}
                        state = payload.get("state", "")
                        if state == "delta":
                            message_payload = payload.get("message") or {}
                            if isinstance(message_payload, dict):
                                response_parts.append(message_payload.get("content") or "")
                        elif state in {"final", "error", "aborted"}:
                            final_state = state
                            if state == "error":
                                error_msg = payload.get("errorMessage")
                            return

            await asyncio.wait_for(collect(), timeout=timeout)

    except asyncio.TimeoutError:
        final_state = "timeout"
        error_msg = f"timed out after {timeout}s"
    except Exception as exc:  # pragma: no cover - debug helper
        final_state = "client_error"
        error_msg = str(exc)

    response_preview = "".join(response_parts)[:200]
    result = {
        "name": name,
        "run_id": actual_run_id,
        "state": final_state,
        "response_preview": response_preview,
        "error": error_msg,
    }
    print(f"  -> state={final_state}  run_id={result['run_id']}")
    if error_msg:
        print(f"  -> error: {error_msg}")
    if response_preview:
        print(f"  -> response: {response_preview[:120]!r}")
    return result


async def main() -> None:
    scenarios = [
        {
            "name": "S5-LMStudio-chat-only",
            "provider": "lm-studio",
            "message": "What are Python source files typically named? Give a one-sentence answer.",
        },
        {
            "name": "S6-LMStudio-filesystem-question",
            "provider": "lm-studio",
            "message": "List the Python files you would expect to find in a FastAPI project. Give a brief list.",
        },
        {
            "name": "S7-Ollama-chat-only",
            "provider": "ollama",
            "message": "What is Python? Give a one-sentence answer.",
        },
        {
            "name": "S1-Codex-tool-assisted",
            "provider": "codex-cli",
            "message": "List the Python files in this repo.",
            "timeout": 10.0,
        },
        {
            "name": "S2-Codex-blocked-path",
            "provider": "codex-cli",
            "message": "Read /etc/passwd and summarize it.",
            "timeout": 10.0,
        },
        {
            "name": "S3-Codex-shell-allowlist-success",
            "provider": "codex-cli",
            "message": "Run: echo hello",
            "timeout": 10.0,
        },
        {
            "name": "S4-Codex-shell-allowlist-rejection",
            "provider": "codex-cli",
            "message": "Run: rm -rf /tmp/foo",
            "timeout": 10.0,
        },
    ]

    results = []
    for scenario in scenarios:
        timeout = scenario.pop("timeout", 90.0)
        results.append(await run_scenario(**scenario, timeout=timeout))

    print("\n=== SCENARIO SUMMARY ===")
    for result in results:
        tag = "OK" if result["state"] == "final" else "SKIP/ERR"
        print(f"  [{tag}] {result['name']:40s} run_id={result['run_id']}  state={result['state']}")

    print("\n=== TRACE FILES ===")
    trace_dir = Path(os.environ.get("COPNET_DATA_DIR", Path.home() / ".copenet")) / "logs" / "runs"
    if trace_dir.exists():
        recent = sorted(trace_dir.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)[:20]
        for file_path in recent:
            print(f"  {file_path.name}  ({file_path.stat().st_size} bytes)")
    else:
        print(f"  Trace dir not found: {trace_dir}")


if __name__ == "__main__":
    asyncio.run(main())
