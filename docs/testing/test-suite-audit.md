# CopeNet Test Suite Audit

Audit date: 2026-07-30

Scope: all tests collected from `tests/` and `src/copenet/host/frontend/tests/`.

Companion inventory: [`docs/testing/test-inventory.json`](test-inventory.json)

## 1. Executive summary

### What was found

- **804 executed test cases** across **145 files** and **782 logical test groups**.
  - 707 Python/pytest cases: 580 under `tests/unit/`, 127 under `tests/integration/`.
  - 97 frontend cases run with Node's built-in `node:test` through `tsx`.
- Frameworks and test utilities:
  - pytest and `pytest-asyncio`
  - FastAPI/Starlette `TestClient`, including in-process WebSocket tests
  - Node `node:test` and `node:assert`
  - React `renderToStaticMarkup` for eight component-smoke cases
- Baseline execution was healthy:
  - Python: **707 passed in 27.44 seconds**
  - Frontend: **97 passed in 1.23 seconds**
- There are **no true browser end-to-end tests** in the deterministic suite. The file named
  `test_multiturn_responses_e2e.py` is a strong in-process integration test with a fake
  provider, not a deployed-system E2E test.
- The frontend test command emits Node's `DEP0205 module.register()` deprecation warning once
  per worker/file. This does not currently fail tests, but it is infrastructure noise.

The suite is not merely coverage filler. Its strongest areas—session identity, transcript and
tool replay, tool policy, prompt-protocol security, market accounting, Fleet ordering, and
provider response parsing—protect realistic and costly regressions.

It is, however, accumulating. The clearest signs are:

- phase-era characterization files that outlived the phase they describe;
- repeated fake-provider scaffolding and overlapping harness checks;
- direct frontend setter tests and detached responsive helpers;
- exact CSS, prompt-copy, static-catalog, and private-argv assertions;
- isolated test islands whose current product entrypoint is unclear;
- happy-path persistence tests without corresponding concurrency or recovery tests.

### Classification distribution

The machine inventory conservatively classifies every logical group:

| Classification | Logical groups | Collected cases | Share of 804 cases |
|---|---:|---:|---:|
| KEEP | 622 | 644 | 80.1% |
| KEEP, BUT IMPROVE | 37 | 37 | 4.6% |
| MERGE | 77 | 77 | 9.6% |
| MOVE UP | 7 | 7 | 0.9% |
| MOVE DOWN | 6 | 6 | 0.7% |
| DELETE | 12 | 12 | 1.5% |
| INVESTIGATE | 21 | 21 | 2.6% |

These are not coverage percentages. `KEEP` means the test has meaningful unique or
boundary-specific value; it does not mean the surrounding subsystem is sufficiently tested.
Likewise, `MOVE UP` and `MOVE DOWN` are valuable behaviors at the wrong verification layer.

As a broader health estimate:

- **75–82%** is high-value protection;
- **9–12%** is primarily consolidation opportunity;
- **5–8%** is valuable but brittle, weakly asserted, or at the wrong layer;
- **1–2%** is high-confidence obsolete, tautological, or redundant coverage;
- **2–3%** has unclear current product relevance.

### Overall suite health

**Overall: good regression intent, uneven architecture.**

The suite is fast and deterministic, and it contains several excellent regression tests with
clear bug history. Confidence is weaker than the raw count suggests because the suite is heavily
weighted toward pure units and in-process happy paths. Important failure and isolation boundaries
are either absent or represented only below the public contract.

### Five most important findings

1. **The security and replay spine is the suite's highest-value coverage.** Prompted-tool
   delimiters, off-manifest rejection, Barricade taint, exact-call approval, session locks,
   tool-result envelopes, and two-turn replay are intentional defense-in-depth and should remain.
2. **The current max-tool-step tests do not test the cap.** A controlled mutation removed the
   prompted-loop cap branch; both cap-named tests still passed because they drive only five calls
   while the configured cap is 100.
3. **External-app and attachment isolation is a critical untested boundary.** Chat attachments
   are globally addressed and do not carry app ownership, while no two-app IDOR contract test
   exists.
4. **Frontend coverage stops below the user workflow.** There are good state and formatting
   units, but no deterministic browser test for first-send locking, reconnect, approval,
   archive/restore, cancellation, or live tool activity.
5. **The Market suite is numerically strong but misses its two load-bearing architectural
   invariants.** Only one valuation helper explicitly tests split adjustment; no suite-wide test
   protects every `fetch_ohlcv()` caller, and no price-overlay/backtest test proves alignment to
   `availableAt` rather than `periodEnd`.

## 2. Audit method

The audit did not judge tests from filenames alone. Work performed:

1. Collected every Python test with `pytest --collect-only`.
2. Parsed Python and frontend test files into a per-function/group inventory.
3. Ran the complete Python and frontend suites.
4. Mapped imports and representative assertions back to production modules.
5. Searched for duplicate test bodies, repeated fixtures, dead helper consumers, isolated
   production packages, and architecture-sensitive keywords.
6. Compared overlapping coverage at unit, harness, orchestrator, transport, and frontend layers.
7. Performed one controlled mutation:
   - changed the cap branch in
     `src/copenet/core/harness/tool_loop_prompted.py` so it could not fire;
   - ran
     `test_max_tool_steps_was_lifted` and
     `test_tool_loop_caps_at_max_tool_steps`;
   - both passed;
   - restored the production file and verified a clean diff.

No tests or production behavior were refactored during the audit.

## 3. Test suite map

Counts below use collected parameter cases, not just function definitions.

