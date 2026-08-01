#!/usr/bin/env python3
"""Codex Responses API probe.

Verifies that the chatgpt.com/backend-api/codex/responses endpoint (the
ChatGPT-subscription-backed Codex Responses API) accepts the multi-turn
input shapes, native tools, and reasoning options that the CopeNet
harness rebuild plans to use.

Usage:
    uv run python scripts/codex_responses_probe.py

Outputs:
    tmp/codex_responses_probe/scenario-{a,b,c}-events.jsonl
    tmp/codex_responses_probe/summary.json
"""

from __future__ import annotations

import argparse
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
    / "tmp/codex_responses_probe"
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


def scenario_d_payload() -> dict:
    """CopeNet's EXACT outgoing payload, built by the real harness code.

    Confirms the live endpoint accepts the params CopeNet adds that scenarios
    A-C did not test: parallel_tool_calls, tool_choice, prompt_cache_key,
    tools WITHOUT strict, and the default reasoning block. If this scenario
    fails where B/C pass, the offending field is one of those.
    """
    from copenet.core.harness.tool_loop import DEFAULT_RESPONSES_REASONING
    from copenet.core.tools import ToolDescriptor, build_responses_tool_schemas
    from copenet.providers.openai_codex import _build_responses_payload

    tools = build_responses_tool_schemas(
        [
            ToolDescriptor(
                id="files.read",
                name="Read File",
                description="Read a text file inside the current workdir.",
                category="repo-read",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                },
                capabilities=["filesystem", "read"],
                evidence_role="grounding",
                side_effect="read",
            ),
            ToolDescriptor(
                id="shell.exec",
                name="Shell Exec",
                description="Run a shell command in the current workdir.",
                category="shell-read",
                input_schema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
                capabilities=["shell", "read"],
                evidence_role="verification",
                side_effect="external",
            ),
        ]
    )
    messages = [
        {"role": "user", "content": [{"type": "input_text", "text": "What's in foo.txt?"}]},
        {
            "type": "function_call",
            "id": "fc_probe_d_0",
            "call_id": "call_probe_d_0",
            "name": "files.read",
            "arguments": "{\"path\":\"foo.txt\"}",
        },
        {"type": "function_call_output", "call_id": "call_probe_d_0", "output": "FILE CONTENTS: hello world"},
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_probe_d_0",
            "content": [{"type": "output_text", "text": "foo.txt says hello world.", "annotations": []}],
            "status": "completed",
        },
        {"role": "user", "content": [{"type": "input_text", "text": "Now read bar.txt and tell me what changed."}]},
    ]
    return _build_responses_payload(
        model=MODEL,
        messages=messages,
        instructions="You are CopeNet's coding assistant.",
        tools=tools,
        prompt_cache_key="probe-session-d",
        reasoning=DEFAULT_RESPONSES_REASONING,
        parallel_tool_calls=True,
    )


def scenario_e_payload() -> dict:
    """E: substantive prompt + summary='auto' (no include). Tests whether
    summary alone unlocks streamed reasoning_summary_text.delta events."""
    from copenet.providers.openai_codex import _build_responses_payload
    messages = [{
        "role": "user",
        "content": [{"type": "input_text", "text": "Write three sentences explaining the tradeoffs of quicksort vs mergesort. Think carefully first."}],
    }]
    return _build_responses_payload(
        model=MODEL,
        messages=messages,
        instructions="You are a careful technical writer.",
        tools=None,
        prompt_cache_key="probe-session-e",
        reasoning={"effort": "medium", "summary": "auto"},
        parallel_tool_calls=True,
    )


def scenario_f_payload() -> dict:
    """F: scenario E + include=['reasoning.encrypted_content']. Mirrors what
    OpenClaw sends. If E shows no reasoning events but F does, the include
    field is the gate."""
    from copenet.providers.openai_codex import _build_responses_payload
    messages = [{
        "role": "user",
        "content": [{"type": "input_text", "text": "Write three sentences explaining the tradeoffs of quicksort vs mergesort. Think carefully first."}],
    }]
    return _build_responses_payload(
        model=MODEL,
        messages=messages,
        instructions="You are a careful technical writer.",
        tools=None,
        prompt_cache_key="probe-session-f",
        reasoning={"effort": "medium", "summary": "auto", "include_encrypted": True},
        parallel_tool_calls=True,
    )


