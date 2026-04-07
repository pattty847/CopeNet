# CopeNet Run Tracing

CopeNet writes one structured JSONL trace per run for debugging harness, tool, provider, and response-synthesis behavior.

## Enable Tracing

Tracing is off by default.

```bash
COPNET_TRACE=1 uv run cope
```

## Where Traces Live

```
~/.copenet/logs/runs/<run-id>.jsonl
```

Override the base directory:

```bash
COPNET_DATA_DIR=/custom/path uv run cope
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

**Known gap:** `model` reflects the request field, not the provider-resolved default. If no model was specified, this field is `null`. See [TRACE-FINDINGS.md](TRACE-FINDINGS.md).

## Event Sequences

### Chat-Only Run (no tool loop)

```
run_started
session_resolved
harness_planned          willAttemptToolLoop: false
provider_turn_started    phase: "provider"
provider_session_updated (optional — provider assigned or changed session id)
provider_turn_completed  phase: "provider", deltaCount: N
assistant_finalized
run_completed
```

### Tool-Assisted Run (model emits a tool invocation)

The harness makes **two provider turns**: one to ask the model which tool to use, one to synthesize the final answer after the tool runs.

```
run_started
session_resolved
harness_planned          willAttemptToolLoop: true
provider_turn_started    phase: "tool-attempt"
provider_turn_completed  phase: "tool-attempt"
tool_requested           toolId, arguments
tool_executed            toolId, ok, summary      ← or tool_blocked
provider_turn_started    phase: "tool-follow-up"
provider_turn_completed  phase: "tool-follow-up"
assistant_finalized
run_completed
```

### Tool Loop Planned But Not Triggered

`willAttemptToolLoop: true` but the model did not emit a JSON invocation.

```
run_started
session_resolved
harness_planned          willAttemptToolLoop: true
provider_turn_started    phase: "tool-attempt"
provider_turn_completed  phase: "tool-attempt", toolRequested: false
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
  "availableToolIds": [
    "context.prepare", "files.list", "files.read",
    "files.search", "git.diff", "git.status", "shell.exec"
  ]
}
```

**Critical distinction:** `availableToolIds` is populated even when `willAttemptToolLoop: false`. The gate is `capabilityProfile.promptedToolUse`, not the presence of registered tools. If a model doesn't report `toolCalls: true` in its capabilities, the tool loop won't trigger regardless of which tools are registered.

### `provider_turn_started` / `provider_turn_completed`

`phase` values and what they mean:

| phase | when |
|---|---|
| `"provider"` | chat-only path, single provider turn |
| `"tool-attempt"` | first turn in tool loop — model decides whether to call a tool |
| `"tool-follow-up"` | second turn in tool loop — model synthesizes answer using tool result |

`provider_turn_completed` includes `deltaCount`. A value of `1` is normal for Ollama, which often returns the entire response in one chunk.

### `tool_requested`

```json
{
  "toolId": "files.read",
  "arguments": { "path": "src/copenet/tracing.py" }
}
```

Emitted when the model's output parses as a valid tool invocation JSON object. If this event is missing despite `willAttemptToolLoop: true`, the model did not produce parseable JSON — check `provider_turn_completed` for `toolRequested: false`.

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

Default shell allowlist: `git`, `rg`, `ls`, `pwd`, `find`.

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
2. **`harness_planned`** — was the tool loop planned? Was `promptedToolUse: true`?
3. **`tool_requested`** — did the model call the expected tool with correct arguments?
4. **`tool_executed` or `tool_blocked`** — policy rejection or real failure?
5. **`assistant_finalized`** — was `toolExecutionAttached` as expected? Is `responseLength` plausible?
6. **`run_failed`** — if present, the error message is the primary diagnostic

For latency: diff timestamps on `provider_turn_started` and `provider_turn_completed`. Tool-assisted runs have two such pairs.

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