| Production area | Test locations | Cases | Predominant level | Protected well | Over-tested or noisy | Under-tested |
|---|---|---:|---|---|---|---|
| Tools, policy, and security | `test_shell_tool.py`, `test_barricade.py`, `test_file_tools.py`, `test_prompted_tool_protocol.py`, approval/tool-result/workspace tests | 152 | Unit, security unit, focused integration | Access matrix, destructive command classification, taint, egress/secret checks, prompted-tool syntax, result envelopes | Command examples split into many functions; retired-tool negatives repeated | Symlink/path replacement, shell grammar fuzzing, real approval reconnect, abort during side effects |
| Market Monitor | `tests/unit/test_market_*.py`, frontend market helpers | 147 | Deterministic unit, direct RPC-handler contract | Trend states, Webull FIFO/splits/drift, cache preservation, canonical financials, watchlist migration, ledger behavior | Scalar metric examples, ticker transaction prose cases, direct handler wrappers | All-caller split-adjustment invariant, `availableAt` overlay alignment, vendor partial failure, persistence corruption |
| Frontend operator UI | `src/copenet/host/frontend/tests/` | 97 | Pure unit/store, 8 SSR smoke | Cross-session run isolation, approval preservation, message-part collapse, tool proof grouping, export fallback, diff/tokenizer helpers | Direct setters, exact copy, dead responsive helpers, exact Tailwind classes | Actual DOM/browser workflows, WS integration, viewport behavior, reconnect and approval UX |
| Harness, prompts, replay | `test_build_chat_messages.py`, `test_context_budget.py`, `test_responses_items.py`, tool-loop integrations, phase files | 76 | Unit and in-process integration | Full tool output replay, call/output pairing, context grouping, prompted/native/Responses paths | Phase-era duplication, repeated scripted providers, microscopic serialization cases | Real cap behavior, attachment replay, provider failure after partial/tool output, cancellation races |
| Provider adapters and auth | Claude, LM Studio, OpenAI Codex, Responses, provider-auth tests | 53 | Adapter unit/contract | SSE/JSONL parsing, partial reads, error events, auth refresh, load lifecycle | Exact catalogs, exact argv/payload details, event variants in separate tests | Abort during streams, malformed catalogs/JSON, nonzero CLI exits, HTTP status matrix |
| Host, RPC, and external API | `test_ws_rpc.py`, `test_app_api*.py`, `test_ws_broadcast.py`, token guard | 52 | In-process contract/integration | Auth handshake, chat transport, disconnect survival, REST/SSE happy paths, public wire shapes | One 1,231-line WS module; repeated auth route setup; some generic 422/`ok` assertions | Malformed WS frames, duplicate IDs, ordering/backpressure, cross-app isolation, upload endpoints |
| Sessions and runtime persistence | Session/transcript/state/run/artifact/json/edit-backup tests | 41 | Real-temp-directory unit | Locks, durable-key safety, corruption quarantine, append/read round trips, stale-run clearing | Access transitions and stale clearing split across overlapping tests | Multi-instance/process writes, truncated JSONL, crash recovery, schema migrations, ordering |
| Media, Meme, and web ingest | API media/meme/web tests, transcriber and ideation units | 36 | Unit and API integration | Auth, media import/download routes, ideation variants, knowledge pack and parsing | Exact authored prompt phrases; progress stream pins duplicate load count | Upload/transcribe security, size/type limits, cleanup on failure, SSRF/private URLs, cancellation |
| Persona, memory, messaging | Persona integration and service, memory/user notes, messaging/Telegram/Pulse stores | 32 | Unit and integration | Privacy tiers, corruption protection, approval lifecycle, route CRUD, prompt inclusion | Repeated CRUD mechanics and some direct state setters | Cross-session privacy isolation, simultaneous updates, failure recovery, version compatibility |
| Fleet, coordination, multi-agent | Fleet, lane runner, WS Fleet, frontend Fleet, `test_multiagent_orchestrator.py` | 28 | Unit and boundary integration | Fleet reveal barrier, lane attribution, cursor-on-failure, archive/hidden lanes | Twenty multi-agent tests cover a package with no discovered product caller | Confirm multi-agent product status; cancellation and durable recovery under concurrent lanes |
| Developer probe/MAO infrastructure | Runtime probe bundle, MAO manifest/scope, probe sweep | 23 | Infrastructure unit | Classification/reporting and hook scope rules | Large repeated synthetic probe payloads; mixed with product tests | Versioned fixture corpus, corrupt bundle behavior, explicit default-suite vs live-suite separation |
| Orchestrator lifecycle | Main orchestrator integration and run records | 19 | Integration | Streaming/finalization, merge partial failure, artifacts, route reuse, Pulse | Large local fake-provider definitions; some assertions stop at `status == ok` | Provider failure lifecycle, concurrent admission/idempotency, lock cleanup after every terminal path |
| Research Lab | `test_research_lab_*.py` | 19 | Unit and focused lane integration | Typed evidence, provenance, calculation warnings, prose discard, budget flagging | Dossier assertions include incidental prose/emoji | Public workflow/API, storage corruption, resume/partial gathering |
| Browser agent | `test_browser_agent_*.py` | 14 | State-machine unit | Stop rules, risk blocking, visible evidence, stuck detection | One observer ordering example | Real Playwright session, URL/domain safety, stale elements, timeout/cancel, untrusted-page injection |
| NASA | `test_nasa_wallpaper.py` | 10 | Unit with fakes | Image/video fallback, non-macOS guard, wallpaper preservation, scheduler output | Exact plist text | Service HTTP/cache validation and corrupt cache behavior |
| Movie Lab | `test_movies.py` | 5 | Unit | Spreadsheet semantics, ambiguity, TV hint, enrichment, recommendation diversity | Large hand-authored XLSX XML fixture | Bad workbooks, duplicate imports, TMDB timeout/rate limits, partial enrichment, store corruption |

## 4. Detailed findings

### F1. Replay and tool security duplication is mostly intentional

- **Files/tests**
  - `tests/unit/test_prompted_tool_protocol.py`
  - `tests/unit/test_barricade.py`
  - `tests/unit/test_tool_result_envelope.py`
  - `tests/integration/test_tool_loop.py`
  - `tests/integration/test_multiturn_responses_e2e.py`
- **Production**
  - `src/copenet/core/harness/tool_loop_common.py`
  - `src/copenet/core/harness/tool_loop_prompted.py`
  - `src/copenet/core/harness/tool_loop_responses.py`
  - `src/copenet/core/tools/barricade.py`
  - `src/copenet/core/orchestrator/messages.py`
