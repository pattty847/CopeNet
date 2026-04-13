# CopeNet Debugging Runbook

A quick-reference guide for diagnosing CopeNet run failures. Start here before proposing architectural changes.

## Step 0: Enable Tracing

If you haven't already:

```bash
COPNET_TRACE=1 uv run copenet
```

Traces go to `~/.copenet/logs/runs/<run-id>.jsonl`. See [TRACING.md](TRACING.md) for the full event reference.

---

## Symptom: No trace file written

**Cause:** Provider failed to initialize before the run started. The `RunTraceWriter` is created after the provider is confirmed available, so init-time errors produce no file.

**What to check:**
1. Is the provider runtime actually running? (`uv run copenet` startup logs will note init failures)
2. Check `providers.list` via the UI or client — are the expected providers listed as available?
3. Check the WebSocket event stream in the browser dev tools for the error event that was sent to the client instead.

---

## Symptom: Tool loop didn't trigger

Expected tool use but got a plain text response.

**What to check in the trace:**

```bash
jq 'select(.event == "harness_planned")' <run-id>.jsonl
```

Look at:
- `willAttemptToolLoop` — if `false`, the capability gate rejected the tool loop
- `capabilityProfile.promptedToolUse` — this must be `true` for the loop to trigger
- `capabilityProfile.toolCalls` — the provider model must report tool capability

If `willAttemptToolLoop: true` but no `tool_requested` event appeared:

```bash
jq 'select(.event == "provider_turn_completed" and .payload.phase == "tool-attempt")' <run-id>.jsonl
```

Check `toolRequested: false` — the model ran but did not emit a parseable JSON invocation.

**Common causes:**
- Model doesn't report `toolCalls: true` in its capabilities (LM Studio/Ollama model config issue)
- Model ignored the tool-use prompt and answered directly in prose
- Model output was not valid JSON — check if the response was close to the expected shape

**Fast comparison workflow:**

If you want to compare real provider/model behavior before digging through traces manually:

```bash
COPNET_TRACE=1 uv run copenet
uv run python scripts/live_probe_matrix.py --lm-model <your-lm-studio-model>
```

Then use the JSON artifact in `tmp/live_probe_results/` plus the trace files named by `runId` to compare:
- expected tool success
- expected tool block
- prose fallback / no tool requested
- resumed-session drift

---

## Symptom: Tool was blocked

**What to check in the trace:**

```bash
jq 'select(.event == "tool_blocked")' <run-id>.jsonl
```

The `payload.reason` field tells you exactly why. Known reasons:

| reason | fix |
|---|---|
| `path escapes workdir` | The model requested a path outside the configured workdir. This is expected and correct behavior — the model needs to use a relative path inside the workdir. |
| `category not allowed: <cat>` | The tool category is not in `ToolPolicy.allowed_categories`. Adjust policy if needed. |
| `command not allowed: <cmd>` | The shell command is not in `ToolPolicy.shell_allowlist`. Default: `git`, `rg`, `ls`, `pwd`, `find`. |
| `shell execution disabled by policy` | `ToolPolicy.allow_shell` is false. |
| `unknown tool` | Tool id not registered. Check `tools.list` in the UI or client. |

---

## Symptom: Provider returned an empty or truncated response

**What to check:**

```bash
jq 'select(.event == "assistant_finalized")' <run-id>.jsonl
```

- `responseLength: 0` — the provider returned no text. Check provider logs or try the same prompt directly against the provider API.
- `responseLength` looks too short — the provider may have hit a context or token limit.
- `toolExecutionAttached: false` after a tool run — the tool result may not have reached synthesis. Check if `tool_executed` appeared and what its `ok` field was.

---

## Symptom: Run failed with an error

```bash
jq 'select(.event == "run_failed")' <run-id>.jsonl
```

`payload.error` is the primary diagnostic. Common patterns:

| error | cause |
|---|---|
| `provider unavailable: <name> (<reason>)` | Provider not reachable or not configured |
| `session binding mismatch` | Request tried to change provider/model for a locked session — start a new chat |
| `session in-flight` | Another run is active for this session — wait or abort it |
| `message is required` | Empty prompt submitted |

---

## Symptom: Latency looks wrong

Tool-assisted runs make **two** provider calls. Compare timestamps:

```bash
jq 'select(.event | startswith("provider_turn"))' <run-id>.jsonl | jq -r '[.timestamp, .event, .payload.phase] | @tsv'
```

- First pair: `tool-attempt` — model decides whether to use a tool
- Second pair: `tool-follow-up` — model synthesizes the final answer

If the follow-up turn is very slow, the tool result may have been large. Check `tool_executed.summary` for output size hints.

---

## Symptom: `model: null` in traces

No model was specified in the request. The provider selected a default model but that resolved value is not currently surfaced in the trace. This is a known gap — see [TRACE-FINDINGS.md](TRACE-FINDINGS.md) F3.

Workaround: explicitly specify a model in the session or check the provider's logs for which model it used.

---

## Symptom: UI shows error but trace looks clean

Check whether `run_completed` appears with `toolExecutionAttached: true` while the UI shows an error — this can indicate a WebSocket delivery failure rather than a run failure. Also check the browser dev tools for the raw WebSocket frame.

---

## General Triage Checklist

```
[ ] Trace file exists?          → if not, provider init failed
[ ] harness_planned present?    → willAttemptToolLoop matches expectations?
[ ] tool_requested present?     → if expected but missing, model didn't parse JSON
[ ] tool_executed or blocked?   → check reason
[ ] assistant_finalized?        → responseLength and toolExecutionAttached correct?
[ ] run_completed or failed?    → run_failed.error is primary diagnostic
```

---

## Verification Commands

```bash
# syntax check all Python
python3 -m py_compile $(rg --files src/copenet -g '*.py')

# syntax check app.js
node --check src/copenet/host/static/app.js

# start server
uv run copenet

# start with tracing
COPNET_TRACE=1 uv run copenet
```