def scenario_g_payload() -> dict:
    """G: scenario F with summary='detailed' (what OpenClaw's most verbose mode
    uses). If F is empty but G has events, the value matters too."""
    from copenet.providers.openai_codex import _build_responses_payload
    messages = [{
        "role": "user",
        "content": [{"type": "input_text", "text": "Write three sentences explaining the tradeoffs of quicksort vs mergesort. Think carefully first."}],
    }]
    return _build_responses_payload(
        model=MODEL,
        messages=messages,
        instructions="You are a careful technical writer.",
        tools=None,
        prompt_cache_key="probe-session-g",
        reasoning={"effort": "high", "summary": "detailed", "include_encrypted": True},
        parallel_tool_calls=True,
    )


def scenario_h_payload() -> dict:
    """H: substantive prompt + tools + summary=auto. Does the presence of
    tools suppress reasoning summary deltas at the auto tier?"""
    from copenet.core.tools import ToolDescriptor, build_responses_tool_schemas
    from copenet.providers.openai_codex import _build_responses_payload
    tools = build_responses_tool_schemas([
        ToolDescriptor(
            id="files.read", name="Read", description="Read a file",
            category="repo-read", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            capabilities=["filesystem"], evidence_role="grounding", side_effect="read",
        ),
    ])
    return _build_responses_payload(
        model=MODEL,
        messages=[{"role": "user", "content": [{"type": "input_text", "text": "Plan how you would read README.md and summarize CopeNet's architecture. Think first."}]}],
        instructions="You are a careful coding assistant.",
        tools=tools, prompt_cache_key="probe-session-h",
        reasoning={"effort": "medium", "summary": "auto"},
        parallel_tool_calls=True,
    )


def scenario_i_payload() -> dict:
    """I: substantive prompt + tools + summary=detailed. If H is empty but
    I has reasoning, tools-mode requires detailed."""
    from copenet.core.tools import ToolDescriptor, build_responses_tool_schemas
    from copenet.providers.openai_codex import _build_responses_payload
    tools = build_responses_tool_schemas([
        ToolDescriptor(
            id="files.read", name="Read", description="Read a file",
            category="repo-read", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            capabilities=["filesystem"], evidence_role="grounding", side_effect="read",
        ),
    ])
    return _build_responses_payload(
        model=MODEL,
        messages=[{"role": "user", "content": [{"type": "input_text", "text": "Plan how you would read README.md and summarize CopeNet's architecture. Think first."}]}],
        instructions="You are a careful coding assistant.",
        tools=tools, prompt_cache_key="probe-session-i",
        reasoning={"effort": "medium", "summary": "detailed"},
        parallel_tool_calls=True,
    )


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the Codex Responses endpoint without printing account data.")
    parser.add_argument(
        "--scenarios",
        default="A,B,C,D,E,F,G,H,I",
        help="Comma-separated scenario labels to run (default: all).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    requested = {label.strip().upper() for label in args.scenarios.split(",") if label.strip()}
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
    print("  ok")
    print()

    scenarios = [
        ("A", "Multi-turn input array (no tools, no reasoning)", scenario_a_payload()),
        ("B", "Single user + tools array (native function calling)", scenario_b_payload()),
        ("C", "Multi-turn w/ prior function_call + function_call_output + reasoning", scenario_c_payload()),
        ("D", "CopeNet's EXACT payload (parallel_tool_calls, tool_choice, prompt_cache_key, no-strict tools, reasoning)", scenario_d_payload()),
        ("E", "Substantive prompt + summary='auto' (no include)", scenario_e_payload()),
        ("F", "Substantive prompt + summary='auto' + include=encrypted_content", scenario_f_payload()),
        ("G", "Substantive prompt + summary='detailed' + effort='high' + include=encrypted_content", scenario_g_payload()),
        ("H", "Substantive prompt + tools + summary='auto'", scenario_h_payload()),
        ("I", "Substantive prompt + tools + summary='detailed'", scenario_i_payload()),
    ]

    summary: dict[str, dict] = {}
    for label, description, payload in scenarios:
        if label not in requested:
            continue
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
