# Session Invariants

The semantics AGENTS.md calls sacred, audited path by path. The good news first: append-only transcripts, atomic index writes, and the absence of rogue binding mutations all **hold** (evidence at the bottom). The findings are lifecycle-coverage holes, not extra write paths.

## Critical

### 1. Exception gap between taking the lock and entering the try/finally
The disk lock is written at `runtime.py:179` (`mark_run_started`), inside the `async with orchestrator._lock` block; the `try` whose `finally` (lines 807-812) releases it does not begin until **line 286**. Everything in between runs unprotected:
- `trace.record(...)` (184-199)
- `transcript_store.append_message(...)` (201-212) — can raise `OSError` (disk full, perms)
- `session_state_store.get_or_create(...)` (213)
- `orchestrator.history(..., limit=400)` (230) and `build_chat_messages` (232)
- `policy_for_task_mode` / tool filtering (280-285)

Any exception here propagates with `in_flight_run_id` set on disk, the in-memory active maps populated, no run record, and no error transcript entry. Combined with finding 2, the session is locked forever. **Fix:** move `mark_run_started` (or the entire post-lock body) inside the try so the existing finally always runs.

### 2. No crash recovery — a killed process permanently sticks the session
`mark_run_finished` is called from exactly one place: the `finally` at `runtime.py:812`. There is no startup/lifespan reconciliation anywhere (grep for recover/reconcile/stale/orphan across host and core: nothing). After `kill -9` mid-run:
- disk `in_flight_run_id` survives; in-memory maps are gone
- `abort` returns `{"aborted": false}` — it only consults `_active_abort_by_run` (`orchestrator/__init__.py:165-167`)
- every future send raises `session is in flight: <dead-run>` (`session_store.py:359-360`)
- the orphaned run gets no RunRecord (RunStore only writes at finalize)

The only escape is hand-editing `index.json`. **Fix:** on `Orchestrator.__init__`, clear all persisted `in_flight_run_id` values (fresh process ⇒ none can be live, single-host assumption) and append a synthetic `status: "interrupted"` run record for each.

## High

### 3. Corrupt index → silent empty → next write destroys all sessions
`session_store.py:393-396`: `_load_map` swallows `OSError`/`JSONDecodeError` and returns `{}`. Every mutator is load→modify→`_save_map`, so one corrupt byte (or transient read failure) means the next rename/archive/run-start atomically replaces `index.json` with a near-empty file. Transcripts survive on disk but are keyed by now-unknown session ids. **Fix:** raise on corrupt index, write a `.bak` before replace, never save a map derived from a failed load.

### 4. The in-flight check-and-set is not atomic across processes
`SessionStore` uses only `threading.RLock` (`session_store.py:96`); the orchestrator's `asyncio.Lock` (`runtime.py:130`) is per-process. The documented CLI lane (`uv run copenet chat send`) and the running host are separate processes sharing `index.json`: both can load (in-flight None), both pass the `mark_run_started` check, both write — two concurrent runs on one session, interleaved transcript appends, and every concurrent `_save_map` is a whole-file lost-update (one process's `provider_session_id`/title/archived writes silently erased by the other's stale snapshot). **Fix:** `fcntl.flock` around load-modify-save, or make the CLI talk to the host RPC instead of opening the stores directly.

### 5. A retried send with the same idempotency key double-runs and unlocks early
The dedupe cache is only populated at completion (`runtime.py:733`), so a client retrying `chat.send` with the same `idempotencyKey` mid-stream produces the same `run_id`. The guard at `runtime.py:136-137` passes when `active_run == run_id`, and `mark_run_started` allows `in_flight_run_id == run` (`session_store.py:359`). Result: duplicate user transcript append, two interleaved provider executions, duplicate run records — and whichever finishes first runs the finally and clears the lock while the other is still mid-run, letting a third send start concurrently. **Fix:** treat `active_run == run_id` as in-flight (return `{"status": "in_flight"}`); admit a run id once.

### 6. Binding-lock null hole (cross-referenced)
`session_store.py:267-286` only enforces locks for non-empty stored fields and never back-fills, so a session created without a task mode can be escalated to `full-access` on any later send via `runtime.py:280`. Full detail in `03-architecture-integrity.md`. **Fix:** persist resolved bindings onto the entry on first send.

## Medium

### 7. Failure after the ok run record yields a second contradictory record under the same run_id
If anything between `run_store.create(run_record)` (`runtime.py:618`) and return raises (artifact/profile/memory side effects, or `await emit(final_payload)` at 725 on a non-swallowing emit lane like the SSE queue), the except block (`runtime.py:751-784`) appends a *second* RunRecord with the same `run_id`, `status="error"`. `RunStore.create` is append-only with no dedupe, and `RunStore.get` iterates `reversed(...)` (`runs.py:209-214`) so the error record shadows the committed ok record — even though the assistant transcript entry (line 527) is already durable. **Fix:** a `run_recorded` flag after line 618; skip the failed-record create when set.

### 8. Failed runs leave a user turn with no transcript response
The except path (`runtime.py:737-806`) emits an error event and writes a failed run record but appends nothing to the transcript — partial streamed text is dropped, and history replay re-feeds a user message with no assistant turn. Append-only is preserved; the asymmetry is durability between transcript and run store. **Fix:** append an assistant entry with `state="error"` (or the partial text) in the except path.

## Low

- **9. fsync gaps.** `_save_map` renames without fsync (`session_store.py:416-418`) — power loss can leave a zero-length index, which then trips finding 3. `RunStore.create` appends without flush/fsync (torn tail line; read path skips bad lines, self-healing). `TranscriptStore` does it right (`transcript_store.py:97-98`); mirror it.
- **10. Duplicate RPC response frame on SessionInFlightError.** `rpc_chat.py:116-120` answers `request_id` with `status: "started"`, then `rpc_chat.py:157-167` sends a second ResponseFrame with the same id on SessionInFlightError. Deliver the in-flight outcome as a chat event instead.
- **11. Merge/pulse brief appends bypass the in-flight lock.** `merge.py:202` and `pulse.py:222` append synthetic assistant messages without `mark_run_started`; a concurrent send during merge hydration interleaves. Ordering only — appends remain atomic.

## Verified intact

- **Append-only transcripts:** `TranscriptStore` has no mutation API; exhaustive caller grep found only runtime appends, merge/pulse briefs, and `copy_history` into new sessions. `append_message` opens `"a"`, flushes, fsyncs under a lock.
- **Atomic index writes:** temp-file + `Path.replace` (`session_store.py:412-418`); nothing writes `index.json` directly outside SessionStore.
- **Provider/model binding:** strictly enforced (`session_store.py:255-262`); no assignment sites outside the store; merge/debug-copy honor "new chat instead of in-place rebind."
- **`in_flight_run_id` write sites are exactly two** — `mark_run_started` (`:361`) and `mark_run_finished` (`:383`, clears only on run-id match) — plus creation. The holes are lifecycle coverage (1, 2), not rogue writers.
- **In-process concurrency with distinct run ids is safe:** check-and-set under `orchestrator._lock` with no awaits on shared state between check and mark.
- **Abort doesn't bypass the lock** (cleanup flows through the normal finally), and the trace writer fails closed.

**Highest-leverage fixes in order: #1, #2, #3 — together they close every "session bricked / index wiped" path found.**
