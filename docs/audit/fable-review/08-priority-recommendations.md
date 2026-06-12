# Priority Recommendations

Ranked action plan for a solo developer who wants to daily-drive this within weeks. Each item: what, where, size, and why it matters for daily use. Items are ordered so that finishing any prefix of the list leaves the system strictly more trustworthy.

## Tier 1 — Trust: stop losing sessions (do this week)

### 1. Close the session-bricking paths
- Move `mark_run_started` inside the existing try/finally (`core/orchestrator/runtime.py:179` → inside the `try` at `:286`, releasing via the `finally` at `:807-812`).
- Add a startup sweep in `Orchestrator.__init__` (`core/orchestrator/__init__.py:106`): clear every persisted `in_flight_run_id` (fresh process ⇒ none can be live) and write a synthetic `interrupted` run record.
- Make `SessionStore._load_map` (`session_store.py:393-396`) raise on corrupt index instead of returning `{}`; write a `.bak` before replace; fsync the temp file before rename (`:416-418`).

**Size: small** (each is a focused change; the sweep needs one new SessionStore method). **Why:** these are the only paths that permanently destroy state. A daily driver you can't crash is the precondition for everything else. Note: `runtime.py` is a high-conflict file — coordinate if Codex is active.

### 2. Stop button
Wire `wsClient.abortActiveRun()` (`wsClient.ts:2047` — already exists) to a button in `AgentComposer.tsx` shown while a run is active. **Size: small.** **Why:** the single most-felt daily gap; the backend is done, this is one component edit.

### 3. Close the same-run-id double-execution hole
`runtime.py:136-137`: treat `active_run == run_id` as in-flight rather than passing the guard. **Size: small.** **Why:** a client retry mid-stream currently double-runs the turn and unlocks early — silent transcript corruption in exactly the flaky-network conditions a daily driver hits.

## Tier 2 — Safety: make the permission story true

### 4. Fix the guarded-shell write holes
`tools/handlers/shell.py`: reject `find` argv containing `-delete`/`-exec`/`-execdir`/`-ok`/`-okdir`/`-fprint*` (`:240` area); drop `branch` from `_SAFE_GIT_SUBCOMMANDS` or reject write flags (`:49-58`). **Size: small.** **Why:** guarded mode is advertised as read-only and currently isn't; you will run untrusted-ish model turns in guarded mode daily.

### 5. Back-fill session bindings on first send
In the first-send path, persist resolved `task_prompt_id`/`system_prompt_id`/persona/workspace onto the entry so the null-lock hole closes (`session_store.py:267-286` enforcement, write site in `resolve_or_create` or a new `bind_session` call from `runtime.py:152-173`). **Size: small-medium.** **Why:** without it, any session created without a task mode can be silently escalated to full-access later — the product's central promise ("locked after first send") is false.

### 6. Decide the codex-cli sandbox question
`providers/codex_cli.py:18-76` launches codex with `--full-auto` regardless of CopeNet task mode, controlled by an undocumented env var. Either map CopeNet task modes onto codex sandbox flags, or document loudly that codex-cli sessions ignore task modes. **Size: small to decide, medium to map.** **Why:** a guarded session that can still write via the provider's own tools is a false sense of safety in daily full-repo use.

## Tier 3 — Continuity: make "walk away and come back" work

### 7. Connection registry + broadcast + approval recovery
`host/ws_server.py`: maintain a set of live connections; emit chat/approval/session events to all of them. Add an `approvals.list` RPC (orchestrator already holds `_pending_approvals`) and fetch it at bootstrap (`wsClient.ts:1304-1320`). Reconsider the 300s approval timeout (`orchestrator/__init__.py:666`) — for an operator who steps away, park indefinitely or much longer. **Size: medium** (the one genuinely structural item in this list). **Why:** this single root cause is behind stuck "reconnecting" bubbles, approvals lost on reload, dead tailnet-phone sync, and flaky mobile. It is the gap between CopeNet today and the stated product vision.

### 8. Model-facing transparency quick wins
Three one-liners from `06-harness-transparency-gaps.md`:
- `registry.py:155-161`: put `str(exc)` into `output` on generic tool exceptions (frontier models currently see `{}`).
- `runtime.py:88-89`: tell the model when an operator rejected an approval (it currently can't distinguish rejection from the pending state and will retry).
- `_shared.py:30-31,58-59` + `shell.py` output dicts: flag truncated shell output.

**Size: small.** **Why:** these directly improve every model's behavior on every turn — fewer dead-end retries, fewer confidently-wrong conclusions from clipped output.

### 9. First-run honesty
- Add `npm install && npm run build` (or a `copenet build-ui` step) to README/STARTUP; log a warning when serving the legacy fallback (`host/api.py:23-24`).
- Token prompt on `auth_failed` persisting to localStorage (`wsClient.ts:75-80`, `ConnectionBanner.tsx`).
- Fix `docs/STARTUP.md:76` (`copenet-host` doesn't exist); document `COPNET_WORKDIR`.
- Zero-provider empty state with setup pointers.

**Size: small each.** **Why:** these are the first-hour traps; each one is the difference between "it works" and "it silently does the wrong thing" for the next machine you install on.

## Tier 4 — Hygiene: subtract before adding

### 10. The mock purge
Move `buildInboxItems` out of `mocks.ts` (it's real logic, `mocks.ts:574-650`), then delete: the mock fallbacks in `useArtifact`/`useBatch`/`useRunActivity` (`adapter.ts:149,187,230`), dead hooks `useWorkingSet`/`useArtifacts`/`useLastTurnState`, the fake half of `useMockTransitions` (keep approve/reject, renamed honestly), `SendMessageComposer`'s simulated send (hide the composer until a delivery lane exists), the MemeLab `allowMock` 404 fallback, and the unpopulatable `RunTimeline` mount. Make `messaging.test` either call `getMe` or report "config present (unverified)". **Size: medium** (wide but mechanical). **Why:** phantom data in the inspector is worse than empty states when you're debugging real runs daily — you cannot trust what you see.

### 11. Update the orientation docs
Rewrite CLAUDE.md's gaps table (4/7 rows stale), fix AGENTS.md's tool-handler list (`context.py` is retired; manifest is 8 tools including `web.*`), align the connect-hello method list (`ws_server.py:139-198`). **Size: small.** **Why:** these files steer every future agent session; stale tables cause re-implementation of shipped work.

### 12. Decide multiagent's fate
`core/multiagent/` is complete, tested, and wired to nothing, with a role map targeting a nonexistent `gemini` provider. Either write the integration contract (how `delegate_subagent_task` enters the live `send_chat` flow, what tool exposes it) and wire it, or move it to a branch until that design exists. **Size: decision is small; wiring is large.** **Why:** unwired scaffolding at HEAD rots fast and invites parallel agents to build on a floating foundation.

## Explicitly deferred (don't do these yet)

- **Extraction of `wsClient.ts`/`send_chat`** — justified (2,346 lines / 720-line function) but high-conflict and zero user-visible payoff; do it opportunistically when touching those files for Tier 1–3 work, not as a project.
- **tool/file polish backlog** (`files.list` dead hint, `context_lines`, schema `required` fields, repeat-detection hoisting) — real but small; batch them into one tools-cleanup PR after Tier 2.
- **Pat Profile real learning** — the keyword demos in `profile/service.py:387-515` need replacing with model-driven extraction, but that's a feature project, not a fix; the storage and injection layers it builds on are sound.
- **Cross-process file locking** (`fcntl.flock` in SessionStore) — real hole, but only bites when running CLI sends concurrently with the host; an interim rule ("don't run both against one session") costs nothing.