- **Classification:** KEEP
- **Evidence:** The tests protect different failure boundaries:
  - parser units prove prose cannot become a call;
  - Barricade tests prove policy/taint decisions;
  - envelope tests prove blocked reasons reach the model;
  - harness tests prove execution and follow-up;
  - orchestrator replay proves persisted real output reaches turn two.
  Removing a lower test because a higher test also uses tools would reduce failure localization
  and leave different provider paths unprotected.
- **Recommended action:** Preserve this layered contract. Consolidate only same-boundary fixture
  variants.
- **Confidence:** High
- **Risk of change:** High if layers are removed; low for table-driven consolidation.

### F2. The max-tool-step suite gives a false behavioral guarantee

- **Tests**
  - `tests/integration/test_phase_0_quickwins.py::test_max_tool_steps_was_lifted`
  - `tests/integration/test_phase_minus_1_baseline.py::test_tool_loop_caps_at_max_tool_steps`
- **Production**
  - `src/copenet/core/harness/tool_loop_common.py::MAX_TOOL_STEPS`
  - `src/copenet/core/harness/tool_loop_prompted.py`
  - equivalent cap branches in native and Responses loops
- **Classification:** MOVE UP / KEEP, BUT IMPROVE
- **Evidence:** One test asserts only that the constant is at least 100. The other accepts both
  obsolete values 4 and 100 and drives five calls. With the prompted cap branch disabled, both
  tests still passed.
- **Recommended action:** Script `MAX_TOOL_STEPS + 1` requests, assert exactly
  `MAX_TOOL_STEPS` executions, terminal reason `max_turns`, and the user-visible cap
  explanation. Apply a shared contract to prompted, native, and Responses loops. Then delete the
  constant-only test.
- **Confidence:** High
- **Risk of change:** Low if the stronger behavioral contract lands first; high if the current
  test is simply deleted.

### F3. Phase-era files no longer describe the current architecture

- **Files**
  - `tests/integration/test_phase_0_quickwins.py`
  - `tests/integration/test_phase_minus_1_baseline.py`
- **Classification:** MOVE DOWN, MERGE, KEEP, BUT IMPROVE
- **Evidence:** These files contain direct file-handler/configuration units, registry negatives,
  RPC error handling, idempotency, transcript replay, and a dual-regime cap test. Comments still
  describe “Phase -1,” “current broken behavior,” and expected inversions that have already
  occurred.
- **Recommended action:** Move each behavior to its current owner:
  - file limits/pagination → file-tool units;
  - retired identifiers → manifest contract;
  - idempotency → orchestrator integration;
  - malformed params → RPC contract;
  - replay → message/replay integration.
  Preserve bug history in short test docstrings, not phase-owned modules.
- **Confidence:** High
- **Risk of change:** Low if moves preserve assertions; medium if bug history is discarded.

### F4. Three exact backend duplicates and one stronger-test overlap

- **Tests**
  - Duplicate registry negative:
    `test_workspace_intel_tools.py::test_tool_registry_does_not_expose_removed_experimental_tools`
    overlaps the same-named test in `test_tool_contracts.py`.
  - Same-session idempotency:
    `test_phase_minus_1_baseline.py::test_idempotency_cache_still_dedupes_within_same_session`
    overlaps `test_orchestrator.py::test_idempotency_key_returns_cached_status`.
  - Token estimator and oversized-current-turn:
    two tests in `test_build_chat_messages.py` overlap the same imported functions and assertions
    in `test_context_budget.py`.
  - Transcript persistence:
    `test_responses_turn_persists_tool_exchange_to_transcript` is subsumed behaviorally by the
    stronger two-turn replay test in the same file, but improves diagnosis.
- **Classification:** DELETE for the first three clusters; MERGE for the transcript-localization
  test.
- **Evidence:** Exact production call, input, and observable result are repeated at the same
  architectural boundary. The stronger owner test remains.
- **Recommended action:** Delete the four high-confidence duplicate cases listed in Section 6.
  Fold transcript-localization assertions into the two-turn test only if failure clarity remains
  acceptable.
- **Confidence:** High for exact duplicates; medium for transcript consolidation.
- **Risk of change:** Negligible for exact duplicates; low diagnostic risk for transcript merge.

### F5. Session semantics are strong but transition examples are fragmented

- **Tests**
  - locked provider/profile mismatch;
  - model/Access reconciliation;
  - null/full/none Access transition tests;
  - stale in-flight clearing tests.
- **Production:** `src/copenet/core/sessions/session_store.py`
- **Classification:** KEEP plus MERGE
- **Evidence:** Provider/profile locking, mutable same-provider model/Access, durable-key
  sanitization, and stale-run recovery are central product invariants. However, three Access
  transition functions differ mainly by stored/requested mode, and two stale-run tests repeat the
  same setup.
- **Recommended action:** Keep lock/reconciliation integration. Convert Access transitions to a
  stored/requested/expected table; merge stale cleanup into one state-transition test.
- **Confidence:** High
- **Risk of change:** Low if all transition rows remain.

### F6. One persistence compatibility test may encode data loss

- **Test:** `test_session_store.py::test_load_map_ignores_camel_case_storage_entries`
- **Production:** `SessionIndexEntry.from_json()` and `SessionStore._load_map()`
- **Classification:** INVESTIGATE
- **Evidence:** The test expects a plausible camelCase session record to disappear silently.
  That may be correct rejection of an impossible on-disk shape, or it may encode loss of data from
  an older release. Code alone cannot establish release history safely.
- **Recommended action:** Determine whether any released build wrote camelCase indexes. If yes,
  add migration/compatibility. If no, rename the test to state that malformed wire shapes are
  rejected and assert an actionable diagnostic rather than silent absence.
- **Confidence:** Medium
- **Risk of change:** High until history is known.

### F7. The persistence suite is happy-path heavy

- **Files:** session/transcript/state/run/artifact/json/edit-backup store tests
- **Classification:** KEEP, BUT IMPROVE
- **Evidence:** Real temp directories are used and corruption quarantine is tested for session,
  JSON, and memory stores. Run, artifact, transcript, and most specialized stores mainly prove
  create/list/get. Per-instance `RLock` does not prove safety across two store instances or
  processes.
