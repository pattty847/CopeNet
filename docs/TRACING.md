# CopeNet Run Tracing

CopeNet writes one structured JSONL trace per run for debugging harness, tool, provider, and response-synthesis behavior.

## Enable Tracing

Tracing is off by default.

```bash
COPNET_TRACE=1 uv run copenet
```

## Where Traces Live

```
~/.copenet/logs/runs/<run-id>.jsonl
```

Override the base directory:

```bash
COPNET_DATA_DIR=/custom/path uv run copenet
# traces go to /custom/path/logs/runs/
```

Each run writes one file named `<run-id>.jsonl`.

**If no trace file appears:** the provider failed to initialize before `RunTraceWriter` started. The client still receives an error event — check the UI response or `providers.list` output first.

## Quick Read

```bash
# list recent runs newest-first
ls -lt ~/.copenet/logs/runs/ | head -10

# event names in order (no jq needed)
python3 -c "import sys,json; [print(json.loads(l)['event']) for l in open('$RUN')]" < <run-id>.jsonl

# if jq is available
jq -r '[.timestamp, .event] | @tsv' <run-id>.jsonl
jq 'select(.event == "harness_planned")' <run-id>.jsonl
jq 'select(.event | startswith("tool_"))' <run-id>.jsonl
```

## Event Shape

Every line is a JSON object:

```json
{
  "timestamp": "2026-04-06T12:00:00.000000+00:00",
  "event": "harness_planned",
  "runId": "abc-123",
  "sessionKey": "session-key",
  "provider": "lm-studio",
  "model": "llama-3.2-3b",
  "payload": { ... }
}
```

**Known gap:** `model` reflects the request field, not the provider-resolved default.
If no model was specified, this field may be `null`. The provider-resolved model is
tracked as open observability work in [ROADMAP.md](plans/ROADMAP.md).

## Event Sequences

### Chat-Only Run (no tool loop)

```
run_started
session_resolved
prompt_context_policy_resolved
chat_messages_built
harness_planned          willAttemptToolLoop: false
prompt_context_assembled
harness_decision_recorded status: "parsed" | "fallback" | "unavailable" (optional)
provider_turn_started    phase: "provider"
provider_session_updated (optional — provider assigned or changed session id)
provider_turn_completed  phase: "provider", deltaCount: N
assistant_finalized
run_completed
```

### Tool-Assisted Run (model emits a tool invocation)

The prompted harness makes **two or more provider turns** on the default path: each pass lets the model either emit exact JSON tool calls or answer in plain text. Native tool-call providers may use `chat_completion` instead of `provider_turn_*` trace pairs.

```
run_started
session_resolved
harness_planned          willAttemptToolLoop: true
harness_decision_recorded status: "parsed" | "fallback" | "unavailable" (optional)
provider_turn_started    phase: "prompted_tool"
provider_turn_completed  phase: "prompted_tool"
tool_requested           toolId, arguments
tool_executed            toolId, ok, summary      ← or tool_blocked
provider_turn_started    phase: "prompted_tool"
provider_turn_completed  phase: "prompted_tool"
tool_loop_continued      step, optional lastToolId, transitionReason
…                        (repeat turns while the tool loop stays active)
assistant_finalized
run_completed
```

Tool calls are normalized as exact registered tool ids plus structured arguments. Tool results also carry `turnId`, `decisionId`, and versioned `effect` metadata for UI inspection.

### Tool Loop Planned But Not Triggered

`willAttemptToolLoop: true` but the model did not emit a JSON invocation.

```
run_started
session_resolved
harness_planned          willAttemptToolLoop: true
harness_decision_recorded status: "parsed" | "fallback" | "unavailable" (optional)
provider_turn_started    phase: "prompted_tool"
provider_turn_completed  phase: "prompted_tool"
assistant_finalized
run_completed
```

### Failed Run

```
run_started
session_resolved         (may be missing if failure is in session resolve)
harness_planned          (may be missing)
run_failed               phase: "send_chat", error: "..."
```

