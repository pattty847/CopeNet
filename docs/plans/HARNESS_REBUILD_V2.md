# Harness Rebuild V2

**Status:** implemented architecture record. Current behavior is authoritative in code,
[ARCHITECTURE.md](../ARCHITECTURE.md), and `AGENTS.md`; unfinished cleanup belongs in
[ROADMAP.md](ROADMAP.md).

This superseded the earlier trace-only HarnessDecision patch and rebuilt the tool loop.
The temporary investigation passes and raw live-probe artifacts used during implementation
have been removed.

**Date sealed:** 2026-05-21

---

## TL;DR

Before V2, CopeNet's chat loop sent one synthetic user message per turn to a Responses
API endpoint that supported full conversation arrays and native tools. The result was no
message history, no native function calling, a four-tool cap, silent file/search clamps,
model amnesia, and keyword-scaffolded session-state mutations.

V2 replaced that loop with the live-verified pattern: build a real `input` array from
durable transcript parts, send it with native `tools`, handle streaming `function_call`
events, and inject `function_call_output` items into the next turn.

Six phases. Phase -1 is prerequisite cleanup (transcript persistence, idempotency scoping, replay schema). Phase 0 is sub-hour quick wins. Phase 1 is the message-history rebuild (the foundation). Phase 2 is the new Responses-native tool loop. Phase 3 trims the tool surface. Phase 4 lands the chat UX. Phase 5 sweeps dead code and tests. Each phase is independently shippable, reviewable, and revertable.

---

## Architecture target

```
User types in chat
    ↓
Orchestrator builds messages[] = build_chat_messages(transcript_parts, new_user_message)
    ↓
Harness sends to provider:
    POST https://chatgpt.com/backend-api/codex/responses
    {
      model, instructions, input: messages[], tools: [...],
      stream: true, store: false,
      prompt_cache_key: <session_id>,
      reasoning: {effort, summary: "auto"},
      parallel_tool_calls: true
    }
    ↓
Provider streams events:
    response.output_item.added (text | function_call | reasoning)
    response.output_text.delta            → emit assistant text delta
    response.reasoning_summary.delta      → emit thinking delta (new UX)
    response.function_call_arguments.delta → accumulate args
    response.output_item.done             → finalize item
    ↓
Tool executor runs function_call → emits function_call_output item
    ↓
Loop appends new items to in-memory messages[] and POSTs again
    ↓
On final text: append assistant message (with parts[]) to transcript
              persist run record
              done
```

Reference shapes were verified against the live subscription endpoint and are covered by
the Responses-loop integration tests. Conversation continuity uses full replay each turn.

---

## Tool surface target (Phase 3)

```
files.read   — adaptive paging with English continuation hints
files.write  — unchanged structurally; preserves expected_digest stale-write guard
files.edit   — unchanged structurally
files.rg     — offset/limit/context_lines + English pagination hints
shell.exec   — unchanged structurally; no silent stdout clamp
```

The initial rebuild exposed five primitives, down from fifteen. Approved domain tools were
added later; `MANIFEST_TOOL_IDS` is now canonical.

---

## Phase −1: Prerequisites

**Purpose:** fix the things the rest of the rebuild relies on but that the investigation only discovered late. Without these, Phase 1's message-history replay will silently lose data.

### −1.1 Transcript persistence gate

Per Codex's second-round review, runtime.py:371 currently gates the entire assistant transcript append (including `parts`) on `assistant_text` being nonempty. Tool-only or max-step turns vanish from transcript entirely.

**Change:** always append the assistant transcript message when the run produced *anything* — text OR tool_calls OR tool_results. Only skip if the run errored out before any output.

**Files:** `src/copenet/core/orchestrator/runtime.py`

**Verification:** new test in `tests/integration/test_run_records.py` — script a provider that emits only tool calls (no final text), assert the transcript has an assistant message with `parts` containing the tool exchange.

### −1.2 Idempotency cache scoping

Per Codex: `dedupe_key = f"chat:{run_id}"` is global. Same `idempotency_key` across sessions returns cached cross-session results. Fix: namespace by `(session_key, idempotency_key)`.

**Change:** 
- `dedupe_key = f"chat:{session_key}:{idempotency_key}"` (and use UUID for `run_id` if no idempotency key provided, so traces stay unique).
- Update the active-abort map to be keyed by `(session_key, run_id)` tuple instead of bare `run_id`.

**Files:** `src/copenet/core/orchestrator/runtime.py`, `src/copenet/core/orchestrator/__init__.py`

**Verification:** new test — two sessions send with same `idempotency_key`, assert no cross-session bleed.

### −1.3 RPC dispatch error boundary