- **Recommended action:** Add multi-instance concurrent writers, truncated last JSONL line,
  interrupted atomic replacement, old-record defaults, and ordering/idempotency tests.
- **Confidence:** High
- **Risk of change:** None to existing behavior; these are additive high-value tests.

### F8. `test_dispatch_rpc_returns_invalid_request_on_bad_param` permits its regression

- **Test:** `tests/integration/test_phase_minus_1_baseline.py::test_dispatch_rpc_returns_invalid_request_on_bad_param`
- **Production:** `src/copenet/host/rpc_dispatch.py`
- **Classification:** KEEP, BUT IMPROVE
- **Evidence:** The test name promises `INVALID_REQUEST` but accepts either `INVALID_REQUEST` or
  `INTERNAL_ERROR`. A regression to a generic internal failure still passes.
- **Recommended action:** Require `INVALID_REQUEST`, assert the request ID and actionable message,
  and verify a following request on the same socket still succeeds.
- **Confidence:** High
- **Risk of change:** Low; a failure would expose real boundary inconsistency.

### F9. WebSocket coverage is broad but structurally brittle and incomplete

- **File:** `tests/integration/test_ws_rpc.py` (1,231 lines, 22 logical tests)
- **Production:** `ws_server.py`, `rpc_schema.py`, `rpc_dispatch.py`, domain RPC modules
- **Classification:** KEEP, BUT IMPROVE
- **Evidence:** The tests protect valuable public behavior, including disconnect survival and
  abort. The disconnect test uses `time.sleep(0.2)`, and the module mixes auth, catalog,
  messaging, permissions, chat, merge, artifacts, briefing, and notes. Invalid frame shapes are
  handled in `ws_server.py`, but are mostly not exercised through the socket.
- **Recommended action:**
  - split by domain;
  - reuse `RpcSocket` and provider fixtures;
  - poll durable state with a bounded timeout;
  - add invalid JSON/non-object/missing-field/invalid-params/unknown-method continuation cases;
  - add duplicate IDs, out-of-order events, reconnect reconciliation, and concurrent-send tests.
- **Confidence:** High
- **Risk of change:** Low for file split; medium for concurrency tests because they may expose
  real defects.

### F10. Approval tests stop below the advertised workflow

- **Files**
  - `tests/unit/test_tool_approval.py`
  - `tests/integration/test_approval_gate.py`
  - `tests/integration/test_ws_rpc.py::test_approvals_list_rpc_returns_recovery_shape`
- **Production:** approval facade and gated executor in orchestrator runtime
- **Classification:** MOVE UP while retaining focused units
- **Evidence:** `test_approval_gate.py` calls a private executor wrapper directly. WS recovery
  checks only the response shape, not a parked run. No test starts a real chat, disconnects while
  pending, recovers the approval, decides once, and verifies exactly-once continuation.
- **Recommended action:** Keep the focused approve/reject/exact-authority tests. Add one public
  chat/RPC park → reconnect → list → decide → resume contract, plus duplicate/late-decision
  rejection.
- **Confidence:** High
- **Risk of change:** Low; additive.

### F11. Frontend direct-setter and dead-helper tests add negligible protection

- **Deletion candidates**
  - four unused-helper cases in `agentMobile.test.ts`;
  - `personaHomeStore.test.ts`;
  - `workspaceIntelStore.test.ts`;
  - ordinary-prose identity case in `wsClientNormalization.test.ts`.
- **Production**
  - `frontend/src/lib/agentMobile.ts`
  - `frontend/src/store/useAppStore.ts`
  - `frontend/src/lib/wsClient.ts`
- **Classification:** DELETE
- **Evidence:** Repository search found no production consumers for four tested mobile helpers.
  The two store tests call a direct setter and read the same values. The ordinary normalization
  case adds no meaningful edge beyond the structured-looking compatibility case.
- **Recommended action:** Delete only the tests now listed in Section 6 after separately deciding
  whether to remove dead production helpers. Cover store state through non-trivial invariants or
  consuming workflows.
- **Confidence:** High
- **Risk of change:** Low.

### F12. Responsive and overflow tests assert implementation strings

- **Tests**
  - `composerToolControls.render.test.tsx`
  - `missionControl.render.test.tsx::MissionControlPanel keeps long run content inside narrow cards`
  - several `mobileCopy.test.ts` and `agentMobile.test.ts` cases
- **Classification:** MOVE UP or MERGE
- **Evidence:** Exact assertions such as `class="relative lg:hidden"` and Tailwind
  `overflow-wrap` tokens can pass when the component is not actually usable at a viewport.
  Detached helper tests can pass if the helper is no longer wired.
- **Recommended action:** Keep pure truncation math as a small table. Verify availability,
  overflow, drawer/nav behavior, and focus at mobile/desktop widths in component/browser tests.
- **Confidence:** High
- **Risk of change:** Low if replacement tests land before removing CSS-string checks.

### F13. There is no deterministic critical-workflow frontend test

- **Current coverage:** store reducers, formatters, normalizers, and SSR markup only
- **Classification:** Missing coverage
- **Evidence:** No test clicks through a live or fake-transport UI. First-send runtime lock,
  archive/restore, approval actions, reconnect/bootstrap, cancel, tool activity, and error banners
  are not verified as user-visible flows.
- **Recommended action:** Add 4–6 deterministic browser/component integration journeys:
  1. create draft → first send → runtime locks;
  2. stream tool call/result → activity proof;
  3. approval approve/reject and reconnect;
  4. abort and terminal UI cleanup;
  5. archive/restore;
  6. mobile navigation/drawers.
- **Confidence:** High
- **Risk of change:** Additive; moderate maintenance if selectors and transport fixtures are not
  designed intentionally.

### F14. Market no-lookahead protection is partly tautological

- **Test:** `test_market_features.py::test_no_lookahead_slice_independence`
- **Production:** `src/copenet/core/market/features.py`
- **Classification:** DELETE and replace
- **Evidence:** Both calls pass an identical `frame.iloc[:k]`. Future bars are removed before
  `compute_features()` is called, so the test cannot detect lookahead in the caller that chooses
  the slice.