## Key Events In Detail

### Prompt and context events

`prompt_context_policy_resolved` records the request purpose, the resolved
profile/Access ids, whether persona context, persona `AGENTS.md`, and
relevance-ranked memory were allowed, and — importantly — `systemPromptSource`.

`systemPromptSource` is `"composed"` when the orchestrator built the instructions
from `(systemPromptId, taskPromptId)`, and `"request_override"` when the caller
supplied explicit `system_prompt` text. The orchestrator is the single owner, so
every transport (WebSocket, REST, SSE, CLI, Fleet, coordination lanes) reports
`"composed"` for the same binding. A `baseSystemPromptChars` of 0 on an
interactive run means the model received no profile or Access instructions and is
always a bug.

`chat_messages_built` records the bounded and unbounded input estimates, how many
oldest provider-view message items were omitted, and the resolved budget:
`inputTokenBudget`, `modelContextTokens`, `reservedOutputTokens`, and
`budgetSource` (`model_metadata` | `provider_fallback`, optionally `_floored`).
The estimator charges text, images, reasoning, and unmodelled item shapes, so a
vision-heavy conversation reports a real size. Stored transcript entries are
never removed — the budget bounds only the provider view.

`tool_loop_input_trimmed` fires when a growing tool loop crosses the budget
mid-turn, after stale-tool-output compaction. Its absence means the turn stayed
within budget on its own.

`prompt_context_assembled` records the request purpose plus character counts for
the base system prompt, persona/context overlay, structured message payload, and
tool schemas. It never records raw prompt text.

`prompted_tool_response_interpreted` records `toolCallCount`,
`malformedBlockCount`, and `rejectedToolIds`. A reply with zero tool calls but a
non-zero `malformedBlockCount` or `rejectedToolIds` is an *attempted* call, not a
finished answer; `prompted_tool_correction_sent` follows when the harness sends
the model a corrective follow-up instead of shipping broken syntax to the user.

Purpose-tagged non-chat calls use the same safe metadata shape when their caller
supplies a trace recorder: `model_request_started` and `model_request_completed`
include the purpose, phase, size counts, and system-prompt transport. No
production caller passes a recorder yet, so these do not currently appear in run
traces.

### `harness_planned`

```json
{
  "capabilityProfile": {
    "provider": "lm-studio",
    "model": "llama-3.2-3b",
    "chat": true,
    "toolCalls": true,
    "streaming": true,
    "promptedToolUse": true
  },
  "willAttemptToolLoop": true,
  "turnId": "turn-...",
  "decisionId": "decision-...",
  "availableToolIds": [
    "files.edit",
    "files.read",
    "files.rg",
    "files.write",
    "market.backtest",
    "market.compare",
    "market.dashboard",
    "market.evidence",
    "market.ticker",
    "memory.read",
    "memory.write",
    "persona.author",
    "plan.write",
    "shell.exec",
    "user.remember",
    "web.fetch",
    "web.search"
  ]
}
```

**Critical distinction:** `availableToolIds` is populated even when `willAttemptToolLoop: false`. The gate is `capabilityProfile.promptedToolUse`, not the presence of registered tools. If a model doesn't report `toolCalls: true` in its capabilities, the tool loop won't trigger regardless of which tools are registered.

**Concrete tool list:** Registered built-ins live in `core/tools/handlers/`; the
model-facing source of truth is `MANIFEST_TOOL_IDS` in `builtin_readonly.py`.
**Write tools (`files.edit`, `files.write`) only appear here when Access policy allows
category `repo-write`** (currently `full-access`). `artifact.create` remains registered
for internal/compatibility routing but is not offered in the model-facing manifest.

### `harness_decision_recorded`

```json
{
  "schema_version": "harness_decision_record.v1",
  "decision_id": "decision-...",
  "turn_id": "turn-...",
  "control_mode": "trace_only",
  "status": "parsed",
  "decision": {
    "request_kind": "code",
    "route": "call_tool",
    "next_action": "SEARCH_FILES",
    "trace_note": "Start by locating the implementation."
  }
}
```

