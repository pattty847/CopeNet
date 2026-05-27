# HANDOVER — finish the harness live-verification (run locally)

**You are a local coding agent (Claude Code / Cursor) on the user's Mac.** You
have what the cloud agent that built this lacks: the repo on disk, **Codex OAuth
creds**, **localhost**, and a **browser**. The user has authorized you to run
everything below autonomously, in a loop, committing small checkpoints, until an
openai-codex tool-using chat turn works end-to-end and the suite is green. Don't
wait for confirmation between steps — just keep going and leave a clear trail.

**Branch:** `codex/pre-harnessdecision-checkpoint`
```bash
cd ~/Programming/CopeNet
git fetch origin && git checkout codex/pre-harnessdecision-checkpoint && git pull
uv run --extra dev pytest -q            # expect ~324 passing; if not, stop & read failures
```

## Context (read these for the full picture)
- `docs/plans/HARNESS_REBUILD_V2.md` — the rebuild + "Implementation status (as built)".
- `docs/TARGET.md` — north star. `docs/plans/MULTI_AGENT_ORCHESTRATOR.md` — next layer.
- `docs/architecture.md` — current subsystem map.

The chat harness was rebuilt in 6 phases: real multi-turn message history
(`core/orchestrator/messages.py`), a native Responses-API tool loop
(`core/harness/tool_loop.py::run_with_responses_tools` +
`providers/openai_codex.py::stream_responses`), a 5-tool model-facing manifest,
inline-thinking + reconnect UX, and a multi-agent foundation (`core/multiagent/`).

## What's ALREADY live-verified (via scripts/codex_responses_probe.py)
Confirmed against the real `chatgpt.com/backend-api/codex/responses` (gpt-5.5):
- Native function calling (output_item.added/function_call_arguments.delta/done/completed).
- Multi-turn structured `input[]` (prior function_call + function_call_output + assistant).
- CopeNet's EXACT payload — `parallel_tool_calls`, `tool_choice`, `prompt_cache_key`,
  no-`strict` tools, `reasoning` block, and **dot-free tool names** (`files.read`
  → `files_read`, reverse-mapped on the way back). Scenario D returns a clean
  `function_call`.

## KNOWN gotchas already fixed (don't re-break these)
- Responses function names must match `^[a-zA-Z0-9_-]+$` — dotted ids are
  sanitized at the provider boundary and reverse-mapped in the loop.
- Resuming CLI providers (claude-cli/codex-cli) get ONLY the new message, not
  the full transcript (they keep their own thread).
- Reasoning is requested by default but the endpoint delivers it as an
  `output_item` (type=reasoning), not `*.delta` — parser handles both.
- The model needs an AGENT directive to actually call tools (see below).

---

## IMMEDIATE TASK — get a real tool-using turn working, then loop

### Step 0: reproduce the error the user just hit
The user ran this and got "a straight error" (text unknown to the cloud agent):
```bash
COPNET_TRACE=1 uv run copenet chat send \
  "Read README.md and explain the architecture in 3 bullets, then suggest one improvement." \
  --provider openai-codex --session think-live1
```
Run it. **Capture the full stderr/traceback.** Likely candidates:
- A traceback in `run_with_responses_tools` / `stream_responses` / `_parse_responses_sse`
  (e.g. an SSE shape the parser mishandles on a real multi-step turn).
- An HTTP 4xx from the live API on the multi-step re-POST (the first POST works
  per Scenario D; the SECOND POST — with function_call + function_call_output +
  the appended assistant message — may have an ordering/shape the endpoint
  rejects. Check the error body for `input[k]`).
- The new agent-instructions change (commit f6fcfa0) — unlikely (imports clean,
  tests pass) but rule it out by checking the traceback origin.

Then read the trace: `cat "$(ls -t ~/.copenet/logs/runs/*.jsonl | head -1)"`.
The `harness_planned` event should show `toolExecutionMode: "responses"` and the
3 tools; find where it stops (which event is last before the error).

### Step 1: diagnose + fix, smallest change that works
- If it's a parser/loop crash: fix `_parse_responses_sse` or
  `run_with_responses_tools` to handle the real event/shape; add a unit test in
  `tests/unit/test_openai_codex_responses.py` or
  `tests/integration/test_responses_tool_loop.py` that reproduces it with a
  scripted provider.
- If it's an HTTP 4xx on the multi-step re-POST: read the error body. The likely
  issue is the order/shape of replayed items. The canonical Responses replay is:
  for each tool-calling response, append the assistant items THEN the
  `function_call` item(s) THEN the matching `function_call_output`(s). Adjust
  `run_with_responses_tools`' append order if needed. Capture the working shape
  by extending `scripts/codex_responses_probe.py` with a scenario that mirrors
  the second POST, and iterate against the live endpoint until it returns 200.
- Keep the cloud agent's design intact: canonical dotted ids internally,
  sanitize only at the provider boundary; don't delete run_with_native_tools or
  narrow SessionStateRecord (see V2 deviations).

### Step 2: confirm the full multi-step loop end-to-end
Re-run Step 0 against a FRESH session each attempt (`think-live2`, `3`, …) so
stale transcript hedging doesn't bias the model. Success looks like, in the trace:
- `tool_requested` / a `responsesFunctionCall` for `files.read`,
- a SECOND `responses_turn_interpreted` (step 2) after the tool ran,
- `assistant_finalized` with a real README-grounded answer (not the "I can't
  read files" hedge).

### Step 3: answer the reasoning/thinking question
On that successful substantive turn, `grep -i reason` the trace. If reasoning
text appears → inline-thinking works; note the exact event/field shape in
`providers/openai_codex.py::_parse_responses_sse` / `_reasoning_item_text` and
tighten if needed. If reasoning is always empty → the endpoint doesn't surface
summaries; lower or drop `DEFAULT_RESPONSES_REASONING` in
`core/harness/tool_loop.py` to save latency, and note it.

### Step 4 (optional, if time): browser pass
Start backend + `cd src/copenet/host/frontend && npm install && npm run dev`.
Verify a tool-using turn renders tool chips → answer; mid-run disconnect +
reconnect does NOT false-abort (reconciles to the real result). The 5-tool
manifest only.

---

## Loop discipline
- After each fix: `uv run --extra dev pytest -q` must stay green (~324+).
  Frontend: `cd src/copenet/host/frontend && npx tsc --noEmit` clean.
- Commit each logical fix as its own checkpoint with a clear message; push to
  `codex/pre-harnessdecision-checkpoint`.
- If a live API shape needs discovery, extend `codex_responses_probe.py`, run
  it, read `docs/investigations/harness-rebuild/probe-results/*.jsonl`, encode
  the finding as a test, then fix the code.
- Stop when: Step 0 prompt completes with a real tool-using, README-grounded
  answer; tests green; reasoning question answered. Write a short summary of
  what the error was, what fixed it, and the reasoning verdict.

## Rules
- Small reversible commits. Never skip hooks. Keep the suite green.
- Don't regress the documented deviations in V2 (run_with_native_tools stays;
  SessionStateRecord not narrowed; off-manifest handlers stay registered).
- The branch is not in production; fix-forward or revert freely.
