# CopeNet Audit Reconciliation — Codex vs. Claude

Date: 2026-07-24  
Repository commit: `c188fa7cf063e8babab3a9a42a557ddf34d04709`  
Claude source: `docs/audit/independent-audit-2026-07-24.md`  
Codex source: independent audit delivered in the preceding Codex thread

## Purpose

This document reconciles the two independent audits into one repair-oriented view. It is not a
simple union of every observation. It separates:

1. defects independently found by both auditors;
2. Codex findings Claude missed or only partially covered;
3. Claude findings that should remain even though Codex did not report them;
4. lower-confidence or threat-model-dependent items that should not displace product correctness;
5. statements in either audit that should be revised in light of the other auditor's evidence.

ID notation:

- `C-A-###` means the finding ID in the Codex audit.
- `CL-A-###` means the finding ID in Claude's audit.

## Bottom line

The audits agree on the repository-level diagnosis: CopeNet is coherent, not structurally
unstable, and most serious failures are localized boundary defects rather than reasons for a
rewrite.

The strongest combined repair case is not the security cluster. It is:

- session identity and runtime inheritance;
- restart/idempotency/recovery truth;
- cancellation and admission behavior;
- frontend reconnect/error state;
- Market Monitor cache and backtest validity;
- durable-store corruption handling;
- run/event/artifact provenance.

Claude found more low-severity cleanup and uncovered several real transport/persistence defects that
Codex did not report. Codex's isolated runtime probes found a smaller set of higher-impact state
failures that Claude missed, including persistence collisions, first-send binding failure,
restart duplication, cache destruction, recovery misclassification, and cross-tool approval
pollution.

## 1. Independently corroborated findings

These should stay in the combined audit. Wording and severity should be normalized, but the
underlying defects are supported by both reviews.

| Combined topic | Codex | Claude | Reconciled conclusion |
|---|---:|---:|---|
| Default `dev-token` gateway credential | C-A-001 | CL-A-001 | Confirmed. Important when the host is reachable outside its intended local boundary. Codex additionally reproduced cross-origin WS access; Claude additionally noted non-constant-time comparison. Treat as operational hardening unless remote binding is supported in production. |
| Private/loopback web fetching | C-A-013 | CL-A-003 | Confirmed SSRF/network-boundary gap in shared `WebIngestionService`. Fix at the ingestion boundary so tool and REST callers inherit it. |
| Cross-transport runtime drift | C-A-005 | CL-A-004, CL-A-007, CL-A-008, CL-A-022 | Confirmed, but broader than either single finding. Prompt composition, model inheritance, profile/Access omission, persona inheritance, and REST error translation should be repaired together in core. |
| Active-run reconnect loses assistant output | C-A-011 | CL-A-005 | Confirmed by identical call-path tracing. High-value daily-driver repair. |
| `chat.send` acknowledges before admission | C-A-012 | CL-A-006 | Confirmed. The server can emit two response frames for one request ID; the frontend consumes the first and strands an optimistic run. |
| Native tool loop ignores cancellation | C-A-010 | CL-A-011 | Confirmed. `tool_loop_native.py` deletes `abort_event`. |
| High-risk shell gate uses substring matching | C-A-008 | CL-A-019 | Confirmed. Codex demonstrated common equivalent command forms that evade the intended approval pause. |
| Off-manifest registered tools remain callable | C-A-018 | CL-A-028 | Confirmed. `MANIFEST_TOOL_IDS` limits advertisement, not execution authority. |
| Backtest backward-fill lookahead | C-A-016 | CL-A-033 | Confirmed. Severity should follow Codex's deterministic reproduction, not Claude's "minor" label: a pre-inception asset produced an impossible 50% portfolio gain. Treat as High financial correctness. |
| Wrong benchmark return in model-facing artifact | C-A-024 | CL-A-012, CL-A-025 | Confirmed. The field is relative outperformance but one renderer adds it to portfolio return. Rename the metric and remove reconstruction math from consumers. |

### Partial corroboration