This record is for trace continuity and UI inspection only. V1 does not steer, suppress, or force tool execution from `HarnessDecision`; normal provider output remains authoritative.

### `provider_turn_started` / `provider_turn_completed`

`phase` values and what they mean:

| phase | when |
|---|---|
| `"provider"` | chat-only path, single provider turn |
| `"prompted_tool"` | one prompted tool-loop pass; the model may call a tool or answer |

`provider_turn_completed` includes `deltaCount`. A value of `1` is normal for Ollama, which often returns the entire response in one chunk.

### `tool_requested`

```json
{
  "toolId": "files.read",
  "arguments": { "path": "src/copenet/tracing.py" }
}
```

Emitted when the model's output parses as a valid tool invocation JSON object with an exact registered tool id. If this event is missing despite `willAttemptToolLoop: true`, the model answered directly or did not produce parseable tool JSON.

### `tool_executed`

```json
{
  "toolId": "files.read",
  "ok": true,
  "summary": "Read file src/copenet/tracing.py.",
  "error": null
}
```

### `tool_blocked`

```json
{
  "toolId": "files.read",
  "reason": "path escapes workdir"
}
```

Known `reason` values:

| reason | cause |
|---|---|
| `path escapes workdir` | path argument resolves outside the configured workdir |
| `category not allowed: <category>` | tool category not in `ToolPolicy.allowed_categories` |
| `command not allowed: <cmd>` | shell command not in `ToolPolicy.shell_allowlist` |
| `shell execution disabled by policy` | `ToolPolicy.allow_shell` is false |
| `unknown tool` | tool id not in the registry |
| `write tool unavailable in current mode` | Registry-level block: `repo-write` category not allowed at the current Access level (not `full-access`) |
| `artifact tool unavailable in current mode` | Registry-level block: `artifact` category not allowed (reserved for narrowed policies) |
Default shell allowlist: `git`, `rg`, `ls`, `pwd`, `find`, `grep`, `head`, `cat`,
`tail`, `wc`, `tree`, `file`, `which`, `diff`.

### `assistant_finalized`

```json
{
  "responseLength": 842,
  "toolExecutionAttached": true
}
```

`toolExecutionAttached: true` means a tool execution payload was attached to the final chat event sent to the client. If this is `false` after a tool run, the tool result may not have reached the UI.

### `run_failed`

```json
{
  "phase": "send_chat",
  "error": "provider unavailable: codex-cli (binary not found)"
}
```

## Triage Order

For a full debugging playbook, see [DEBUGGING.md](DEBUGGING.md).

Quick order for an unexpected run:

1. **Find the trace** — newest file in `~/.copenet/logs/runs/`
2. **`harness_planned`** — was the tool loop planned? Was `promptedToolUse: true`? Do `availableToolIds` reflect session Access (**`full-access` needed for write tools**)?
3. **`tool_requested`** — did the model call the expected tool with correct arguments?
4. **`tool_executed` or `tool_blocked`** — policy rejection or execution failure?
5. **`assistant_finalized`** — was `toolExecutionAttached` as expected? Is `responseLength` plausible?
6. **`run_failed`** — if present, the error message is the primary diagnostic

For latency: diff timestamps on `provider_turn_started` and `provider_turn_completed`. Multi-step tool loops may have **multiple** pairs per run.

## Trace Report Format (for agents)

When filing a trace-based finding:

```
Scenario: <name>
Run ID:   <run-id>
Expected: <what should happen>
Observed: <what actually happened>
Events:   <relevant event list with payload excerpts>
Finding:  <one to two sentence summary>
```

## Cleanup

No automatic retention. Delete old trace files manually:

```bash
ls -lt ~/.copenet/logs/runs/ | head -20
rm ~/.copenet/logs/runs/<old-run-id>.jsonl
```
