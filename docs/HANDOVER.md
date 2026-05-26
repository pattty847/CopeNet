# HANDOVER — harness rebuild verification

**For:** a local coding agent (Cursor / Claude Code on the Mac) with repo access,
Codex OAuth creds, a browser, and localhost. The agent that built this ran in a
cloud container and could not do live-API or browser verification.

**Branch:** `codex/pre-harnessdecision-checkpoint` (everything below is on it).

**Start here:**
```bash
cd ~/Programming/CopeNet
git fetch origin
git checkout codex/pre-harnessdecision-checkpoint
git pull origin codex/pre-harnessdecision-checkpoint
uv run --extra dev pytest -q            # expect ~319 passing
```

---

## What was built (context)

A full rebuild of CopeNet's chat harness, per `docs/plans/HARNESS_REBUILD_V2.md`
(read its "Implementation status (as built)" section). In short:

- **Phase 1** — real multi-turn message history. `core/orchestrator/messages.py`
  (`build_chat_messages` → Responses `input[]`; `flatten_messages_to_prompt` for
  prompt-only providers). Killed the synthetic working-set + keyword auto-mutation.
- **Phase 2** — native Responses-API tool loop for openai-codex.
  `core/harness/tool_loop.py::run_with_responses_tools` +
  `providers/openai_codex.py::stream_responses`. Streams the function_call
  lifecycle, replays `function_call_output`, re-POSTs.
- **Phase 3** — model-facing tool manifest trimmed to 5 primitives
  (files.read/write/edit/rg, shell.exec) via `ToolRegistry.list_tools()`.
- **Phase 4** — inline "thinking" parts + reconnect-without-false-abort.
- **Multi-agent foundation** — `core/multiagent/` (provider selection + fallback;
  not yet wired into send_chat). See `docs/plans/MULTI_AGENT_ORCHESTRATOR.md`.
- **5 audit fixes** — CLI double-context, tool-output replay loss, dead thinking,
  abort-unsafe tools, payload-superset risk.

All backend tests + frontend `tsc` green. The pieces the cloud agent could NOT
verify are below.

---

## TASK 1 — confirm CopeNet's exact live payload (5 min, highest priority)

```bash
uv run python scripts/codex_responses_probe.py
```
Look at **Scenario D** ("CopeNet's EXACT payload…"). It sends the params the
original A/B/C scenarios never tested: `parallel_tool_calls`, `tool_choice`,
`prompt_cache_key`, tools WITHOUT `strict`, and the default reasoning block —
built by the REAL `_build_responses_payload` + `build_responses_tool_schemas`.

- **If D shows a `function_call`** (like B/C) → CopeNet's real request is
  live-verified. Done. Record it in the V2 doc.
- **If D shows `HTTP 4xx`** → one of those extra params is rejected. Bisect by
  editing `scenario_d_payload()` in `scripts/codex_responses_probe.py`. Prime
  suspects, in order: `prompt_cache_key`, then `tool_choice`, then
  `parallel_tool_calls`. Once identified, remove that param from
  `providers/openai_codex.py::_build_responses_payload` (guard it or drop it),
  re-run, and keep the rest. Commit the fix.

---

## TASK 2 — does inline thinking actually stream? (reasoning event name)

The probe showed gpt-5.5 emitted NO reasoning events for trivial turns even with
reasoning requested. The summary event name isn't pinned down. The SSE parser is
now name-agnostic (`response.reasoning*.delta` → thinking), but we need to know
if the endpoint emits reasoning summaries AT ALL on real work.

```bash
# Run a real, non-trivial openai-codex turn with tracing on:
COPNET_TRACE=1 uv run copenet chat send --provider openai-codex \
  --session probe-think --message "Read README.md, then explain the project's
  architecture in 3 bullets and suggest one improvement."
# Then inspect the trace JSONL for reasoning:
ls -t ~/.copenet/traces/**/*.jsonl 2>/dev/null | head -1   # path may differ
grep -i reasoning <that trace file>
```
- If you see `reasoning_delta` provider events / `response.reasoning*` SSE types
  → thinking works; note the exact event name in
  `providers/openai_codex.py::_parse_responses_sse`.
- If reasoning NEVER appears even on substantive turns → the codex backend-api
  endpoint likely doesn't surface reasoning summaries. In that case: keep the
  parser as-is (harmless), and either lower `DEFAULT_RESPONSES_REASONING` effort
  in `core/harness/tool_loop.py` or drop reasoning to save latency. Report which.

---

## TASK 3 — browser pass on the chat UX (Phase 4)

```bash
# backend
uv run copenet serve            # or however the host is started (check README / AGENTS.md)
# frontend
cd src/copenet/host/frontend && npm install && npm run dev
```
Open the UI, start an openai-codex session, and verify:
1. A tool-using turn renders: (thinking, if Task 2 confirms it) → tool chip →
   result → final answer. Tool chips should be the 5-primitive set only.
2. **Reconnect test:** mid-run, kill the backend (or drop wifi) and bring it
   back. The pending assistant must NOT flip to "aborted"/"Connection lost.";
   on reconnect it should reconcile to the real result (the run kept going
   server-side). This is the Phase 4.6 fix — confirm it holds.
3. The old WorkingSetCard is gone from above the chat input.

Frontend unit tests (note: 2 pre-existing `agentsShellState` failures are
unrelated to this work):
```bash
cd src/copenet/host/frontend && node --import tsx --test tests/*.test.ts tests/*.test.tsx
```

---

## Rules of engagement (same as the cloud agent followed)

- Small, logically-grouped commits = checkpoints. Keep the suite green.
- Don't delete `run_with_native_tools` (live LM Studio path) or narrow
  `SessionStateRecord` (Pulse/Merge read it) — see the documented deviations in
  the V2 doc.
- The remaining off-manifest handler deletion + dead-frontend sweep are tracked
  in V2's "remaining sweep" — low priority, do after verification.
- If something's wrong, fix forward or revert the offending commit; nothing here
  is load-bearing in production yet.

## Report back to the cloud session
Paste: Scenario D result, the reasoning event name (or "none"), and the browser
pass outcome. That closes every gap the cloud agent flagged.
