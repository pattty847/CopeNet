# Harness Transparency Gaps

What the harness/runtime knows that the wrapped model is never told. Traced to the three feed-back sinks:

- `_native_tool_message_content()` (`tool_loop.py:773-777`) — native Chat Completions loop (`:288-294`) and Responses loop (`:494-499`)
- `to_prompt_payload()` (`contracts.py:141-155`) — prompted loop (`tool_loop.py:626`)
- the system-prompt composers (`tool_loop.py:780-799, 963-1045`)

## The structural asymmetry that amplifies everything below

| Channel | ok | summary | error | body/output |
|---|---|---|---|---|
| `to_prompt_payload()` — prompted loop (weak models) | yes | yes | yes | yes |
| `_native_tool_message_content()` — native + Responses (frontier models) | no | no | no | yes |

Frontier models on the native/Responses paths get the *thinnest* result envelope. The single fix that subsumes several below: make `_native_tool_message_content` emit the `to_prompt_payload()` envelope (or at minimum merge `ok`/`error` into the body when `ok is False`) at `tool_loop.py:773-777` — one function, both loops.

**The single highest-value line in this audit:** generic handler exceptions (`registry.py:155-161` — e.g. `ValueError("pattern is required")`) produce `ToolExecutionResult` with `output={}` and `body=None`. On native/Responses paths the model receives literally the string `{}`. Fix: `output={"error": str(exc), "policyDecision": "tool_error"}`.

## 1. Output truncation

**What exists:** `MAX_TOOL_STEPS = 100` (`tool_loop.py:49`); `_DEFAULT_MODEL_FACING_RESULT_CHARS = 30000` (`:65-78`); per-tool caps in `policy.py:44-49` (`shell_output_limit` 16K/30K, `file_output_limit` 24K, etc.); the silent slices `stdout[:output_limit]` in `_shared.py:30-31,58-59`.

**What reaches the model:** this is the strongest dimension. `files.read`/`files.rg` embed explicit truncation markers with exact continuation calls (`files.py:165-169, 234-237, 346-362`); the harness backstop adds `"truncatedForModel": true` + a continuation hint pointing at the persisted artifact (`tool_loop.py:927-939`); flattened history marks its 2000-char clips (`messages.py:126`).

**Gap:** **shell output is silently truncated.** `_shared.py:30-31/:58-59` slice stdout/stderr with no marker and no flag; `shell.exec`'s output dict (`shell.py:257-263`) has no `truncated` field. A model running `git log` or a test suite treats a clipped output as complete. Secondary: `read_guidance()` clips AGENTS.md at 6000 chars silently (`_shared.py:73`); the 100-step budget is never disclosed upfront (the cap message at `tool_loop.py:92-96` arrives only after the fact, as a delta).

**Minimal fix:** have `run_command`/`run_shell_command` return truncation flags (compare pre-slice length); add `"stdoutTruncated": bool` to shell output dicts and append a literal `[stdout truncated at N chars]` marker to the clipped stream — it rides `output` to all three loop types. Disclose the budget with one line in `compose_responses_tool_instructions` (`tool_loop.py:1007-1013`).

## 2. Task mode

**What exists:** `policy_for_task_mode` (`policy.py:52-63`); `ToolExecutionContext.task_prompt_id` (`contracts.py:269`); `permission_mode` computed at `runtime.py:977` — for run-record metadata only.

**What reaches the model:** a `full-access` session gets the genuinely good `task-modes/full-access.md` overlay ("approval_required is the correct stop point, not a failure to bypass"). A **default-mode session gets nothing** — the overlay is "No additional task overlay," and the model's only hint is the shell.exec descriptor describing *both* modes without saying which is active. Guarded models never see write tools in the manifest (pre-filtered at `runtime.py:281-285`), so they discover their mode by inference from absence. Policy rejections look like: `{"policyDecision": "write_blocked", "policySummary": "Current tool mode does not allow repository write tools."}` (`registry.py:93-104`) — decent when present, but never names the lever (task mode) or the remedy (operator switches the session).

**Minimal fix:** add a `task_mode` param to `compose_responses_tool_instructions` (caller has it: `harness/__init__.py:113-117` can pass `tool_context.task_prompt_id`) with one directive line stating the active mode and what blocked calls mean; mirror in `compose_native_tool_system_prompt` (`tool_loop.py:976-988`) and `compose_prompted_tool_system_prompt` (`:780-799`). Plus the `registry.py:155-161` error-envelope fix above.

## 3. Approval gates

