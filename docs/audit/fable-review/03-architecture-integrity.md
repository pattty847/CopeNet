# Architecture Integrity

Checked against the principles stated in AGENTS.md. Three invariants verified intact; the violations below are ordered by severity.

## Verified intact (with evidence)

- **Append-only transcripts HOLD.** `TranscriptStore` exposes only `append_message`/`read_history`/`copy_history` (`transcript_store.py:90-145`); `copy_history` duplicates into a *new* session id. Repo-wide grep found zero mutation paths for stored entries; `append_message` flushes + fsyncs every record under a lock — the strongest durability guarantee in the repo, exactly where it matters.
- **No direct `index.json` writes outside SessionStore.** Only SessionStore itself, the orchestrator passing the path in, and a probe constructing its own store.
- **No rogue binding-mutation paths.** Grep for assignments to provider/model/profile/persona/workspace fields outside `session_store.py` returned nothing; the store's only mutators are title, archived, provider_session_id, and run markers. The hole is the null-lock case (below), not an extra write site.

## High

### Codex CLI provider owns execution/sandbox policy — disjoint from the task-mode policy layer
`providers/codex_cli.py:18-76` reads `COPNET_EXECUTION_MODE` (default `tools-enabled` → `--full-auto`; `unrestricted` → `--dangerously-bypass-approvals-and-sandbox`) and decides the subprocess's write/exec rights itself. This is per-run execution policy living in a provider — the Thin Providers principle's exact carve-out — and it is disjoint from `policy_for_task_mode` (`tools/policy.py:52`, applied at `runtime.py:280`), which governs only CopeNet's own tool registry. A guarded-mode session on codex-cli still launches codex with workspace-write + exec. `COPNET_EXECUTION_MODE` appears nowhere else in src/ or docs/. May be intentional as a v1 escape hatch, but it silently undercuts the permission story the rest of the system is built around.

### The session binding lock is one-way (null hole)
`session_store.py:267-270`: `if entry.task_prompt_id and entry.task_prompt_id != normalized_task_prompt_id: raise` — sessions stored with a null task mode never lock, the requested value is never back-filled, and `runtime.py:280` falls through to the **request's** task mode for tool policy. Any later send can pass `full-access` and gain write tools + unrestricted shell. The same `if entry.X and ...` skip applies to `system_prompt_id`, `persona_*`, and `workspace_root` (lines 263-286). Provider/model are checked strictly (lines 255-262). "After first send, the session is locked to provider, model, profile, and task mode" is not what this code enforces. Fix: persist resolved bindings onto the entry on first send, so null locks too.

### Corrupt index silently becomes empty, then gets atomically overwritten
`session_store.py:393-396` swallows `OSError`/`JSONDecodeError` and returns `{}`. Every mutator is load→modify→save, so one transient read failure means the next mutation cleanly replaces `index.json` with a near-empty file — all sessions orphaned, silently. Violates Safe Collaboration Rule 4 ("do not swallow storage errors silently") and converts the atomic-write invariant into a clean total-replacement mechanism. Same pattern in `state_store.py`.

## Medium

### Extraction-before-expansion: ~37 files over threshold
**Python >400 lines (18):** `meme_ideation.py` (1120), `orchestrator/runtime.py` (1075), `harness/tool_loop.py` (1045), `orchestrator/__init__.py` (893), `providers/openai_codex.py` (779), `host/app_api.py` (754), `profile/service.py` (671), `probes/runtime_bundle.py` (670), `host/rpc_catalog.py` (661), `host/rpc_sessions.py` (631), `tools/handlers/files.py` (578), `tools/contracts.py` (546), `providers/local_http.py` (533), `messaging/store.py` (502), `orchestrator/pulse.py` (453), `tools/barricade.py` (452), `orchestrator/merge.py` (445), `sessions/session_store.py` (418).

**TS/TSX >350 lines (19):** `wsClient.ts` (2346), `DataToolsPage.tsx` (1106), `types/backend.ts` (1015), `MessagingSettingsPanel.tsx` (832), `MemeLab.tsx` (831), `ChatWorkspace.tsx` (805), `AgentComposer.tsx` (737), `useAppStore.ts` (697), `InlineToolRows.tsx` (674), `mocks.ts` (650), `RightPanel.tsx` (584), `adapter.ts` (574), `SessionDrawer.tsx` (539), `OperatorActionCenter.tsx` (531), `InspectorDrawer.tsx` (528), `ExperimentsPage.tsx` (440), `useMemeLab.ts` (388), `memeClient.ts` (378), `SendMessageComposer.tsx` (352).