| Topic | Codex | Claude | What remains distinct |
|---|---:|---:|---|
| Idempotency cache | C-A-006 | CL-A-027 | Claude found unbounded memory/stale reuse. Codex found the more serious behavior: the dedupe state is memory-only, so a restart retry duplicates transcript entries, provider work, and side effects. Both should be fixed through one durable admission design. |
| Durable JSON handling | C-A-007 | CL-A-009, CL-A-017, CL-A-023, CL-A-035 | Claude found individual non-atomic or unguarded stores. Codex demonstrated the systemic failure in `_json_store.read_json`: corruption becomes an empty valid store and a later mutation overwrites recoverable data. The systemic contract should lead; individual stores are migration targets. |
| Approval semantics | C-A-008, C-A-009 | CL-A-019 | Both found the weak shell matcher. Claude did not find Codex's separate cross-tool escalation: “always allow” for `files.write` can persist its target into the global unrestricted shell allowlist. |

## 2. Codex findings Claude missed

These were not present in Claude's findings table, or Claude's executive/healthy-pattern statements
implicitly treated the area as sound. Each was either reproduced with an isolated temporary-store
probe or established through a complete call path.

### C-A-002 — External app can cancel an unrelated run

- Files: `src/copenet/host/app_api.py:636-644`,
  `src/copenet/core/orchestrator/__init__.py:235-246`
- Defect: `cancel_run` calls `Orchestrator.abort(run_id=...)` even when the run was not found in an
  app-owned session. `abort` does not validate the run/session relationship.
- Why it stays: it is a direct ownership failure with a small repair, even if external apps are
  currently trusted.
- Verification: two apps plus an operator session; every cross-owner cancellation must fail without
  changing the foreign abort event.

### C-A-003 — Accepted session keys collide in durable stores

- Files: `core/sessions/session_store.py:150-213`, `core/runtime/runs.py:141-145`,
  `core/runtime/artifacts.py:16-17,93-98`, `core/sessions/state_store.py:15-16,99-104`
- Defect: SessionStore accepts keys such as `a/b` and `ab`; the other stores delete unsupported
  characters, mapping both identities to the same files.
- Probe result: run records, artifacts, and state written through one key were visible through the
  other.
- Why it stays: cross-session durable-state mixing violates one of CopeNet's central invariants.

### C-A-004 — Nullable immutable bindings are never established on first send

- File: `core/sessions/session_store.py:261-345`
- Defect: profile/persona/workspace are compared only if already populated. A draft with null fields
  accepts different values on later sends while its stored binding remains null.
- Probe result: first send with A followed by B was accepted; persisted fields remained null.
- Why it stays: Claude's statement that binding reconciliation is solid applies only to pre-populated
  bindings. The first-send transition remains broken.

### C-A-006 — Idempotency does not survive restart

- Files: `core/orchestrator/__init__.py:168`, `core/orchestrator/runtime.py:161-200`
- Defect: durable RunStore data is not consulted during dedupe admission.
- Probe result: two orchestrators sharing the same directories accepted the same session/run key and
  appended duplicate user/assistant turns and duplicate terminal run records.
- Why it stays: this is more consequential than the cache-growth issue in CL-A-027.

### C-A-007 — Corrupt JSON can be silently overwritten as an empty store

- File: `core/_json_store.py:10-24` and every read-modify-write store using it
- Defect: missing files, permission/read errors, and malformed JSON all return the same fallback.
- Probe result: after corrupting a populated MemoryStore and AppStore, listing returned empty and the
  next mutation replaced the original content with only the new item.
- Why it stays: this is a systemic data-loss mode. Claude's per-store atomicity findings should be
  folded into this repair rather than handled as unrelated patches.

### C-A-009 — Non-shell “always allow” approval pollutes shell authority

- Files: `core/orchestrator/runtime.py:51-94`,
  `core/tools/handlers/shell.py:257-272,435-445`
- Defect: the generic approval wrapper stores `output.command or output.target` in the global shell
  permission store for every approved tool.
- Probe result: approving a `files.write` target such as `./script.sh` persisted that text as a shell
  command; a later read-only run could execute it through standing approval.
- Why it stays: this contradicts Claude's healthy-pattern statement that approval sets are correctly
  tool/argument scoped.

### C-A-014 — Market symbol paths are not contained

- File: `core/market/store.py:102-117`
- Defect: read/bar/signal filenames interpolate an arbitrary uppercased symbol without validation.
- Probe result: `save_ticker_read("../escaped", ...)` wrote outside `reads/`.
- Priority: lower in a trusted local UI than financial math/cache defects, but the repair is small
  and should be done alongside canonical ticker validation.

