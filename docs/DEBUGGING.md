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
- `willAttemptToolLoop` — `true` only when policy-visible tools exist and the provider/model reports native tool-call support
- `capabilityProfile.toolCalls` — the provider model must report native tool capability
- `availableToolIds` — write tools (`files.edit`, `files.write`) only appear when session
  Access is **`full-access`** (`task_prompt_id` in `policy_for_task_mode`). If the model
  tries to call writes under another Access level, traces/client payloads report
  `write tool unavailable in current mode` / `policyDecision = write_blocked`.

CLI providers (`codex-cli`, `claude-cli`) and non-native local providers stream through provider passthrough here. If they use tools internally, that is provider-managed rather than a CopeNet tool loop.

If `willAttemptToolLoop: true` but no `tool_requested` event appeared:

```bash
jq 'select(.event == "provider_turn_completed" and .payload.phase == "prompted_tool")' <run-id>.jsonl
```

Check the provider text around that pass — the model either answered directly or did not emit a parseable JSON invocation.

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

## Symptom: Tool was blocked

**What to check in the trace:**

```bash
jq 'select(.event == "tool_blocked")' <run-id>.jsonl
```

The `payload.reason` field tells you exactly why. Known reasons:

| reason | fix |
|---|---|
| `path escapes workdir` | The model requested a path outside the configured workdir. This is expected and correct behavior — the model needs to use a relative path inside the workdir. |
| `category not allowed: <cat>` | The tool category is not in `ToolPolicy.allowed_categories` for this session. |
| `command not allowed: <cmd>` | The shell command is not in `ToolPolicy.shell_allowlist`. Default: `git`, `rg`, `ls`, `pwd`, `find`. |
| `shell execution disabled by policy` | `ToolPolicy.allow_shell` is false. |
| `unknown tool` | Tool id not registered. Check `tools.list` in the UI or client. |
| `write tool unavailable in current mode` | Access is not `full-access`, so `repo-write` tools are filtered out of the manifest. Select **Full Access** or avoid write tools. |
| `artifact tool unavailable in current mode` | Reserved for narrowed policies that drop the `artifact` category. |
| `unsafe or unsupported batch request` | The batch had no read/context calls the harness could legally run together. |

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
| `session binding mismatch` | Request tried to change provider, profile, persona, or workspace for a locked session. Same-provider model and Access changes are allowed. |
| `session in-flight` | Another run is active for this session — wait or abort it |
| `message is required` | Empty prompt submitted |

---

## Symptom: Latency looks wrong

Prompted tool-assisted runs often make **multiple** provider calls. Compare timestamps:

```bash
jq 'select(.event | startswith("provider_turn"))' <run-id>.jsonl | jq -r '[.timestamp, .event, .payload.phase] | @tsv'
```

- `prompted_tool` — one tool-loop pass where the model may propose tools or answer using previous results

If a follow-up turn is very slow, the tool result may have been large. Check `tool_executed.summary` for output size hints.

---

## Symptom: `model: null` in traces

No model was specified in the request. The provider selected a default model but that
resolved value is not currently surfaced in the trace. This remains tracked in
[ROADMAP.md](plans/ROADMAP.md).

Workaround: explicitly specify a model in the session or check the provider's logs for which model it used.

---

## Symptom: Tool Activity proof looks wrong in the Agents UI

Runtime “proof” cards are derived client-side from **`SessionRunRecord.toolSteps`** (and persisted **artifacts** filtered by `runId`) in `host/frontend/src/runtime/activityProof.ts`, rendered by `ToolActivityProof.tsx`. If the backend omits `members` on a `tool.batch` step, expand **Show proof** — policy text and previews come from the normalized `toolExecution` payload on chat events.

---

## Symptom: UI shows error but trace looks clean

Check whether `run_completed` appears with `toolExecutionAttached: true` while the UI shows an error — this can indicate a WebSocket delivery failure rather than a run failure. Also check the browser dev tools for the raw WebSocket frame.

---

## General Triage Checklist

```
[ ] Trace file exists?          → if not, provider init failed
[ ] harness_planned present?    → willAttemptToolLoop + tool ids match Access (writes need full-access)?
[ ] Native tool capability?     → toolCalls must be true for CopeNet-managed tools
[ ] tool_requested present?     → if expected but missing, the model chose plain text or the provider did not expose native tool calls
[ ] tool_executed or blocked?   → check reason
[ ] assistant_finalized?        → responseLength and toolExecutionAttached correct?
[ ] run_completed or failed?    → run_failed.error is primary diagnostic
```

---

## Verification Commands

```bash
# syntax check all Python
python3 -m py_compile $(rg --files src/copenet -g '*.py')

# start server
uv run copenet

# start with tracing
COPNET_TRACE=1 uv run copenet
```