- **Recommended action:** Replace it with a replay/overlay boundary test that supplies a complete
  evidence set with later filings/bars and asserts only records with `availableAt <= as_of` reach
  the calculation.
- **Confidence:** High
- **Risk of change:** Low if replacement is added; medium if simply deleted.

### F15. Split adjustment is a load-bearing invariant without suite-wide enforcement

- **Production callers:** `market/backtester.py`, `replay.py`, `runtime.py`, `financials.py`,
  `data_sources.py`, `webull/orders.py`, and `webull/sync.py`
- **Existing test:** only
  `test_market_financials.py::test_valuation_price_inputs_preserve_split_adjusted_contract`
  directly asserts `auto_adjust=True`.
- **Classification:** Missing high-value contract
- **Evidence:** Several callers explicitly pass `True`; at least two rely on the default. If the
  default changes or a new caller passes/uses an unadjusted basis, the shared cache key carries no
  adjustment tag and can contaminate all consumers.
- **Recommended action:** Add an architectural contract that enumerates every `fetch_ohlcv()` call
  and requires explicit split adjustment, or replace the boolean API with one typed
  split-adjusted boundary.
- **Confidence:** High
- **Risk of change:** None; likely to catch future severe data regressions.

### F16. Scenario tests use misleading “real” language

- **Test:** `test_market_backtester.py::test_scenario_metadata_shock_details_are_real_for_each_preset`
- **Production:** `SCENARIOS` and `run_scenario()` in `market/backtester.py`
- **Classification:** KEEP, BUT IMPROVE
- **Evidence:** The test usefully protects public `shockDetails`, but scenarios are hand-authored
  magnitudes projected onto a synthetic cosine path, not real historical replays.
- **Recommended action:** Rename to
  `test_scenario_metadata_exposes_configured_synthetic_shock_details`. Keep the wire assertion.
- **Confidence:** High
- **Risk of change:** Negligible.

### F17. External-app isolation and attachment ownership are unproven

- **Production**
  - `src/copenet/host/app_api.py`
  - `src/copenet/core/apps/app_store.py`
  - `src/copenet/core/attachments/__init__.py`
- **Classification:** Missing critical security coverage
- **Evidence:** REST tests cover authentication and some app-scoped session/media behavior, but
  not two-app denial. `ChatAttachment` has no `app_id`; the authenticated GET route resolves a
  global attachment ID directly.
- **Recommended action:** Add two-app tests covering session visibility/history, media
  list/detail, cancellation, chat attachments, and attachment use in sends. If cross-app
  attachment retrieval succeeds, treat it as an IDOR defect rather than merely a missing test.
- **Confidence:** High
- **Risk of change:** Tests may expose a production authorization gap.

### F18. Media upload/transcribe and URL security are mostly uncovered

- **Production:** media upload/transcribe/download/import routes, media service/downloader, web
  ingest
- **Classification:** Missing critical security/failure coverage
- **Evidence:** Upload and transcribe build temp paths with the raw filename appended. Current
  tests do not cover traversal filenames, maximum sizes, unsupported types, cleanup on
  exceptions, cancellation/early-close, or SSRF/private-host/redirect behavior.
- **Recommended action:** Add boundary tests for hostile filenames, size/type rejection,
  cleanup, private/loopback/IPv6 URLs, redirects, and transcriber exceptions/cancellation.
- **Confidence:** High
- **Risk of change:** Tests may expose security and cleanup defects.

### F19. The multi-agent package is an isolated 20-test island

- **Test:** `tests/unit/test_multiagent_orchestrator.py`
- **Production:** `src/copenet/core/multiagent/`
- **Classification:** INVESTIGATE
- **Evidence:** Repository search found no caller outside the package exports and its tests. The
  tests themselves are coherent—selection, fallback, timeout, and bounded delegation—but their
  regression value depends on whether this is supported product code.
- **Recommended action:** Make an explicit product decision:
  - active/future committed path → retain core fallback tests, add one real caller contract, and
    merge route tables;
  - abandoned experiment → remove code and tests together in a separately reviewed change.
- **Confidence:** High that it is isolated; low on product intent.
- **Risk of change:** High if deleted without product confirmation.

### F20. Specialized subsystem tests are sparse but generally meaningful

- **Areas:** Fleet, Research Lab, Movies, NASA, Browser agent
- **Classification:** KEEP, with targeted improvements
- **Evidence:** These tests protect domain rules rather than framework mechanics:
  - Fleet reveal barrier and cursor semantics;
  - Research typed provenance and prose discard;
  - Movie ambiguity/rating/recommendation rules;
  - NASA video fallback and existing-wallpaper preservation;
  - Browser stop/risk/evidence state machine.
- **Recommended action:** Do not reduce these merely because the subsystem is small. Improve
  semantic fixtures and add missing public/failure boundaries described in Section 8.
- **Confidence:** High
- **Risk of change:** Medium to high if removed.

### F21. Test infrastructure is duplicated and one test mutates a real build directory

- **Evidence**
  - Fake/prompted/native provider classes recur across at least ten integration modules.
  - `_collect_events`, orchestrator builders, and tool contexts are repeatedly rebuilt.
  - `test_frontend_public_images_are_served_when_present` can create
    `frontend/dist/imgs/wallpaper.png` and does not own cleanup.
- **Classification:** KEEP, BUT IMPROVE
- **Recommended action:** Provide small domain-specific test builders—not one universal fake—for
  scripted provider turns, orchestrator construction, and event collection. Inject frontend dist
  as a temp path.
- **Confidence:** High
- **Risk of change:** Low, provided helpers remain explicit and do not hide scenario intent.

### F22. Some names claim stronger levels or guarantees than assertions prove

- **Examples**
  - `test_multiturn_responses_e2e.py` is in-process integration.
  - approval “integration” bypasses public chat/RPC.
  - invalid meme request combines two invalid fields and checks only 422.
  - scenario “real” shocks are synthetic.
- **Classification:** KEEP, BUT IMPROVE
- **Recommended action:** Use names that identify the actual boundary and one observable
  guarantee. For invalid requests, parameterize fields and assert validation locations.