### C-A-015 — Failed Market refresh erases valid bars and publishes false live state

- File: `core/market/runtime.py:286-307,417-433`
- Defect: fetch exceptions become empty frames; empty frames overwrite valid cached bars; zero breadth
  is then published as `status="live", current="risk-off"`.
- Probe result: a seeded VOO cache became empty after a forced transient fetch failure and the
  dashboard reported live/risk-off.
- Why it stays: this is one of the highest-priority product findings in either audit.

### C-A-017 — Incomplete Responses stream is recorded as successful

- Files: `providers/openai_codex.py:335-435`,
  `core/harness/tool_loop_responses.py:89-125`
- Defect: the provider emits `responsesCompleted: false` after premature EOF, but the harness ignores
  it and emits a normal final event when no function calls were collected.
- Probe result: partial text plus an incomplete marker produced a final event and an `ok` run.
- Why it stays: truncated provider responses become false success in transcript/run history.

### C-A-019 — Crash recovery can overwrite durable success with “interrupted”

- Files: `core/orchestrator/__init__.py:183-229`,
  `core/orchestrator/runtime.py:695,861-866`, `core/runtime/runs.py:209-214`
- Defect: if the process exits after writing the successful RunRecord but before clearing
  `in_flight_run_id`, startup unconditionally appends an `interrupted` record with the same ID.
- Probe result: `RunStore.get` returned the later interrupted record instead of the prior success.
- Why it stays: Claude's healthy-pattern statement that startup recovery “works” needs this crash
  window qualification.

### C-A-020 — WebSocket schema drops fields emitted by core

- Files: `host/rpc_chat.py:87-101`, `host/rpc_schema.py:22-36,117-137`
- Defect: reasoning text, `identityContext`, `agentContext`, and `harnessDecision` are not represented
  in `ChatEventPayload` and are discarded before reaching the frontend.
- Why it stays: frontend code consumes some of these fields, so this is an active contract break,
  not unused telemetry.

### C-A-021 — Oversized tool artifacts carry the tool call ID as run provenance

- Files: `core/harness/tool_result_materialization.py:79-91`,
  `frontend/src/runtime/activityProof.ts:206-224`
- Defect: materialization writes `run_id=tool_result.call_id`; frontend groups only artifacts whose
  `artifact.runId === run.runId`.
- Why it stays: large outputs persist but disappear from their run's observable proof.

### C-A-022 — One auxiliary bootstrap failure prevents the entire UI from loading

- File: `frontend/src/lib/wsBootstrapAction.ts:36-118`
- Defect: core and optional RPCs share one `Promise.all`; state is committed only after all succeed.
- Why it stays: a corrupt Pulse/persona/messaging store can make sessions and history unusable even
  when the chat backend is healthy.

### C-A-023 — Debug-copy graph is internally inconsistent

- Files: `core/orchestrator/catalog.py:208-267`, `core/runtime/runs.py:156-186`
- Defect: persona fields are omitted; runs are cloned before artifacts and retain the source artifact
  IDs while cloned artifacts receive new UUIDs.
- Probe result: copied runs referenced artifacts absent from the target session's ledger.
- Why it stays: debug copies are supposed to preserve the evidence needed to reproduce a problem.

## 3. Claude-only findings that should stay

These were not called out in the Codex report but are supported by the current implementation and
should remain in the combined repair backlog.

### High-value runtime and transport findings

1. **CL-A-004 — Prompt composition occurs only in the WebSocket transport.**  
   Keep and merge with C-A-005. `compose_prompt` belongs in the orchestrator/core path so CLI,
   REST/SSE, Telegram, and WS receive identical behavior.

2. **CL-A-007 / CL-A-008 — Omitted model uses provider/app default rather than session binding.**  
   Keep and merge with the transport-inheritance repair. The effective model should be resolved once
   from the admitted session entry, then used for provider execution and every audit stamp.

3. **CL-A-010 — A provider that ignores abort can leave a session in flight indefinitely.**  
   Keep as a confirmed architectural weakness with runtime reproduction still required. The fix
   likely needs a cancellable task/timeout and an explicit terminal transition, not just an event.