Per Codex: `int("lol")` in `chat.history(limit=...)` propagates a `ValueError` out through `dispatch_rpc()` and drops the socket. Wrap dispatch with a generic exception handler that returns a structured `INVALID_REQUEST` error frame on the response for the offending request id.

**Files:** `src/copenet/host/rpc_dispatch.py`, `src/copenet/host/rpc_chat.py` (and any other RPC handlers with `int(...)`/`float(...)` on raw params)

**Verification:** test — send `{method: "chat.history", params: {sessionKey: "x", limit: "lol"}}`, assert structured error response, socket stays open.

### −1.4 Define canonical Responses item replay shape

Add a new typed module `src/copenet/core/harness/responses_items.py` that defines the exact item shapes verified in PASS-7:

```python
# Pseudo-Python — actual code in implementation
def user_input_item(text: str) -> dict: ...
def assistant_message_item(message_id: str, text: str) -> dict: ...
def function_call_item(item_id: str, call_id: str, name: str, arguments_json: str) -> dict: ...
def function_call_output_item(call_id: str, output: str) -> dict: ...

def parts_to_response_items(parts: list[dict]) -> list[dict]: ...
def transcript_to_input_array(transcript: list[dict], current_user_message: str) -> list[dict]: ...
```

This is the contract Phase 1 builds against. Schema is verified by PASS-7's live probe data.

**Files:** new — `src/copenet/core/harness/responses_items.py`

**Verification:** unit tests in `tests/unit/test_responses_items.py` — each item-shape builder produces a dict matching the captured probe events.

### −1.5 Characterization tests

Pin the current broken behavior with tests so we know when each phase fixes a thing.

**New tests:**
- "Four tools then stop": script a provider that returns 5 tool calls; assert exactly 4 execute, 5th is silently dropped (current behavior). After Phase 0 raises the cap, this test inverts to "all 5 execute."
- "Cross-turn amnesia": send two user messages, assert the second turn's provider call sends ONE user message containing a working_set blob (current behavior). After Phase 1, this test inverts to "second turn's input array contains user/assistant/user."

**Files:** `tests/integration/test_pre_rebuild_baseline.py` (new — explicitly named to signal it documents pre-rebuild behavior and most assertions will flip during the rebuild).

**Files touched in this phase (~5-6 files):**
- `src/copenet/core/orchestrator/runtime.py`
- `src/copenet/core/orchestrator/__init__.py`
- `src/copenet/host/rpc_dispatch.py`
- `src/copenet/host/rpc_chat.py`
- `src/copenet/core/harness/responses_items.py` (new)
- `tests/integration/test_pre_rebuild_baseline.py` (new)

**Expected diff:** ~250 lines added, ~30 lines changed.

**Go/no-go for Phase 0:** all new tests passing, `npx tsc --noEmit` clean, `uv run --extra dev pytest -q` green.

---

## Phase 0: Quick wins

**Purpose:** sub-hour changes that immediately reduce harness pain. Each is independently revertable. None of these depend on Phase 1+.

### 0.1 Raise tool step cap

`MAX_TOOL_STEPS` in `src/copenet/core/harness/tool_loop.py:25`: **4 → 100**.

Frontier harnesses don't impose a hard step cap on normal work — they rely on the model deciding when it's done. 100 is high enough that legitimate work never hits it, low enough that runaway loops eventually stop.

Also: change the loop-end behavior so that when the cap IS hit, the assistant message includes a clear explanation (`"[Stopped after MAX_TOOL_STEPS=100 tool calls. Returning what was produced so far.]"`) appended to whatever text exists. No more silent stops.

### 0.2 Kill silent file/search clamps

**`files.read`:**
- Remove `bounded_limit = min(limit, context.policy.file_output_limit)` clamp (line 195).
- If model passes explicit `limit`, honor it up to a generous safety guard (~500KB absolute max).
- If `limit` omitted, default to adaptive paging at ~64KB.
- When truncated, append English continuation hint to `content` text: `\n\n[Read truncated at line {N} (~{KB}KB). Use offset={N} to continue.]`

**`files.rg`:**
- Add `offset` and `limit` params.
- When match cap exceeded, append English hint: `\n\n[Showing matches 1-{N}. Total found: {T}. Use offset={N} to continue.]`