- **Confidence:** High
- **Risk of change:** Negligible; clearer names improve suite trust.

## 5. Consolidation candidates

The goal is fewer places to understand a contract, not fewer input cases.

| Cluster | Before | Proposed after | Why confidence is retained |
|---|---:|---:|---|
| Session stale-run recovery | 2 tests | 1 state-transition test | One test can assert pre-block, recovery tuple, cleared marker, future send, and idempotent second sweep |
| Session Access transitions | 3 tests plus broad reconcile test | 1 parameter table plus broad persistence test | All stored/requested/expected rows remain |
| Responses item serialization/replay precedence | 7 tests | 3 table-driven contracts | Exact wire shapes and precedence cases remain |
| Shell destructive/read-only examples | 6 tests | 1 named security matrix | Every command, Access mode, and decision remains visible |
| Prompted harness happy path | 2 harness tests plus 1 orchestrator test | 1 canonical harness contract plus 1 orchestrator contract | Removes same-boundary duplication but preserves higher boundary |
| Retired tool identifiers | 3 negatives | 1 parameterized absent-ID manifest contract | Canonical owner remains; exact duplicate disappears |
| OpenAI Responses SSE variants | 6 parser tests | 2 tests with event fixture tables | Same parser boundary, easier addition of new event variants |
| Frontend diff/tokenizer/file preview | 15 micro-tests | about 5 representative/table tests | Round-trip and edge inputs remain, setup shrinks |
| Frontend mobile copy/helper examples | 12 cases | 2–4 tables plus browser assertions | Pure truncation remains below; responsive behavior moves to the UI layer |
| Market scalar metric edges | 6 tests | about 3 metric tables | Known-series and zero/short cases remain |
| Market transaction-tone variants | 4 tests | 1 scenario table | Keeps gift/mechanical/value/share divergence rules |
| Runtime probe classifications | 7+ large payload tests | named fixture table plus report tests | Preserves classification corpus without copied payload scaffolding |
| REST gateway-token variants | 2 endpoint-specific auth tests | 1 authenticated-route table | Endpoint behavior tests remain separately |

### Proposed structural before and after

Before:

```text
tests/
  integration/
    test_phase_0_quickwins.py
    test_phase_minus_1_baseline.py
    test_ws_rpc.py                 # 1,231 lines, many domains
    test_tool_loop.py
    test_tool_prompt_matrix.py
  unit/
    test_build_chat_messages.py    # duplicates context-budget cases
    test_workspace_intel_tools.py  # duplicate manifest negative
```

After:

```text
tests/
  contracts/
    providers/
      test_provider_catalog_contract.py
      test_responses_event_contract.py
    rpc/
      test_ws_auth_catalog.py
      test_ws_chat_lifecycle.py
      test_ws_approvals.py
      test_ws_messaging.py
    tools/
      test_manifest_contract.py
      test_prompted_protocol_contract.py
  integration/
    test_orchestrator_lifecycle.py
    test_replay_across_turns.py
    test_approval_reconnect.py
  unit/
    harness/
      test_context_window.py
      test_response_items.py
    tools/
      test_files.py
      test_shell_policy_matrix.py
```

This is a conceptual target; it does not require an immediate directory rewrite.

## 6. High-confidence deletion candidates

Only high-confidence candidates are listed here. No deletion has been performed.

### D1. Exact removed-tool registry duplicate

- Delete:
  `tests/unit/test_workspace_intel_tools.py::test_tool_registry_does_not_expose_removed_experimental_tools`
- Keep:
  `tests/unit/test_tool_contracts.py::test_tool_registry_does_not_expose_removed_experimental_tools`
- Production behavior: `ToolRegistry.list_tools()` excludes retired identifiers.
- Evidence: same registry call and same absent IDs; the kept test is in the contract-owning file
  and also asserts a current manifest member.
- Risk: Negligible.

### D2. Same-session idempotency duplicate

- Delete:
  `tests/integration/test_phase_minus_1_baseline.py::test_idempotency_cache_still_dedupes_within_same_session`
- Keep:
  `tests/integration/test_orchestrator.py::test_idempotency_key_returns_cached_status`
- Production behavior: same session and idempotency key executes once, then returns cached with no
  new events.
- Evidence: same boundary, request pattern, statuses, and event expectation. The unique
  cross-session isolation regression remains in the phase-minus file until moved.
- Risk: Negligible.

### D3. Duplicate token-estimation unit

- Delete:
  `tests/unit/test_build_chat_messages.py::test_estimate_input_tokens_is_roughly_char_quarter`
- Keep:
  `tests/unit/test_context_budget.py::test_text_estimate_is_still_roughly_char_quarter`
- Production behavior: the same context-window estimator returns roughly one token per four
  characters.
- Evidence: same imported implementation and 400 → 100 assertion.
- Risk: None.

### D4. Duplicate oversized-current-turn unit

- Delete:
  `tests/unit/test_build_chat_messages.py::test_token_budget_always_keeps_oversized_current_turn`
- Keep:
  `tests/unit/test_context_budget.py::test_oversized_current_turn_is_always_kept`
- Production behavior: context trimming never drops the current user turn even when oversized.
- Evidence: same production function and same observable result; the context-budget owner test is
  stronger.
- Risk: None.

### D5. Tautological feature no-lookahead case

- Delete after replacement:
  `tests/unit/test_market_features.py::test_no_lookahead_slice_independence`
- Production behavior claimed: point-in-time features do not consume future data.
- Evidence: both inputs are identical slices, so the claimed future-data mutation cannot reach
  the function.
- Replacement: caller-level replay/financial-availability test.
- Risk: Low after replacement; medium without it.

### D6. Four dead `agentMobile` helper tests

- Delete:
  - `conversation debug helper text is hidden on mobile`
  - `working set section labels compact on mobile`
  - `working set uses compact three-up grid on mobile`
  - `working set starts collapsed on mobile and expanded on desktop`
- Production behavior: values returned by four helpers with no production consumers.
- Evidence: repository-wide search found use only in the helper module and its tests.
- Risk: Low. Review dead production helpers separately.