4. **CL-A-014 — Partial output hides terminal error presentation.**  
   Keep. `MessageBubble` displays `errorMessage` only when there is no content or parts, so a failed
   run with partial output looks successful.

5. **CL-A-022 — Omitted persona is re-resolved against the global default.**  
   Keep and merge with C-A-004/C-A-005. Existing locked sessions should inherit their stored persona,
   not today's global default.

### Persistence findings

6. **CL-A-009 — SessionStateStore has no corrupt-file recovery contract.**  
   Keep, but do not “recover” by silently returning an empty state. Route it through the same
   fail-loud/quarantine contract recommended for C-A-007.

7. **CL-A-017 — Persona identity/flavor files are written non-atomically.**  
   Keep. Several existing persona files are directly overwritten while `USER.md` already uses an
   atomic helper.

8. **CL-A-023 — Webull account and portfolio snapshots are non-atomic and parse failure becomes
   absence.**  
   Keep. This can make a configured account appear disconnected after a partial write.

9. **CL-A-024 — ProviderAuthStore lock can be orphaned by process death.**  
   Keep as a small recovery repair. Add owner PID/creation time and bounded stale-lock cleanup.

10. **CL-A-035 — Generic atomic JSON helper lacks fsync and uses a shared temp name.**  
    Keep as part of the C-A-007 store-hardening project. Use unique same-directory temp files,
    flush/fsync, replace, and directory fsync where the durability guarantee matters.

### Harness, API, and maintainability findings

11. **CL-A-029 — Prompted loop only includes the immediately preceding step's tool results.**  
    Keep as a low-priority divergence risk. It is masked for current Claude resume behavior, but the
    generic prompted loop does not honor its provider-agnostic contract.

12. **CL-A-030 — Resume behavior branches on provider name despite a capability flag.**  
    Keep as focused architectural drift. Replace the name allowlist with normalized provider
    capability metadata.

13. **CL-A-031 — `hello-ok.features.methods` is stale.**  
    Keep. Generate advertisement from the canonical dispatch catalog or test exact parity.

14. **CL-A-032 — “No evidence” and “evidence unavailable” are conflated.**  
    Keep. This is a financial honesty issue even if low severity.

15. **CL-A-026 — Error guidance names retired tools.**  
    Keep as a small cleanup because it directly wastes model turns.

16. **CL-A-034 / CL-A-038 — Contributor docs and dead tool mappings reference deleted surfaces.**  
    Keep as cleanup after runtime fixes.

17. **CL-A-041 — Research Lab's documented durability does not exist.**  
    Keep as a contract decision: either implement durable dossiers or change the subsystem
    description so callers do not assume persistence.

### Verification gaps, not production defects

The following Claude entries should remain in the verification plan, but should not be counted as
confirmed production defects:

- **CL-A-020:** no negative regression test for outside-workspace writes.
- **CL-A-021:** no automated split-adjust invariant test.
- **CL-A-037:** unguarded `toolSteps` is speculative until a supported legacy/partial payload is
  demonstrated.

The split-adjust test is particularly important because the invariant is load-bearing and has caused
a real incident, even though both audits verified that the current callers are correct.

## 4. Findings to defer, demote, or adjudicate

These are useful observations, but they should not compete with current data-integrity and runtime
work.

| Finding | Recommendation |
|---|---|
| CL-A-002 / CL-A-018 / CL-A-039 / CL-A-040 | Treat as a threat-model/operating-mode decision. CopeNet is a local user-level agent harness, so secret-read/egress and local plaintext-token concerns depend heavily on whether untrusted prompts and remote binding are supported. |
| CL-A-013 synthetic flag | Do not call this a current false historical replay. UI/artifact wording says “Simulated” and “Projected,” and `shockDetails` is present. A `synthetic: true` field is worthwhile machine-readable hardening. |
| CL-A-015 stale `sessions.list` race | Retain as a suspicion until an overlapping-refresh timing test reproduces Stop/tool-feed detachment. |
| CL-A-016 first-delta-before-ack duplicate | Retain as a suspicion until an artificial fast-event/slow-response test reproduces two bubbles. |
| CL-A-036 import-time MemoryRecord defaults | Low cleanup unless direct construction outside store factory paths is shown. |
| CL-A-042 Telegram confused-deputy | Future integration checklist, not a current defect; Claude found no inbound Telegram handler. |
| C-A-001 cross-origin/default token | Keep as operational hardening, but lower its repair priority if the product contract is strictly loopback/local and no untrusted web content is in scope. |
| C-A-014 market path traversal | Keep as input/storage correctness with a small fix, but prioritize financial cache and backtest defects first in a trusted single-user deployment. |

