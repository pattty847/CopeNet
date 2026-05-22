#!/usr/bin/env python3
"""Codex Responses API probe.

Verifies that the chatgpt.com/backend-api/codex/responses endpoint (the
ChatGPT-subscription-backed Codex Responses API) accepts the multi-turn
input shapes, native tools, and reasoning options that the CopeNet
harness rebuild plans to use.

Usage:
    uv run python scripts/codex_responses_probe.py

Outputs:
    docs/investigations/harness-rebuild/probe-results/scenario-{a,b,c}-events.jsonl
    docs/investigations/harness-rebuild/probe-results/summary.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from copenet.core.provider_auth import OpenAICodexAuthService


CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
MODEL = "gpt-5.5"
RESULTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "docs/investigations/harness-rebuild/probe-results"
)


def build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "originator": "copenet-probe",
        "User-Agent": "copenet-probe/0.1",
    }


def stream_request(payload: dict, token: str, sink_path: Path) -> dict:
    """POST to Codex Responses, write each SSE event to sink_path, return summary."""
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(CODEX_URL, data=body, headers=build_headers(token), method="POST")

    event_counts: dict[str, int] = {}
    text_deltas: list[str] = []
    function_calls: list[dict] = []
    reasoning_deltas: list[str] = []
    errors: list[dict] = []
    response_completed: dict | None = None

    try:
        with request.urlopen(req, timeout=120.0) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            raw_body = response.read().decode("utf-8", errors="replace")

        # Save the raw body alongside parsed events for debugging.
        sink_path.with_suffix(".raw.txt").write_text(raw_body, encoding="utf-8")

        # The Codex endpoint returns SSE format whether or not Content-Type
        # announces it. Detect by looking for data: lines in the body itself.
        sse_lines = [line for line in raw_body.splitlines() if line.startswith("data:")]
        if not sse_lines:
            return {
                "status": "non_sse_response",
                "content_type": content_type,
                "body_preview": raw_body[:1500],
            }

        with sink_path.open("w", encoding="utf-8") as sink:
            for line in sse_lines:
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue

                sink.write(json.dumps(event, ensure_ascii=False) + "\n")
                event_type = str(event.get("type") or "")
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

                if event_type == "response.output_text.delta":
                    text_deltas.append(str(event.get("delta") or ""))
                elif event_type == "response.output_item.added":
                    item = event.get("item") or {}
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        function_calls.append(
                            {
                                "id": item.get("id"),
                                "call_id": item.get("call_id"),
                                "name": item.get("name"),
                                "arguments": str(item.get("arguments") or ""),
                            }
                        )
                elif event_type == "response.function_call_arguments.delta":
                    if function_calls:
                        function_calls[-1]["arguments"] = (
                            function_calls[-1].get("arguments") or ""
                        ) + str(event.get("delta") or "")
                elif event_type in (
                    "response.reasoning_summary.delta",
                    "response.reasoning_summary_text.delta",
                ):
                    reasoning_deltas.append(str(event.get("delta") or ""))
                elif event_type == "response.completed":
                    completed = event.get("response")
                    if isinstance(completed, dict):
                        response_completed = completed
                elif event_type in ("response.failed", "error"):
                    errors.append(event)

    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        return {
            "status": "http_error",
            "code": exc.code,
            "reason": str(exc.reason),
            "detail": detail[:1500],
        }
    except error.URLError as exc:
        return {"status": "url_error", "reason": str(exc.reason)}

    return {
        "status": "ok",
        "event_counts": event_counts,
        "text_total": "".join(text_deltas),
        "function_calls": function_calls,
        "reasoning_total": "".join(reasoning_deltas),
        "errors": errors,
        "response_completed_keys": sorted(list(response_completed.keys())) if response_completed else None,
    }


def scenario_a_payload() -> dict:
    """Multi-turn input array. No tools, no reasoning. Tests basic multi-message input."""
    return {
        "model": MODEL,
        "stream": True,
        "store": False,
        "instructions": "You are a friendly arithmetic assistant. Answer in one word.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "What's 2+2?"}]},
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_probe_a_0",
                "content": [{"type": "output_text", "text": "4", "annotations": []}],
                "status": "completed",
            },
            {"role": "user", "content": [{"type": "input_text", "text": "And 3+3?"}]},
        ],
    }


def scenario_b_payload() -> dict:
    """Single user message + tools array. Tests native function calling."""
    return {
        "model": MODEL,
        "stream": True,
        "store": False,
        "instructions": "You are a weather assistant. Use the get_weather tool when asked about weather.",
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "What's the weather in San Francisco?"}],
            }
        ],
        "tools": [
            {
                "type": "function",
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ],
    }


def scenario_c_payload() -> dict:
    """Full multi-turn: prior function_call + function_call_output + new user + reasoning."""
    return {
        "model": MODEL,
        "stream": True,
        "store": False,
        "instructions": "You read files for the user. Use the read_file tool when asked about file contents.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "What's in foo.txt?"}]},
            {
                "type": "function_call",
                "id": "fc_probe_c_0",
                "call_id": "call_probe_c_0",
                "name": "read_file",
                "arguments": "{\"path\":\"foo.txt\"}",
            },
            {
                "type": "function_call_output",
                "call_id": "call_probe_c_0",
                "output": "Hello, world!",
            },
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_probe_c_0",
                "content": [
                    {"type": "output_text", "text": "foo.txt says 'Hello, world!'", "annotations": []}
                ],
                "status": "completed",
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Now what's in bar.txt?"}],
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "read_file",
                "description": "Read a text file by path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ],
        "reasoning": {"effort": "low", "summary": "auto"},
        "include": ["reasoning.encrypted_content"],
    }


def print_scenario_result(label: str, result: dict, sink_path: Path) -> None:
    status = result.get("status")
    if status == "http_error":
        print(f"  HTTP {result['code']} {result.get('reason')}")
        print(f"  detail: {result.get('detail', '')[:400]}")
        return
    if status == "url_error":
        print(f"  URL error: {result.get('reason')}")
        return
    if status == "non_sse_response":
        print(f"  Non-SSE response (content-type={result.get('content_type')})")
        print(f"  body: {result.get('body_preview', '')[:400]}")
        return

    counts = result.get("event_counts", {})
    print(f"  event types observed ({len(counts)}):")
    for ev_type, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {count:>4}  {ev_type}")
    text = result.get("text_total", "")
    if text:
        snippet = text.strip().replace("\n", " ")[:160]
        print(f"  assistant text ({len(text)} chars): {snippet!r}")
    fcs = result.get("function_calls") or []
    if fcs:
        print(f"  function_calls ({len(fcs)}):")
        for fc in fcs:
            print(f"    name={fc.get('name')} call_id={fc.get('call_id')} args={fc.get('arguments')!r}")
    reasoning = result.get("reasoning_total") or ""
    if reasoning:
        snippet = reasoning.strip().replace("\n", " ")[:200]
        print(f"  reasoning ({len(reasoning)} chars): {snippet!r}")
    errs = result.get("errors") or []
    if errs:
        print(f"  ERRORS: {json.dumps(errs)[:400]}")
    print(f"  raw events: {sink_path}")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Codex Responses API probe")
    print("=" * 60)
    print(f"Endpoint: {CODEX_URL}")
    print(f"Model:    {MODEL}")
    print(f"Results:  {RESULTS_DIR}")
    print()

    print("Authenticating...")
    auth = OpenAICodexAuthService()
    try:
        profile = auth.ensure_valid_profile()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        print("  Run: uv run copenet auth login --provider openai-codex")
        return 1
    print(f"  ok, account_id={profile.account_id}")
    print()

    scenarios = [
        ("A", "Multi-turn input array (no tools, no reasoning)", scenario_a_payload()),
        ("B", "Single user + tools array (native function calling)", scenario_b_payload()),
        ("C", "Multi-turn w/ prior function_call + function_call_output + reasoning", scenario_c_payload()),
    ]

    summary: dict[str, dict] = {}
    for label, description, payload in scenarios:
        print(f"Scenario {label}: {description}")
        sink_path = RESULTS_DIR / f"scenario-{label.lower()}-events.jsonl"
        result = stream_request(payload, profile.access_token, sink_path)
        summary[label] = {"description": description, "result": result}
        print_scenario_result(label, result, sink_path)
        print()

    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": CODEX_URL,
                "model": MODEL,
                "scenarios": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Summary written: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
