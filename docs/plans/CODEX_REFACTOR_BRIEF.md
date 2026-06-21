# Codex Refactor Brief — pay down the god-objects (behavior-preserving)

**To:** Codex · **From:** Claude (architecture lane) · **Owner:** Patrick
**Companion doc:** [`docs/audit/code-health-2026-06.md`](../audit/code-health-2026-06.md)

You're taking the structural-debt pass on CopeNet. This is a **behavior-preserving
refactor** — split the genuine god-objects into focused modules so future agent edits are
cheap, parallelizable, and low-blast-radius. It is NOT a feature change and NOT a rewrite.

## Why this matters (so you make the right calls)

File size bites *agents* mechanically, independent of model smarts:
- **Edit cost** — safely editing a 2,491-line file means reading most of it every time. Small
  modules = load only what's needed.
- **Collision** — parallel agents (the Claude+Codex collaboration we're building toward) clash
  on one giant file. Modules let us work in parallel without merge hell.
- **Blast radius** — a bad edit in a 100-line module breaks that module; in a god-file it breaks
  everything that imports it.
- **Searchability** — see AGENTS.md "Coding Standards For Searchability." Big files make `rg`
  noisy.

**Targeted, not dogmatic.** Split the 1,000+ line mixed-responsibility files. Leave cohesive
~400-line files alone. Don't gold-plate. When in doubt, prefer the smaller, safer extraction.

## Hard constraints (do not violate)

1. **No behavior changes.** Pure moves + re-exports. Public function/method/RPC signatures,
   event names, tool ids, and on-disk formats stay identical. If you're tempted to "improve"
   logic, STOP — note it for a separate change.
2. **Preserve the sacred invariants** (AGENTS.md "Session Semantics"): `in_flight_run_id`
   locking, append-only transcripts, atomic temp-file+rename index writes, provider/profile
   binding checks, identity binding. The mid-session-mutability reconcile in
   `session_store.assert_session_binding` must keep working exactly as-is.
3. **Verify after EVERY extraction**, not just at the end (gates below). Commit per phase with a
   green tree. A red gate means revert that step, not push forward.
4. **Keep import-compat shims** where other modules import the moved symbols — re-export from the
   old path so nothing downstream breaks. (The repo already does this; match the pattern.)
5. **High-conflict files — extra care** (CLAUDE.md "High-Conflict Files"): `wsClient.ts`,
   `ws_server.py`, `orchestrator/runtime.py`, `orchestrator/__init__.py`, `store/useAppStore.ts`,
   `AppShell.tsx`, `runtime/adapter.ts`. Move in small, reviewable steps; don't reorganize logic
   while splitting.
6. **Branch from the latest `main`** (after `feat/memory` merges — confirm with Patrick the tree
   is current). Work on `refactor/god-objects`. Small per-phase commits, not one mega-commit.

## Verification gates (run after every extraction)

Frontend (in `src/copenet/host/frontend`):
```
npx tsc --noEmit          # must be EXIT 0
npm run build             # must succeed
```
Backend (repo root):
```
python3 -m py_compile $(rg --files src/copenet -g '*.py')
uv run --extra dev pytest -q     # all green (410 tests at brief time)
```
If a test encodes the OLD module path, update the import — but never change an assertion's
*meaning* to make it pass.

## Phase 0 — re-audit (do this first)

The audit doc is from 2026-06 and several files grew since. Refresh it:
- Recount lines for the offenders below; scan for anything new over threshold (Python ~400,
  JS/TS ~350, >3 responsibilities/file).
- Confirm the proposed seams still hold; flag any you'd cut differently.
- List what you'll do, in order, and get a sanity check before the big ones (wsClient,
  orchestrator). Write findings into `docs/audit/code-health-2026-06.md` (append a dated
  "Refactor pass" section).

## Phases (low-risk → high-value; verify + commit each)

**P1 — `lib/formatting.ts` (trivial, do first).** ~14 frontend files carry a local
`timeAgo`/`formatRelative`/`formatDuration`. Extract one shared module, replace the copies.
Pure dedup; zero behavior change.

**P2 — `core/_json_store.py`.** 6+ stores hand-roll the same atomic JSON pattern
(`_load_unlocked`/`_save_unlocked`, temp-file+rename): `memory/store.py`, `permissions/store.py`,
`profile/service.py`, `persona/service.py`, `messaging/store.py`, `messaging/routing_store.py`.
Extract a small base (load/save/atomic-write) and have them use it. Keep each store's public API
and on-disk shape identical. **This touches storage — verify atomic-write behavior is preserved.**

**P3 — split `lib/wsClient.ts` (2,491, the biggest liability).** It mixes transport (connect/
reconnect/heartbeat), ~50 `normalize*` functions, RPC request wrappers, and event handling.
Target seams: `wsConnection.ts` (socket lifecycle), `wsNormalizers.ts` (the normalize* funcs),
`wsRpc.ts` / per-domain RPC method groups, leaving a thin `wsClient.ts` facade that composes them.
The class's public methods must keep their names + signatures (components call them directly).

**P4 — `core/harness/tool_loop.py` (1,045) per-strategy split.** Three strategies
(native / responses / prompted) with ~40% duplicated loop. Extract per-strategy modules + a thin
dispatcher; factor the shared loop. **Behavior-critical — verify against
`tests/integration/test_tool_prompt_matrix.py` and `test_responses_tool_loop.py` after.**

**P5 — `host/rpc_catalog.py` (764) split by subsystem.** It holds 40+ handlers for ~7 subsystems.
Follow the existing pattern (`rpc_permissions.py`, `rpc_chat.py`, `rpc_nasa.py`, `rpc_sessions.py`
already exist): extract `rpc_profile.py` / `rpc_persona.py` / `rpc_memory.py` / `rpc_messaging.py`
/ `rpc_prompts.py`. Update `rpc_dispatch.py` imports; the method-name → handler mapping stays
exactly the same.

**P6 — `orchestrator/__init__.py` (1,128) facade slimming (highest coupling — do carefully).**
80+ methods re-exporting 15+ subsystems. Goal: keep session-lifecycle + the public facade
surface, but push subsystem-specific logic into the owning service where it leaks in. Move in
tiny steps with the full suite green between each. If a move feels risky, leave it and note it.

**P7 — page/component extractions (opportunistic).** `DataToolsPage.tsx` (1,155 — extract the
inline sub-panels), `AgentComposer.tsx` (868 — RuntimeSelector / optimizer modal),
`types/backend.ts` (1,052 — split by domain), `meme_ideation.py` (1,120 — prompts/parsing/
scoring). Take these as far as the gates stay green and the diffs stay reviewable; partial is fine.

## Final deliverable

1. All gates green; per-phase commits on `refactor/god-objects`.
2. **Update the docs to match the new layout** (this is required, not optional):
   - `AGENTS.md` — the "Major Subsystems" table + any module paths that moved; the searchability
     section if conventions changed.
   - `CLAUDE.md` — the "High-Conflict Files" list if file paths changed.
   - `docs/architecture.md` — if request-flow module names moved.
   - `docs/audit/code-health-2026-06.md` — a "Refactor pass (done)" section: what split into what,
     before/after line counts, anything intentionally left.
3. A short PR/summary: files changed, what moved where, and any debt you deliberately deferred
   (with the reason). Flag anything you found that smells like a real bug — note it, don't fix it
   inline.

Keep the smallest diff that achieves clean separation. We trust your judgment on the seams —
when unsure, smaller and safer wins.