## 5. Statements in Claude's audit that should be revised

These are not reasons to reject Claude's audit. They are places where Codex's probes add a necessary
qualification.

1. **“Session binding reconciliation is locally solid.”**  
   Revise to: populated bindings are enforced correctly, but null immutable fields are not adopted
   on first send and can remain permanently unlocked (C-A-004).

2. **“Startup crash recovery works.”**  
   Revise to: it unbricks genuinely interrupted sessions, but can append a false interrupted record
   after durable success in the record-written/marker-not-cleared crash window (C-A-019).

3. **“Approval sets are keyed correctly.”**  
   Revise to distinguish the in-run Barricade argument digest from the global permission store.
   Generic `approved_always` can persist a non-shell target as unrestricted shell authority
   (C-A-009).

4. **“Backfill lookahead is minor.”**  
   Revise severity. A deterministic staggered-inception example generated a 50% impossible portfolio
   gain. This is High when arbitrary user portfolios or IPO/fund inception dates are supported.

5. **“All lanes converge through `send_chat`, therefore semantics are unified.”**  
   Convergence is structurally good, but request normalization remains transport-owned. Missing
   prompt/model/profile/persona/Access values change behavior before and inside the shared core path.

6. **“The point-in-time replay/base-rate path is lookahead-clean.”**  
   This statement can remain for `replay.py`; it should not be generalized to the separate portfolio
   backtester, which contains the confirmed `.bfill()` lookahead.

## 6. Combined repair backlog

This is the recommended union, ordered for realistic product impact in a trusted local repository.

### P0 — State identity, financial correctness, and silent data loss

1. **Canonicalize session identity across every store**  
   Covers C-A-003. Validate session keys at ingress or use injective/hash filenames, with collision
   detection for existing data.

2. **Make first-send binding adoption atomic and explicit**  
   Covers C-A-004 and CL-A-022. Store provider/profile/persona/workspace on first admitted send;
   inherit stored values thereafter.

3. **Replace backward-fill in portfolio backtests with an explicit investability policy**  
   Covers C-A-016/CL-A-033. Never synthesize prices before inception.

4. **Preserve last-known market data on refresh failure**  
   Covers C-A-015. Never replace good bars with an empty fetch and never label a failure-derived
   regime as live.

5. **Adopt a shared corrupt-store contract**  
   Covers C-A-007, CL-A-009, CL-A-017, CL-A-023, and CL-A-035. Missing is not the same as unreadable;
   quarantine/fail loud and do not overwrite recoverable state.

### P1 — Run admission, cancellation, and recovery truth

6. **Persist idempotent run admission**  
   Covers C-A-006/CL-A-027. Deduplicate by `(session_key, run_id)` across restart, bound retention,
   and define in-progress/terminal retry results.

7. **Acknowledge `chat.send` only after admission**  
   Covers C-A-012/CL-A-006. Exactly one RPC response per request; explicit terminal handling for a
   rejected optimistic run.

8. **Make cancellation authoritative in every provider/tool loop**  
   Covers C-A-010/CL-A-010/CL-A-011. Check before provider calls and side effects, plus a bounded
   force-finalize path for providers that ignore cancellation.

9. **Preserve terminal truth during startup recovery**  
   Covers C-A-019. Do not synthesize interruption if the same run already has a durable terminal
   record.

10. **Honor provider completion metadata**  
    Covers C-A-017. Premature Responses EOF must end as error/aborted, never `ok`.

### P2 — Runtime parity and approval authority

11. **Resolve one effective runtime in core**  
    Covers C-A-005 and CL-A-004/A-007/A-008/A-022. Resolve omitted values from the session binding,
    compose prompts in core, distinguish omitted from explicit changes, and stamp exactly what ran.

12. **Make approvals tool-specific**  
    Covers C-A-008/C-A-009/CL-A-019. Persist `(tool_id, canonical argument digest)` rather than raw
    targets in a global shell namespace; strengthen destructive shell classification.