**What exists:** `_approval_required` (`shell.py:149-172`), the Barricade taint gate, and `_make_approval_gated_executor` (`runtime.py:39-91`) which parks on `await_tool_approval` (300s timeout) and on approve re-runs the exact call.

**What reaches the model:** the gate result does tell the model an approval concept exists (`policySummary: "High-risk full-access shell command requires operator approval before execution."`), and **resume is transparent and verified** — an approved call's re-run result flows back mid-turn as if the gate never fired.

**Gap:** the model cannot distinguish outcomes. On approval, the result is indistinguishable from instant success. On **rejection or timeout**, the model receives the *original* `approval_required` payload — identical to the pre-decision state — with no signal that a human said no, what the decision was, or that retrying is pointless. A rejected model will plausibly re-issue the same command and re-page the operator. The decision and operator note are in hand at `runtime.py:58-71` and discarded.

**Minimal fix:** in `_make_approval_gated_executor` (`runtime.py:88-89`): on approve, merge `"operatorDecision": "approved"` into the re-run output; on reject/timeout, return a copy with `{"policyDecision": "rejected_by_operator", "operatorDecision": decision, "operatorNote": note, "policySummary": "The operator <decision> this command. Do not retry it; choose a different approach or ask the user."}`. Rides the existing output channel; no loop changes.

## 4. Tool retries / repeat detection

**What exists:** `_track_tool_repetition` (`registry.py:122,187-213`) tracks consecutive identical calls registry-wide; `_repeat_response` (`files.py:466-487`) warns at 3, blocks at 4.

**What reaches the model:** good messages when they fire — the warning and block text both land in `output` ("Blocked repeated identical files.read call. Stop re-reading the same file...") and reach all paths.

**Gap:** coverage. Enforcement lives only in `files.read` and `files.rg`. A model looping `shell.exec git status` or `web.search` forty times is never warned or blocked; A-B-A-B thrash resets the counter and is invisible; the only backstop is the silent 100-step cap.

**Minimal fix:** hoist the check into `ToolRegistry.execute` right after `_track_tool_repetition` (`registry.py:122-123`): generic block at count ≥ 4 with `{"policyDecision": "repeat_blocked", "repeatCount": N}`, generic warning merge at count == 3; keep the file handlers' tool-specific phrasings as overrides or delete the duplicated plumbing.

## 5. Session context

**What exists:** `session_key`, `provider_name`, `request.model`, `entry.task_prompt_id`, `run_id`, `plan.turn_id` — all in `send_chat` scope; history capped at `limit=400` (`runtime.py:230`) with older rows silently dropped; no summarization exists yet (`messages.py:39-41` — compaction deferred); workdir in `tool_context.workdir`; identity overlay built at `runtime.py:1033-1075`.

**What reaches the model, per path:**
- **Responses:** profile + task-mode md + identity overlay + "You are CopeNet's coding agent operating in a REAL workspace rooted at {workdir}. You have working tools: {ids}..." — workdir told; session/provider/model/turn not.
- **Native Chat Completions:** only "Use provider-native tools when they help. Answer in plain text when ready." (`tool_loop.py:976-988`) — **not even the workdir.**
- **Prompted:** JSON-protocol instructions + tool schemas — no workdir either.
- **CLI providers:** `"System instructions:\n{...}\n\nUser request:\n{...}"`; on resume, only the bare new message.

**Gap:** the model doesn't know its session identity, what provider/model it's running as, its task mode (§2), the turn budget, or that history was capped at 400 rows. All of it sits in run-record metadata for the UI (`runtime.py:599-616`) and is withheld from the agent that needs it most. Pre-wired future hazard: when compaction lands, no mechanism exists to tell the model its transcript was summarized.

**Minimal fix:** one runtime-context block in `ChatHarness.run_turn` (`harness/__init__.py:88-90`), appended after `context_overlay`:

```python
runtime_context = (
    f"Runtime: CopeNet session {session_id or 'unknown'} | provider {plan.provider}"
    f"{f' model {plan.model}' if plan.model else ''} | "
    f"task mode {getattr(tool_context, 'task_prompt_id', None) or 'guarded default'} | "
    f"workdir {getattr(tool_context, 'workdir', '?')} | "
    f"tool budget {MAX_TOOL_STEPS} calls/turn."
)
```

This rides `effective_system_prompt` into all four execution paths with no per-loop changes. Add the history-cap disclosure where it's known (`runtime.py:230-243`): when `len(full_history) >= 400`, prepend `"[Older conversation history was omitted; only the most recent turns are shown.]"` — and reserve the same line for future compaction.