**Files:** `src/copenet/core/tools/handlers/files.py`, `src/copenet/core/tools/policy.py` (don't delete `file_output_limit` — repurpose as default for omitted `limit`).

### 0.3 Delete `context.prepare` tool

The implementation audit classified this as pure scaffolding. Conversation history is the
context.

**Files:**
- Delete entire `src/copenet/core/tools/handlers/context.py`
- Remove from `src/copenet/core/tools/builtin_readonly.py` registration
- Update `tests/unit/test_context_tool.py` → delete

### 0.4 Gate memory + profile auto-extraction behind config

Per Codex's round-2 finding: `memory/service.py:145+` keyword-extracts memories from phrases like "i like", "do not", "we should" and re-injects them into next-turn prompts. Same disease as `personal_history.py`. Identical fix is `profile/service.py:387` if it exhibits the same pattern.

**Change:** add an environment variable (or config field) `COPENET_AUTO_MEMORY_EXTRACTION` (default `false`). The post-run mutation block in `runtime.py` skips the call to `memory_service.extract_from_run` and `profile_service.update_from_run` when the flag is off.

**Why config flag, not deletion:** the feature might be useful later when redesigned with explicit user opt-in. Keep the code, gate the invocation. Default off prevents prompt pollution during the rebuild and operator validation.

**Files:** `src/copenet/core/orchestrator/runtime.py`, plus a small `src/copenet/core/_config.py` or env-var helper module.

**Files touched in this phase (~6-8 files):**
- `src/copenet/core/harness/tool_loop.py`
- `src/copenet/core/tools/handlers/files.py`
- `src/copenet/core/tools/policy.py`
- `src/copenet/core/tools/handlers/context.py` (deleted)
- `src/copenet/core/tools/builtin_readonly.py`
- `src/copenet/core/orchestrator/runtime.py`
- Small env-var/config helper (new)

**Expected diff:** ~150 lines changed/added, ~120 lines deleted.

**Verification:**
- The "four tools then stop" baseline test inverts: now 100 tools execute.
- New test: model requests `files.read limit=50000`, gets 50000 chars.
- New test: model requests `files.read` with no limit on a large file, gets adaptive page + continuation hint.
- New test: `COPENET_AUTO_MEMORY_EXTRACTION=false` (default) — assert no memory writes after a run that contains "i like" trigger words.

**Go/no-go for Phase 1:** all Phase 0 tests passing, no regressions on existing green tests after the trims.

---

## Phase 1: Real message history

**Purpose:** replace the synthetic `working_set.prompt` blob with a proper `messages[]` array built from the transcript. The foundation everything else depends on.

### 1.1 New module: `build_chat_messages`

In `src/copenet/core/orchestrator/messages.py` (new file):

```python
def build_chat_messages(
    *,
    transcript_messages: list[TranscriptMessage],
    current_user_message: str,
    max_context_tokens: int | None = None,
) -> list[dict]:
    """Walk transcript parts and produce a Responses-API input array."""
    items: list[dict] = []
    for msg in transcript_messages:
        if msg.role == "user":
            items.append(responses_items.user_input_item(msg.content))
        elif msg.role == "assistant":
            if msg.parts:
                items.extend(responses_items.parts_to_response_items(msg.parts, msg.run_id))
            elif msg.content:
                items.append(responses_items.assistant_message_item(msg.run_id, msg.content))
    items.append(responses_items.user_input_item(current_user_message))
    # max_context_tokens TBD — for now, no compaction. Token budget defer to Phase 6+.
    return items
```

Uses the typed item builders from Phase −1.4. No keyword extraction. No state synthesis. Just transcript → API items.

### 1.2 Wire into orchestrator

Replace `runtime.py:154-162` (`assemble_working_set` call) with `build_chat_messages` call. Pass the resulting `messages[]` to the harness via a new `messages: list[dict]` parameter (alongside or replacing the existing `prompt: str`).

For Phase 1, the harness signature change is additive — `prompt` stays for the prompted-tool loop (LM Studio / Ollama), `messages` is added for the new Responses path. Phase 2 will route openai-codex through `messages`.

### 1.3 Delete the synthetic working_set

- Delete `src/copenet/core/orchestrator/working_set.py` entirely
- Delete the session_state mutation block in `runtime.py:667-720` (the part that updates `task_summary`, `active_entities`, `prior_decisions`, etc.)
- Delete `src/copenet/core/orchestrator/personal_history.py` entirely
- Narrow `SessionStateRecord` to: `session_key`, `relevant_asset_ids`, `relevant_artifact_ids`, `merge_state`, `pulse_state`, `created_at`, `updated_at`. Everything else dies.

The implementation audit found that Pulse and Merge could degrade gracefully; they were
deferred for a later rewire.

### 1.4 Update RunRecord shape

`RunRecord.working_set` field (`runs.py:54`) becomes obsolete. Replace with `message_count: int` and `input_token_estimate: int` for trace/inspector value. Frontend `RunRecord.workingSet` type goes away.

### 1.5 Tests

- New: `test_build_chat_messages.py` — given a transcript with text+tool_call+tool_result parts, assert the produced `messages[]` matches the canonical Responses item shape.
- New: round-trip test — run a 3-turn scripted session, verify the third turn's outgoing messages contains items from turns 1 and 2.
- Delete: `test_working_set.py`, `test_personal_history.py`.
- Trim: `test_state_store.py` (remove asserts on killed fields), `test_run_store.py` (remove `working_set` asserts).

**Files touched in this phase (~12-15 files):**
- `src/copenet/core/orchestrator/messages.py` (new, ~80 lines)
- `src/copenet/core/orchestrator/runtime.py` (edit)
- `src/copenet/core/orchestrator/working_set.py` (delete)
- `src/copenet/core/orchestrator/personal_history.py` (delete)
- `src/copenet/core/sessions/state_store.py` (narrow)
- `src/copenet/core/runtime/runs.py` (narrow)
- `src/copenet/core/harness/__init__.py` (signature)
- Tests: new + 2 deletes + 4 trims

**Expected diff:** ~400 lines added (mostly tests), ~600 lines deleted.

**Coordination point:** frontend `RunRecord.workingSet` consumers need to be updated in Phase 4. For Phase 1, leave the field as empty dict on the wire. Don't break the frontend yet.

**Verification:**
- "Cross-turn amnesia" baseline test inverts: turn 2 input array contains turn 1 user+assistant.
- All round-trip tests pass.
- Manual probe: run `uv run copenet chat send` two turns in a row on the standing probe session, verify in trace logs that turn 2's outgoing payload has multi-message input.

**Go/no-go for Phase 2:** Phase 1 tests green. Manual probe confirms multi-turn replay actually goes out the wire. No regressions on Pulse/Merge tests (they should degrade output but not error).

---

## Phase 2: Native Responses-API tool loop

**Purpose:** stop parsing JSON out of assistant text. Use the native `tools` field. Handle the streaming `function_call` event lifecycle directly. The architectural unlock confirmed in PASS-7.

### 2.1 New loop: `run_with_responses_tools`

In `src/copenet/core/harness/tool_loop.py`, add a new function alongside the existing prompted loop:

```python
async def run_with_responses_tools(
    *,
    provider: ResponsesProvider,
    messages: list[dict],
    abort_event: asyncio.Event,
    model: str | None,
    instructions: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    session_id: str,            # for prompt_cache_key
    trace: TraceRecorder | None,
) -> AsyncIterator[ProviderEvent]:
    """Native Responses API tool loop. Streams function_call events,
    executes tools, appends function_call_output to messages, iterates."""
    ...
```

The loop:
1. Build `tools[]` from `plan.tools` using a new `build_responses_tool_schemas()` helper.
2. POST the messages + tools to the provider, stream the response.
3. Watch for `response.output_item.added` events with `item.type == "function_call"`. Accumulate `function_call_arguments.delta` chunks. On `output_item.done`, hand off to the tool executor.
4. After tool execution, append the `function_call` item (with completed arguments) AND the `function_call_output` item to the in-memory `messages[]`.
5. POST again. Loop.
6. On any `response.output_item` with `type: "message"` (assistant text), stream those text deltas through normally. When the response completes without further function calls, finalize.

Reasoning summary events (`response.reasoning_summary.delta`) emit a new `reasoning_delta` provider event for the frontend.

### 2.2 Delete the dead `run_with_native_tools`

Per Codex's first-round finding: the existing `run_with_native_tools` is Chat Completions-shaped (`provider.chat_completion(messages, tools)` → `choices[0].message.tool_calls`). It's not compatible with the Responses API and the only "native" provider (openai-codex) wasn't even using it. Dead code. Delete.

### 2.3 Flip openai-codex to native

`src/copenet/providers/openai_codex.py`:
- Change `capabilities.toolCalls` → `True`
- Rewrite `_build_payload` to accept `messages: list[dict]` instead of `prompt: str`, plus optional `tools`, `prompt_cache_key`, `reasoning`, `parallel_tool_calls` parameters.
- Send `prompt_cache_key=<session_id>` for free caching.
- Send `reasoning={effort: "high", summary: "auto"}` + `include=["reasoning.encrypted_content"]` when the harness opts in.
- Implement a streaming method (probably renamed `stream_responses(messages, tools, ...)`) that yields the full event vocabulary from PASS-7.

### 2.4 Planning update

`src/copenet/core/harness/planning.py`: choose `tool_execution_mode = "responses"` when provider declares `responsesApi: true` (new capability flag). Otherwise fall back to `prompted` (LM Studio/Ollama) or `none`.

### 2.5 Keep prompted-tool loop alive (for now)

`run_with_prompted_tools` stays for LM Studio/Ollama path. Deprioritized but functional. Per your "local models won't be used in the harness yet" call, we leave it alone. Will likely get cleaned up in a later pass once the Responses path is solid.

### 2.6 Tests

- New: `test_responses_tool_loop.py` — script a provider that returns the captured PASS-7 event stream for scenario B/C; assert tool calls are extracted, executed, and the next request includes `function_call_output` items.
- Modify: `test_tool_loop.py` — remove or update tests pinned to the dead `run_with_native_tools`.
- New: integration test using a recorded fixture of real Codex Responses events.

**Files touched in this phase (~6-8 files):**
- `src/copenet/core/harness/tool_loop.py` (large edit)
- `src/copenet/core/harness/planning.py` (small edit)
- `src/copenet/core/harness/capabilities.py` (new capability flag)
- `src/copenet/providers/openai_codex.py` (rewrite)
- Tests: 1-2 new, 1-2 modified

**Expected diff:** ~600 lines added, ~200 lines deleted.

**Coordination point:** the new `reasoning_delta` provider event needs a wsClient handler (Phase 4). For Phase 2, the event flows through but the frontend doesn't yet render it visibly. That's fine — backend ships first, frontend catches up.

**Verification:**
- Live probe: use the standing probe session `69696469` with `openai-codex / gpt-5.5`. Send a non-trivial task. Verify in trace logs: the outgoing payload has `tools[]`, the response stream contains `function_call` events, the tool is executed, and the second loop iteration includes `function_call_output` in `input[]`.
- Native tool execution end-to-end works.

**Go/no-go for Phase 3:** Phase 2 tests green. Live probe confirms native function calling actually runs against the real endpoint with real tools. Trace logs show the expected event vocabulary.

---

## Phase 3: Tool surface trim

**Purpose:** drop the redundant/vestigial tools and polish the initial five primitives.

### 3.1 Delete tool handlers

- `src/copenet/core/tools/handlers/git.py` — entire file (model uses `shell.exec git ...`)
- `src/copenet/core/tools/handlers/workspace_intel.py` — entire file (`repo.map`, `test.discover` — model explores via primitives)
- `src/copenet/core/tools/handlers/context.py` — already deleted in Phase 0
- Within `files.py`: delete `files.list` (`shell.exec ls`) and `files.search` (duplicate of `files.rg`)
- Update `src/copenet/core/tools/builtin_readonly.py` registration

### 3.2 Polish `files.read`

Already partially improved in Phase 0. Phase 3 finishes the description style guide pass:
```python
description=(
    "Read a text file inside the current workdir. "
    "Supports offset (1-based line) and limit (line count). "
    "Returns content with continuation hint if truncated."
)
```
No prescriptive "use when" / "do not use when" prose.

### 3.3 Polish `files.rg`

Already paginated in Phase 0. Phase 3 adds `context_lines` param (mirrors rg's `-C` flag) and the description style guide pass.

### 3.4 Tool description style guide pass

Every kept tool's description follows the style guide from PASS-4:
- 1-2 sentences max
- Imperative
- No prescriptive nannying
- Mention key params inline
- Neutral on policy/authority

### 3.5 Optional `description` field on every tool's input schema

Add `description: {"type": "string", "description": "Brief intent for this call, shown in UI"}` to each tool's `input_schema`. System prompt instructs the model to fill it in. UI uses it as the tool chip label.

This is the "Ran Confirm provider_auth exports" pattern from Claude Code's UI — the model writes a short intent label per tool call.

### 3.6 Defer memory + artifact tools

`memory.read`, `memory.write`, `artifact.create` — leave the handlers in place but remove from the manifest registration. Comes back when we want it.

### 3.7 Delete `_repeat_response` nag system

`src/copenet/core/tools/handlers/_shared.py` `_repeat_response` is symptom-treatment for the amnesia bug. With Phase 1 message history, the model can see what it already did. Nag dies.

### 3.8 Tests

- Delete `test_workspace_intel_tools.py` (whole)
- Trim `test_shell_tool.py` (remove any reliance on killed git.* tools)
- Update `test_tool_event_payloads.py` (remove fixtures for killed tools)
- New: `test_files_read_continuation.py` — adaptive paging + English hint behavior

**Files touched in this phase (~8-10 files):**
- Handlers: 3 deleted, 1 polished, 1 (files.py) edited
- Registration: `builtin_readonly.py` edited
- Tests: 1 deleted, 3 trimmed, 1 new

**Expected diff:** ~80 lines added, ~600 lines deleted.

**Verification:** existing tool tests for killed tools fail-by-design; new test suite covers the 5 kept tools. Model run against the standing probe session produces sensible behavior with the reduced surface.

**Go/no-go for Phase 4:** Phase 3 tests green. Real session probe behaves well with 5 tools. No regressions on Phase 1/2 work.

---

## Phase 4: Chat UX + frontend cleanup

**Purpose:** the user-visible win. Inline thinking between tool calls. Delete the "10 inches of overhead." Fix the disconnect/reconnect bug.

### 4.1 Inline thinking stream in chat column

Add new event flow:
- Backend: `reasoning_summary.delta` events from the Responses API flow through as `provider_event(kind="reasoning_delta", text="...")`.
- Orchestrator: emit these as `{kind: 'reasoning_delta', runId, sessionKey, seq, text}` over the WS.
- wsClient: normalize as a new part kind `{kind: 'thinking', text}` in the assistant message's `parts[]`.
- ChatMessage renderer: render `{kind: 'thinking'}` parts as compact italic/muted text inline, between tool chips.

Result: live narration like Claude Code. Tool batches collapse under their description labels (per the model's per-call `description` arg from Phase 3.5).

### 4.2 Tool chip grouping

When the model emits multiple `function_call` items in one response (`parallel_tool_calls: true` from PASS-7), render them as a single "Ran N tools" expandable header in the chat column, with individual chips nested inside. Matches Claude Code's UX.

### 4.3 File write/edit diff preview

For `files.write` and `files.edit` tool results, render the result chip with an inline diff preview (`+N -M` counter, scrollable green/red content). Data is already in the tool result body.

### 4.4 Delete dead UI

- `src/copenet/host/frontend/src/components/runtime/WorkingSetCard.tsx` — delete
- `src/copenet/host/frontend/src/lib/personalHistory.ts` — delete
- `src/copenet/host/frontend/src/runtime/mocks.ts` `workingSetByKey` — delete that block
- `src/copenet/host/frontend/src/runtime/adapter.ts` — delete `useWorkingSet` hook and `taskSummary` mapper
- `src/copenet/host/frontend/src/runtime/types.ts` — delete `WorkingSet` types
- `src/copenet/host/frontend/src/types/backend.ts` — narrow types around the killed fields

### 4.5 Trim references

- `ChatWorkspace.tsx:604` — remove `<WorkingSetCard ... />`
- `SessionSidebar.tsx:207` / `SessionDrawer.tsx:69` — drop `taskSummary` display, show title only
- `lib/missionControl.ts` — drop suggestion lanes that depend on `task_summary`. Keep panel shell if it still serves anything; otherwise simplify.
- `components/home/MissionControlPanel.tsx` — simplify if lanes empty out

### 4.6 Fix disconnect false-aborted (Codex finding #3)

Per Codex round 2: backend keeps tasks running on socket disconnect (`ws_server.py:104`); frontend marks every pending assistant as `aborted` on close (`wsClient.ts:884`) AND clears `activeRunId`. Reconnect bootstrap doesn't reattach to in-flight runs.

**Change:**
- On WS close, do NOT clear `activeRunId` or mark pending assistants as `aborted`. Instead, mark stream as "detached" and update UI to show "reconnecting...".
- On WS reconnect, check `sessions.list` response for any session where `inFlightRunId` is set. If yes, re-subscribe to that run's stream (may need a new RPC `chat.attach` or polling fallback).
- Only mark a run as truly aborted if backend confirms via `chat.aborted` event or run record final state.

### 4.7 Approval UI: untouched

Per your screenshots — keep the Telegram-style approve/deny UX intact. `OperatorActionCenter.tsx`, `ApprovalQueuePanel.tsx`, `ApprovalRequestCard.tsx`, `OutboundMessageCard.tsx` survive the rebuild unchanged. Real backend approval events get wired in as a separate feature pass later.

### 4.8 Tests

- Frontend: rendering test for `{kind: 'thinking'}` parts (Vitest or similar).
- Frontend: rendering test for grouped parallel tool calls.
- Integration: WS disconnect/reconnect test — confirm the frontend reattaches to in-flight runs without false-abort.

**Files touched in this phase (~15-18 files):**
- Backend: orchestrator `runtime.py` (emit new event), `wsClient.ts` (handle new event), no major schema changes
- Frontend: ~12 files edited or deleted per above
- Tests: ~3-4 new frontend tests, 1 integration test

**Expected diff:** ~500 lines added (mostly UX rendering), ~800 lines deleted (dead UI).

**Verification:** real session probe — send a message, watch the chat column render thinking text → tool chip → thinking text → final answer. WorkingSetCard gone. Disconnect mid-run, reconnect, run continues without false abort.

**Go/no-go for Phase 5:** Phase 4 manually validated by you running a real session. UX matches the target.

---

## Phase 5: Sweep

**Purpose:** dead code cleanup, doc updates, final test pass. Nothing risky — purely subtractive and cosmetic.

### 5.1 Delete

- `src/copenet/core/workspace_intel/` — if no callers remain after Phase 3 tool deletion. Otherwise leave for future use.
- Any other modules that grep clean after the prior phases.

### 5.2 Test cleanup

- Delete: `test_personal_history.py`, `test_working_set.py`, `test_context_tool.py`, `test_workspace_intel_tools.py` (all already covered in phase verifications but final sweep confirms).
- Trim: `test_state_store.py`, `test_run_store.py`, `test_runtime_probe_bundle.py`, `test_orchestrator.py`, `test_ws_rpc.py`, `test_harness_controller.py`.
- Verify the full suite is green with `uv run --extra dev pytest -q`.

### 5.3 Docs

- Update `AGENTS.md`:
  - Replace the harness/prompt-composition language with the new shape
  - Remove references to `working_set`, `personal_history`, `task_summary`, etc.
  - Document the new tool surface (5 tools)
  - Document the new `messages[]` flow
- Update `CLAUDE.md`:
  - Update the "Backend Gaps Known to Claude" table — most are resolved
  - Update "High-Conflict Files" list
- Update `docs/ARCHITECTURE.md`:
  - Subsystem map: remove deleted modules
  - Update tool loop description
- Remove the superseded V1 plan after V2 is established as the architecture record

### 5.4 Optional: `TARGET.md`

Per the workflow lessons in our conversation, create `docs/TARGET.md` as the standing "what are we building toward" doc. Distinct from AGENTS.md (which describes current state). Every future PR description references which TARGET section it serves.

Initial TARGET.md is roughly: "CopeNet is a personal continuity engine built around frontier-model orchestration via OAuth. Harness layer = Claude Code / Codex CLI / OpenClaw parity. Above that = your personal layers (persona/identity/memory when redesigned, briefing, return cues, etc.)."

**Files touched in this phase (~10-15 files):**
- Code deletions per item-by-item check
- Test edits per phase 5.2
- 4-5 doc files

**Expected diff:** ~200 lines added (mostly docs), ~400 lines deleted.

**Verification:** clean test run, clean doc read, `git log` since Phase −1 shows a coherent demolition + rebuild story.

---

## Cross-phase coordination

| Backend change | Frontend change | Phase |
|---|---|---|
| `RunRecord.working_set` field obsolete | `RunRecord.workingSet` consumers (WorkingSetCard, missionControl) deleted | 1 backend, 4 frontend |
| New `reasoning_delta` event in WS stream | wsClient handler + ChatMessage renderer | 2 backend, 4 frontend |
| `function_call` items per call have `description` arg from model | Tool chip uses description as label | 3 backend schema, 4 frontend |
| Disconnect doesn't kill `inFlightRunId` server-side | Reconnect reattaches to in-flight runs | 4 backend + 4 frontend together |

The only phase where backend and frontend MUST land together is Phase 4 (the reattach behavior, since disconnect handling crosses both). Phases 1-2 can land backend-first with frontend `working_set` consumers left as deadwood for one PR cycle.

---

## Open design decisions (need your read before implementation)

1. **Phase 0.4 (memory/profile gate):** environment variable or config field? Default off OK?
2. **Phase 3.5 (model-authored `description` per tool call):** schema field on every tool, or convention via prior assistant text? Both work; first is more reliable, second is OpenClaw-aligned.
3. **Phase 4.6 (reconnect to in-flight run):** new RPC method `chat.attach(runId)` or extend `sessions.list` response to include attachment endpoints? Either works.
4. **Phase 5.4 (TARGET.md):** worth creating now, or defer until the rebuild is complete?

I'll flag these as Phase begins and we resolve at implementation time.

---

## Rollback strategy

Each phase is one or two commits, on a branch, mergeable to main independently. Rollback = revert the merge.

**Phase −1 is fully revertable.** Pure adds + bugfixes; nothing else depends on it for compile.

**Phase 0 is fully revertable.** Config flag for memory/profile; deletion of context.prepare; cap bumps. All independent.

**Phase 1 is the first irreversible point.** Once `assemble_working_set` is gone, going back requires restoring the synthetic-prompt path. Practically: don't revert Phase 1, fix forward.

**Phase 2 stacks on Phase 1.** Same: fix forward.

**Phase 3 is mostly revertable** if any kept tool turns out to need a deleted one (unlikely but possible).

**Phase 4 is revertable per-component.** Each UI component can be un-deleted from git history.

**Phase 5 is purely cleanup.** Always revertable.

The architectural commitment happens at Phase 1. Be sure before that merge lands.

---

## What's not in this plan (deferred, intentionally)

- Pulse: rewire to consume transcript directly when we want it back. Per Bucket B disposition.
- Merge: same.
- Persona auto-update / memory redesign: gated off in Phase 0; thoughtful redesign later.
- Local model (LM Studio / Ollama) Responses-shaped path: keep the prompted loop alive but unmaintained. Future pass.
- Progressive disclosure of tool schemas: v2.1.
- Workspace intel revival: only if we decide we want it. Probably not in this rebuild.
- External app `/api/v1` lane audit: Codex flagged cross-app cancel ownership and web-ingest SSRF. File as separate issue, fix when we touch app_api.py for any reason.
- HarnessDecision trace-only work (from V1): keep the existing code; do not extend during V2. If proven valuable later, integrate as a real router. For now, dormant.

---

## Estimated total work

| Phase | Expected effort | Risk |
|---|---|---|
| −1 | Half a day | Low (pure prereq) |
| 0 | Half a day | Low (small, revertable) |
| 1 | 1-2 days | Medium (foundation) |
| 2 | 1-2 days | High (live API integration) |
| 3 | Half a day | Low (subtraction) |
| 4 | 1-2 days | Medium (UX work) |
| 5 | Half a day | Trivial |

**Total:** ~5-7 focused days. Could compress if individual phases go faster.

---

## After the rebuild

CopeNet's harness layer is Claude Code / Codex CLI / OpenClaw parity. The chat experience supports inline thinking, native tool calls, multi-turn continuity, reasonable tool surface, and prompt caching.

The persona/identity/memory/profile layers are dormant but preserved. When they come back, they come back through explicit operator opt-in and a clean redesign — not auto-mutation.

Pulse, Merge, Meme Lab, Web Ingest, Telegram routing, external `/api/v1` — all currently live, mostly orthogonal to the harness, degraded but not broken through the rebuild. Each gets its own future pass when it's worth attention.

This is the foundation. After this, every new feature builds on a harness that actually works.

---

## Implementation status (as built)

Phases −1 → 5 implemented on branch `codex/pre-harnessdecision-checkpoint`. Full
backend suite (294 tests) green; frontend `tsc` clean; frontend unit suite green
(2 pre-existing unrelated `agentsShellState` failures).

**Landed:**
- **−1** transcript persistence gate, per-session idempotency scoping, RPC error
  boundary, `responses_items.py`, baseline characterization tests.
- **0** `MAX_TOOL_STEPS` 4→100 (+ explicit stop note), file/search clamps killed
  with English continuation hints, `context.prepare` retired, memory/profile
  auto-extraction gated behind `COPNET_AUTO_*` env flags (default off).
- **1** `messages.py` (`build_chat_messages` + `flatten_messages_to_prompt`),
  real multi-turn history, keyword auto-mutation removed, `RunRecord.message_count`
  + `input_token_estimate`. tool_call/tool_result parts now share a `callId`.
- **2** `run_with_responses_tools` + openai-codex `stream_responses` (native
  Responses function_call lifecycle, prompt_cache_key, reasoning, parallel calls),
  `responses` tool-execution mode, `reasoning_delta` event.
- **3** model-facing manifest initially trimmed to five primitives via
  `ToolRegistry.list_tools()` (handlers still registered for routing). Approved plan,
  web, Market, persona, memory, and user-note tools were added later; the current source
  of truth is `MANIFEST_TOOL_IDS` in `core/tools/builtin_readonly.py`.
  `files.rg` gained `context_lines`.
- **4** inline thinking parts (backend emit → wsClient → renderer), reconnect
  reconciliation (no more false-abort), WorkingSetCard removed from chat.
- **5** docs (`ARCHITECTURE.md`, `AGENTS.md`), `docs/TARGET.md`.

**Documented deviations (deliberate, see commit messages):**
- `SessionStateRecord` was NOT narrowed. Pulse/Merge still read+write its text
  fields and are on the deferred-rewire list; narrowing now would crash them
  rather than degrade. The auto-mutation (the actual disease) is gone.
- `run_with_native_tools` was NOT deleted — it is the live LM Studio/Ollama path
  (declares `toolCalls`, driven via `chat_completion`, 6 test files). The plan's
  "dead code" premise was wrong for this codebase. The Responses path was added
  alongside it.
- Phase 3 trimmed the *manifest* (what the model sees) rather than deleting
  handler files; physical deletion is deferred to keep the probe/characterization
  suite stable.

**Remaining sweep (low-risk follow-ups):**
- Physically delete off-manifest handlers (`git.py`, `workspace_intel.py`,
  `files.list`/`files.search`) + the `_repeat_response` nag, reworking the probe
  classification suite (`probes/runtime_bundle.py`) and characterization tests in
  one focused pass.
- Delete remaining dead frontend (`useWorkingSet`/`mapSessionStateToWorkingSet`
  in `runtime/adapter.ts`, `runtime/mocks.ts` `workingSetByKey`, `WorkingSet`
  types) and the `taskSummary` reads in `SessionSidebar`/`SessionDrawer`.
- Narrow `SessionStateRecord` together with the Pulse/Merge rewire.
- **Live-verify Phase 2** against the real `chatgpt.com/backend-api/codex/responses`
  endpoint (`scripts/codex_responses_probe.py`) — needs OAuth + network.
- Manual browser pass for Phase 4 UX.