13. **Enforce the run's exact offered tool IDs**  
    Covers C-A-018/CL-A-028. Preserve a separate explicit internal-call surface if needed.

14. **Fix external-app run ownership on cancellation**  
    Covers C-A-002. Validate both at the API mapping boundary and inside `abort`.

### P3 — Frontend and observability truth

15. **Reconcile pending messages before replacing history**  
    Covers C-A-011/CL-A-005.

16. **Always render terminal error state alongside partial content**  
    Covers CL-A-014.

17. **Preserve the complete chat-event contract**  
    Covers C-A-020. Add schema fields and a backend/frontend fixture.

18. **Correct run provenance for materialized tool artifacts**  
    Covers C-A-021.

19. **Degrade optional bootstrap subsystems independently**  
    Covers C-A-022.

20. **Repair debug-copy reference remapping**  
    Covers C-A-023.

### P4 — Market reporting and honesty

21. **Store actual benchmark return and excess return as separate fields**  
    Covers C-A-024/CL-A-012/CL-A-025.

22. **Distinguish evidence-empty from evidence-unavailable**  
    Covers CL-A-032.

23. **Validate ticker identifiers before storage/network use**  
    Covers C-A-014.

24. **Add split-adjust invariant tests**  
    Covers CL-A-021.

25. **Add `synthetic: true` to scenario results**  
    Covers CL-A-013 as hardening, not as evidence that the current UI claims historical replay.

### P5 — Focused cleanup

26. Repair prompted-loop result accumulation and capability-based resume selection
    (CL-A-029/CL-A-030).
27. Generate advertised WS methods from a canonical catalog (CL-A-031).
28. Fix retired-tool guidance and dead mappings (CL-A-026/CL-A-038).
29. Reconcile deleted shim documentation (CL-A-034).
30. Decide whether Research Lab is durable or documented as in-memory (CL-A-041).
31. Add stale-lock recovery to ProviderAuthStore (CL-A-024).

## 7. Suggested verification bundles

The repairs should be verified by behavior bundle rather than one test per file.

### Session/restart bundle

- Draft with null profile/persona/workspace adopts values on first send.
- Later changes reject; same-provider model and explicit Access changes still reconcile.
- `a/b` and `ab` cannot share any run/artifact/state path.
- Same idempotency key before and after orchestrator restart produces one transcript turn and one
  terminal run.
- Recovery after each persistence boundary preserves the correct terminal status.

### Transport parity bundle

- WS, CLI, REST/SSE, GatewayClient, and messaging route produce the same effective
  provider/model/profile/persona/workspace/Access and composed system prompt.
- Omitted values inherit; explicit model/Access changes remain auditable.
- Concurrent sends produce exactly one response per request and no orphan optimistic message.

### Tool/approval/cancellation bundle

- Every loop stops before a provider request and before every tool side effect after cancellation.
- Registered but unoffered tool IDs are rejected.
- “Always allow” is isolated by tool ID and argument digest.
- Equivalent destructive shell forms receive the same decision.
- Incomplete provider streams never persist as successful.

### Frontend continuity bundle

- Disconnect during streaming, reload history, resume deltas, and finalize without loss or
  duplication.
- Partial output plus terminal error visibly remains an error.
- Missing optional bootstrap RPCs do not prevent session/history use.
- Oversized tool artifacts appear under the originating run.

### Market bundle

- Total and partial fetch failures retain last-known bars and mark stale/error honestly.
- Staggered asset inception never permits investment before the first real bar.
- All consumers agree on portfolio return, benchmark return, and excess return.
- Evidence failure is not rendered as “no evidence.”
- Every `fetch_ohlcv` cache writer remains split-adjusted.

## 8. Recommended review outcome

Claude should review this reconciliation by:

1. confirming or disputing each Codex-only reproduction, especially C-A-003, C-A-004, C-A-006,
   C-A-009, C-A-015, C-A-017, and C-A-019;
2. revising the healthy-pattern statements where those probes establish a crash window or nullable
   first-send exception;
3. deciding whether the combined backlog ordering matches the product's trusted-local deployment
   assumptions;
4. keeping Claude's broader low-severity findings as a later cleanup/verification layer rather than
   allowing them to dilute the smaller high-impact runtime set.