### D7. Two direct Zustand setter round trips

- Delete:
  - `src/copenet/host/frontend/tests/personaHomeStore.test.ts`
  - `src/copenet/host/frontend/tests/workspaceIntelStore.test.ts`
- Production behavior: setters assign provided objects.
- Evidence: tests contain no normalization, isolation, persistence, merge, or consuming behavior;
  they read back the same values.
- Risk: Low.

### D8. Ordinary-prose identity normalization

- Delete:
  `wsClientNormalization.test.ts::normalizeAssistantDisplayText leaves ordinary assistant prose alone`
- Keep/merge:
  the structured-looking legacy-content case.
- Production behavior: display text remains unchanged.
- Evidence: the structured-looking case is the realistic regression boundary; ordinary literal
  identity adds negligible unique signal.
- Risk: Low.

## 7. Tests that need improvement

### Stronger assertions

- Require exact `INVALID_REQUEST` in the RPC bad-param test.
- Extend orchestrator abort tests to assert:
  - durable terminal status;
  - cleared `in_flight_run_id`;
  - no post-abort tool execution;
  - successful next send.
- For API invalid-request tests, assert error locations/fields rather than only 422.
- For REST/WS shape tests, assert ownership, ordering, and terminal invariants, not only `ok`.

### Less mocking / better boundaries

- Keep provider parsers mocked at network/process I/O, but add orchestrator failure tests using
  throwing/partial fake providers.
- Move approval workflow protection to the public chat/RPC boundary.
- Move responsive CSS behavior to component/browser tests.
- Add one real Research workflow boundary instead of only typed builder units.

### Better names

- Rename fake-provider “E2E” tests as orchestrator/Responses integrations.
- Rename synthetic Market scenario test.
- Replace phase names with current domain behavior.
- Ensure test names match exact assertions, especially invalid-request tests.

### Smaller fixtures

- Share scripted provider and event-collection builders by boundary.
- Replace raw XLSX XML in Movie tests with a focused workbook fixture/builder.
- Replace large repeated runtime-probe dictionaries with named fixture records.
- Use record builders for RunStore and WS setup while keeping important fields explicit.

### More deterministic setup

- Replace fixed sleeps with bounded polling on durable/terminal state.
- Inject frontend dist and service roots through temp directories.
- Avoid tests that leave ignored files in product build directories.
- Remove exact duplicate model loading count from transcriber progress; assert eventual release.

### Reduced implementation coupling

- Parse plist output semantically.
- Do not assert exact Tailwind strings for layout behavior.
- Do not pin exact prompt prose unless a prompt version/text is the product contract.
- Use shared provider catalog invariants instead of exact static model lists where appropriate.
- Keep exact Responses wire shapes: those are external contract assertions, not accidental
  implementation detail.

## 8. Missing high-value tests, ranked

### Critical

1. **Provider failure lifecycle**
   - raise before output, after partial delta, and after tool execution;
   - assert error event, failed run record, transcript policy, trace terminal event, lock cleanup,
     and successful next send.

2. **Concurrent session admission and idempotency**
   - same session/same key concurrently;
   - same session/different keys;
   - different sessions/same key;
   - prove exactly-once provider execution and correct in-flight behavior.

3. **Persistence concurrency and crash recovery**
   - two `SessionStore` instances/processes;
   - JSONL append integrity/order;
   - truncated final record;
   - interrupted atomic replace;
   - old schemas with missing fields.

4. **Full approval/reconnect workflow**
   - real chat parks;
   - socket disconnects;
   - pending approval is recovered;
   - decision resumes once;
   - duplicate/late decisions are rejected;
   - abort while pending clears state.

5. **External-app isolation / IDOR**
   - two apps cannot cross-read sessions, media, attachments, histories, or cancel each other's
     runs.

6. **File write/edit path security**
   - `../`, absolute outside path, symlink target, symlink parent, target replacement after digest,
     and workspace-root changes.

7. **Market split-adjustment architectural contract**
   - every `fetch_ohlcv()` caller is explicitly split-adjusted;
   - new callers fail the contract if basis is omitted/false.

8. **Market point-in-time financial alignment**
   - price overlay/backtest uses `availableAt`/filing date;
   - later filing cannot affect an earlier as-of result;
   - accession/provenance survives filtering.

### High

9. **Malformed WebSocket frames and continued usability**
   - invalid JSON, non-object, missing ID/method, invalid params, unknown method, oversized frame,
     duplicate IDs, and a valid request afterward.

10. **Cancellation races**
    - during provider streaming, slow tool execution, parallel Responses calls, and approval wait;
    - exactly one terminal event and no later side effect.

11. **Prompt-injection integration**
    - hostile web/tool output containing CopeNet delimiters passes through the actual prompted
      follow-up loop and cannot create a call.

12. **Attachment replay fidelity**
    - past image attachment is re-inlined on a later turn;
    - trimming does not orphan its user turn;
    - missing/corrupt attachment produces an honest error.

13. **Frontend critical workflows**
    - the six journeys listed in F13.

14. **Media upload/transcribe and URL boundary security**
    - traversal, size/type, cleanup, SSRF/private hosts, redirects, exception/cancellation.

15. **Provider malformed/abort contracts**
    - Claude nonzero/malformed JSONL;
    - LM Studio invalid catalog/non-JSON/status;
    - OpenAI abort and fragmented function-call SSE.

### Medium

16. **Specialized-store compatibility/corruption**
    - Market, Movie, NASA, Media, Research.

17. **Browser agent real-session contract**
    - scheme/domain restriction, timeout, stale element recovery, trace persistence, untrusted
      page content.

18. **Movie/NASA vendor failures**
    - malformed workbook and missing columns;
    - TMDB timeout/rate-limit/partial data;
    - NASA HTTP/error payload and invalid cache download.

19. **Property/fuzz tests**
    - shell tokenization/classification across quoting, substitutions, redirects, Unicode
      whitespace, and chains;
    - URL normalization across IPv6, userinfo, encoded secrets, redirects, and host casing;
    - transcript tool-call/result pairing and context trimming invariants.

## 9. Proposed target test architecture

