# Executive Summary — Top 10 Findings

Cold audit, 2026-06-11. Findings verified against code at HEAD (`ab3b288`). Ranked by impact.

## 1. A crash or early exception permanently bricks a session, and there is no recovery

`mark_run_started` writes `in_flight_run_id` to disk at `orchestrator/runtime.py:179`, but the `try/finally` that releases it doesn't begin until line 286. Any exception in the ~100 lines between — transcript append (line 201), state-store load (213), history read (230), prompt building — leaves the lock set with no cleanup. Worse, there is **no startup reconciliation anywhere**: after a `kill -9` or power loss mid-run, the persisted `in_flight_run_id` survives, `chat.abort` returns `aborted: false` (it only checks in-memory maps, `orchestrator/__init__.py:165-167`), and every future send raises `session is in flight` forever. The only escape is hand-editing `index.json`. This is the single biggest threat to daily-driver trust. See `05-session-invariants.md` findings 1–2.

## 2. Guarded "read-only" shell mode can delete the workspace

The allowlist check inspects only `argv[0]` (`handlers/shell.py:240`), so allowlisted binaries with write-capable flags pass: `find . -delete` removes files, `find . -exec rm {} +` runs arbitrary `rm`, and `git branch -D main` passes the git subcommand safelist (`shell.py:49-58`). The mode the whole product describes as read-only is not. See `04-tool-surface-critique.md` §2.

## 3. The session lock is one-way: a session without a task mode can be escalated to full-access on any later send

`assert_session_binding` only enforces locks when the stored field is non-empty (`session_store.py:267-270` — `if entry.task_prompt_id and ...`), and the requested value is never back-filled onto the entry. The runtime then honors the **request's** task mode for tool policy (`runtime.py:280`: `entry.task_prompt_id or request.task_prompt_id`), so any later send to a null-task-mode session can pass `full-access` and gain write tools + unrestricted shell, turn by turn. Provider/model are locked strictly; profile, task mode, persona, and workspace root all share the null hole. Separately, the codex-cli provider ignores CopeNet task modes entirely — it launches with `--full-auto` (workspace write + exec) by default regardless of session policy, governed by an undocumented `COPNET_EXECUTION_MODE` env var (`providers/codex_cli.py:18-76`).

## 4. Frontier models on the native/Responses paths receive `{}` when a tool errors

`_native_tool_message_content` (`tool_loop.py:773-777`) sends the model only `result.body` or `result.output` — never `ok`, `summary`, or `error`. The prompted (weak-model) path gets the full envelope via `to_prompt_payload()`. Generic handler exceptions (`registry.py:155-161`) produce `output={}`, so a frontier model that passes a bad argument sees literally the string `{}` and has to guess what went wrong. One function fix closes it. See `06-harness-transparency-gaps.md`.

## 5. There is no way to stop a run from the UI, and approvals die on reload

`chat.abort` is fully implemented server-side, and `wsClient.abortActiveRun()` exists at `wsClient.ts:2047` — with zero callers. No stop button exists anywhere. Compounding it: chat/approval events are emitted only through the originating socket's closure (`rpc_chat.py:122-133`; no connection registry in `ws_server.py`), so a page reload mid-approval loses the approval card permanently and the run dies by 300s timeout; a second device (the tailnet phone the README sells) never sees live runs at all. See `07-daily-driver-friction.md`.

## 6. Mock data still leaks into live product surfaces, violating the repo's own mock-discipline rule

`mocks.ts resolveKey()` returns fabricated data for **any** session key (`mocks.ts:262-265`), and `useArtifact`/`useBatch` fall back to it inside hooks consumed by the live `InspectorDrawer` (`adapter.ts:149,230`). The message composer's Send button is pure theater — `simulateSendMessageComposed` fabricates an outbound record and a fake approval; no delivery path exists anywhere in the backend. `messaging.test` stamps `connection_status="connected"` without ever contacting Telegram (`orchestrator/messaging.py:237-270`). See `01-dead-weight.md` and `02-unfinished-contracts.md`.

## 7. The multiagent package — the HEAD commit — is wired to nothing

All four modules of `core/multiagent/` (delegation, orchestrator_adapter, provider_selector, fallback_executor) have zero importers outside their own package and one unit test. No tool exposes delegation to the model; nothing in the orchestrator or harness calls it; the default role map targets a `"gemini"` provider that doesn't exist in `src/copenet/providers/`. It may be intentional staging, but as shipped it is scaffold-only.

## 8. A corrupt `index.json` is silently treated as empty — and the next write atomically destroys every session

`_load_map` swallows `OSError`/`JSONDecodeError` and returns `{}` (`session_store.py:393-396`). Every mutator does load→modify→save, so one corrupt byte means the next rename/archive/run-start writes a near-empty index over the old file via the (correct) temp+rename. The atomic-write invariant is preserved while its purpose is defeated. Low probability, catastrophic, invisible.

## 9. A fresh clone silently serves the wrong UI, and the docs that orient new sessions are stale

`frontend/dist` is gitignored and the build step (`npm install && npm run build`) appears in no README/STARTUP path; the host silently falls back to the legacy vanilla UI (`api.py:23-24`) with no warning. `docs/STARTUP.md:76` documents a `copenet-host` script that doesn't exist. CLAUDE.md's "Backend Gaps" table is 4/7 stale — `profile.get`, `briefing.get`, and `briefing.ready` all shipped; a developer trusting the table would re-implement them. AGENTS.md still lists a `handlers/context.py` that was retired in Phase 0.3.

## 10. The extraction-before-expansion rule is the most-violated principle in the repo

18 Python files exceed the 400-line threshold and 19 TS/TSX files exceed 350. The worst: `wsClient.ts` at 2,346 lines (transport + ~30 wire decoders + the entire RPC surface + product policy), and `send_chat` in `runtime.py` — a single ~720-line function holding idempotency, locking, transcript, history replay, harness invocation, event shaping, artifacts, run records, titles, profile/memory extraction, and briefing emission. Both are also the highest-risk files to edit, which is exactly why the rule existed.

---

## Fix this first

**The session-reliability trio plus a stop button.** (1) Move `mark_run_started` inside the existing try/finally in `runtime.py`; (2) add a startup sweep that clears stale `in_flight_run_id` values and records interrupted runs; (3) make `_load_map` fail loudly on corruption instead of returning `{}`. Then (4) wire a Stop button to the already-working `chat.abort`. Together these are maybe a day of work and they convert CopeNet from "trustworthy until the first crash" to something you can actually leave running unattended — which is the entire product thesis. The shell allowlist holes (#2) and the task-mode null hole (#3) are the next tier: they're the gap between the permission story the product tells and the one it enforces.