The worst multi-responsibility offenders:
1. **`wsClient.ts` (6.7× threshold)** — WS transport/reconnect, ~30 `normalize*` wire decoders across every domain (lines 114-944), the entire RPC method surface, and product policy (`PROVIDER_PRIORITY`/`pickPreferredProvider`, lines 59-89). The decoders alone are a `wire/` module waiting to exist.
2. **`runtime.py send_chat`** — a single ~720-line function (lines 94-812): idempotency, locking, transcript appends, history replay, harness invocation, event shaping, artifacts, run records, title scheduling, session state, profile/memory extraction, briefing emission. The canonical extraction candidate.
3. **`meme_ideation.py`** — DTOs, prompt building, JSON extraction, a seven-function heuristic judge, provider execution, and orchestration in one file.
4. **`DataToolsPage.tsx`** — an entire sub-app: hub routing plus four pages plus two drawer components.
5. **`orchestrator/__init__.py`** — a facade spanning ~10 domains, with real logic (not delegation) in `await_tool_approval`/`decide_approval` (lines 657-739).
6. **`openai_codex.py`** — two parallel generations of the same SSE concern (legacy `run()` stack at lines 587-740, Phase-2 `stream_responses` stack at 299-435), plus dead code: `_post_responses` (lines 562-584) has zero callers.

(`ws_server.py` at 205 lines with handlers extracted into `rpc_*` modules is the rule done right.)

### Harness specializes by hardcoded provider name where a capability flag exists
`tool_loop.py:1031-1038` and `runtime.py:33` (`_RESUME_CLI_PROVIDERS = {"claude-cli", "codex-cli"}`) string-match provider names, while providers already publish `capabilities.resume` in `describe()` (`claude_cli.py:108`) and the harness normalizes it into `ModelCapabilityProfile.resume` — then ignores it. Adding a third CLI provider requires editing two hardcoded sets.

### Internal-flow re-validation
`runtime.py` has 22 `isinstance` checks; the actual trust boundary (`ws_server.py`) has 2. The orchestrator re-`isinstance`s and re-coerces payloads the harness itself constructed two layers down (`runtime.py:380,396,426-433`; `_normalize_tool_step` at `:1009-1026` re-`str()`/`bool()`s every field of `ToolExecutionResult.to_event_payload` output). Other instances: `planning.py:46` re-guards `provider.describe()`; `runtime.py:80-87` guards a set it created itself via `setdefault` (and the non-set branch adds the key to a throwaway set); `runtime.py:960-961` defensive-getattrs an attribute of the internal `ToolDescriptor` contract. Per AGENTS.md's own normalization rule, the fix is typed DTOs for the tool-event metadata channel instead of `dict[str, Any]` re-checked at every hop.

### Capability metadata contradiction (Ollama)
Provider-level `describe()` claims `toolCalls: True` for Ollama (`local_http.py:74`); its models report `False` (`local_http.py:455`); and Ollama has no `chat_completion`, so a failed model-overlay match yields `willAttemptToolLoop: true` in the trace while the runtime silently runs with no tool loop (`harness/__init__.py:145`). Makes the documented trace-triage step 1 unreliable.

## Low

### CLI providers accept `system_prompt` and silently discard it
`codex_cli.py:177-186`, `claude_cli.py:135-144` — the parameter is never referenced in the body. The harness compensates by folding the system prompt into the user prompt and passing `None`, but any direct caller (tests, probes, future paths) gets profile/task-mode prompts silently dropped.

### Default prompt composition lives in a provider
`openai_codex.py:19,556` — `OPENAI_CODEX_DEFAULT_INSTRUCTIONS = "You are CopeNet's coding assistant. ..."` is injected when no system prompt is passed. One sentence, but it's the Thin Providers principle's named example (prompt composition belongs in `prompts/`/harness).

### `_save_map` renames without fsync
`session_store.py:416-418` — temp+rename is preserved (the invariant as written), but no flush/fsync before rename; on power loss the rename can land empty on some filesystems, which then trips the corrupt-index hole above. `TranscriptStore` does this correctly; mirror it.