### Unit tests

Use for:

- pure Market calculations and state classifications;
- parsers and wire-item builders;
- session transition rules;
- command/URL/path policy decisions;
- store normalization of one record;
- frontend reducers and non-trivial formatters.

Do not use for:

- direct getters/setters with no custom behavior;
- framework guarantees;
- CSS availability or user workflow claims;
- large mocked flows where all meaningful logic is replaced.

### Integration tests

Use real temp storage and the real orchestrator/harness for:

- send/finalize/fail/abort lifecycle;
- transcript/run/artifact persistence;
- replay across turns;
- approval parking and continuation;
- Fleet/lane behavior;
- provider adapters with only network/process I/O faked.

Keep these deterministic. A fake provider is appropriate when it scripts the true provider
contract and production orchestration remains real.

### Contract tests

Create explicit shared contracts for:

- provider metadata/catalog/error semantics;
- Responses and chat-completion tool call/result shapes;
- REST and WS common session/message/run fields;
- tool manifest and Access visibility;
- RPC error normalization;
- split-adjusted Market data access;
- persistence backward compatibility.

Contract tests should assert stable external semantics, not incidental implementation order.

### End-to-end tests

Maintain a very small deterministic browser suite for operator-critical workflows. It should use
a controlled backend/fake provider, not live vendor quota. Four to six journeys are enough if
they cover the full story.

Live provider probes and real vendor/browser probes should remain explicitly opt-in
infrastructure checks outside the default 28-second suite.

### Security tests

Treat security as a first-class suite, not scattered examples:

- tool allowlist and Access matrix;
- shell/path/URL adversarial tables;
- Barricade/prompt-injection flow;
- cross-app and cross-session isolation;
- approval authority and replay resistance;
- token/bind rules.

Security duplication is justified when it protects parser, policy, execution, and public
transport boundaries separately.

### Regression tests

Every regression test should state:

- the defect or invariant;
- the nearest production boundary;
- why a stronger overlapping test does or does not subsume it.

Once architecture changes, move the test to the new owner and update the language. Do not keep a
permanent phase graveyard.

### Property-based and fuzz tests

Use selectively for high-dimensional input surfaces:

- shell classification;
- URL/host normalization;
- path containment and symlinks;
- transcript part pairing;
- context trimming;
- persisted-record optional fields.

Do not replace clear deterministic examples with broad generators. Keep a small named regression
corpus beside properties.

## 10. Prioritized action plan

### Phase 1 — Safe cleanup

Actions:

- apply the 12 high-confidence deletion decisions;
- merge exact manifest/idempotency/context-budget duplicates;
- table-drive session transitions, shell command examples, Responses micro-cases, and frontend
  diff/tokenizer/preview helpers;
- rename misleading tests;
- move phase-era direct units to their owner modules;
- isolate frontend dist writes;
- replace the WS fixed sleep.

Estimated impact:

- **Affected:** 55–75 current cases
- **Likely net reduction:** 35–55 cases
- **Maintenance reduction:** 8–12% fewer repeated setups/assertion sites in affected areas
- **Regression risk:** Low, provided MOVE/replace items are sequenced before removal
- **Confidence improvement:** Small to moderate; primarily trust and diagnosis

### Phase 2 — Structural improvements

Actions:

- split the WS suite by domain;
- add shared, explicit scripted-provider/orchestrator/RPC builders;
- create provider, tool-manifest, REST/WS field, and Market data-access contract suites;
- move approval verification to a public workflow;
- replace CSS-string checks with component/browser behavior;
- decide the status of `core.multiagent`;
- separate deterministic product tests from live/probe infrastructure.

Estimated impact:

- **Affected:** 90–130 current cases
- **Likely net reduction:** 10–25 cases; most value comes from structure, not count
- **Maintenance reduction:** 15–25% in harness/RPC/provider/frontend fixture code
- **Regression risk:** Medium because boundaries and fixtures move
- **Confidence improvement:** Moderate

### Phase 3 — Coverage upgrades

Actions:

- add provider failure, concurrent admission, persistence concurrency, approval reconnect, and
  cancellation-race tests;
- add cross-app isolation and media/path/URL security tests;
- add split-adjustment and `availableAt` architectural contracts;
- add attachment replay and old-schema compatibility;
- add 4–6 deterministic frontend E2E journeys;
- add targeted property/fuzz tests.

Estimated impact:

- **Added:** roughly 25–45 carefully selected cases, some parameterized
- **Maintenance reduction:** None directly; shared contracts prevent future duplication
- **Regression risk:** Low to production, medium likelihood of exposing real defects
- **Confidence improvement:** High

The expected stable result is not necessarily a much smaller suite. A reasonable first pass
could consolidate or remove **roughly 50–70 current cases** without materially reducing
confidence, then add **25–45 higher-value boundary/failure cases**. Net count is secondary.

## 11. Concise verdict

1. **Intentionally comprehensive or merely accumulating?**
   Both. The core security, session, replay, Market, and Fleet coverage is intentionally
   comprehensive. Phase-era harness tests, frontend helper/setter tests, static catalogs, probe
   fixtures, and exact implementation strings show clear accumulation.

2. **Highest-value categories:**
   Tool/security policy, session identity and persistence invariants, harness/tool replay,
   Market accounting/state logic, Fleet ordering, and provider response parsing.

3. **Most maintenance noise:**
   Phase-owned characterization files, repeated fake providers, microscopic serialization and
   scalar examples, direct Zustand setters, exact CSS/copy/prompt/catalog/argv assertions, and
   large mixed-domain WS fixtures.

4. **How many can likely be consolidated or removed?**
   Approximately **50–70 of 804 current cases**, with only 12 recommended for immediate
   high-confidence deletion. Most of the remainder should be table-driven or merged, not have
   their input cases discarded.

5. **How to prevent renewed accumulation:**
   Require each new test to name its architectural boundary and plausible mutation, identify
   nearby overlapping coverage, prefer named contract tables for input variants, move regression
   tests when architecture moves, review direct-setter/exact-style tests skeptically, and require
   critical workflows to have one public-boundary test rather than dozens of detached units.
