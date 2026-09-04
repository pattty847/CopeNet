# Chart Agent demo implementation plan

Status: initial demo implemented and verified. Updated 2026-09-04.
See [DEMO.md](DEMO.md) for the implementation record, measured limits and remaining work.
The milestones below retain the design rationale and acceptance scope.
Architecture decisions: [ARCHITECTURE.md](ARCHITECTURE.md).
Product brief: [VISION.md](VISION.md).

## Demo scope and acceptance story

Build this inside the existing ticker workspace, using real normal sessions and existing
market data. The complete demo is:

1. Open a ticker; configure an indicator and pan/zoom away from the default range.
2. Open the companion; its context shows the actual displayed symbol, interval, dates,
   selected region, plots, freshness, and supported panel state.
3. Ask, “Explain this region and draw two levels you can justify.”
4. The model reads exact captured data, creates editable chart objects, and links its
   explanation to their evidence. If the data does not justify two levels, it says so.
5. Ask it to revise a named object. Manually adjust another object, then prove the model
   cannot overwrite that operator-controlled object with a stale request.
6. Undo a batch; reload and verify the remaining drawings/conversation/evidence survive.
7. Change symbol and timeframe, send again, and verify automatic current-state capture.
   An old in-flight result never draws on the new symbol.
8. Switch Quick/Balanced/Deep and inspect the differences in context/range coverage and
   tool budget. Each mode can answer a question about one selected exact candle.

The demo includes current quote awareness on user invocation. It excludes proactive live
commentary, actual exchange/order-book ingestion, vision, arbitrary generated indicators,
trade execution, and messaging. These remain separate follow-on slices. Saved ticker
Synthesis remains a distinct one-shot read, clearly labeled; companion chat uses `chat.send`.

## Scope coverage

| Surface/capability | Demo contract |
| --- | --- |
| Candles | Exact loaded D/W/M data; viewport and selection; completion/basis metadata |
| Indicators | Read active configuration and exact plotted outputs; manual picker continues working |
| Comparisons and financial overlays | Read displayed values/configuration and units; do not draw price objects on rebased axes |
| Research dock | Typed state/data for visible Overview, Fundamentals, SEC & Events, Synthesis |
| Live quote | Same subscription/state as displayed quote, captured with its own timestamp |
| Drawings | Levels, zones, two-anchor trendlines, labels; manual and agent actions; select/edit/hide/undo |
| Agent | Normal sessions, model/Access rules, stop, history, tool inspection, evidence references |
| Detail | Three functional evidence budgets; stored source detail preserved |
| Market landing panels | Later adapters; do not claim full landing-panel awareness in the demo |
| Account context | Excluded by default; explicit inclusion must cover all captured panel resources |

## Milestone 1 — Contracts and shared state

First internal checkpoint: implement the smallest dependent portions of milestones 1–3
before expanding their breadth: one candle resource and viewport, atomic capture, a minimal
document with one horizontal level, explicit-session send, the context/read/apply tool path,
and its render receipt. Exercise it through the normal provider loop in an isolated synthetic
workspace. It is finished product code in the modules below, not a disposable prototype.
Do this before all-panel mapping, four-shape manual tooling, cleanup UI, or companion polish.
If context or drawing delivery fails, resolve it before expanding. Then complete milestones
1–3 in the order below, followed by UX and the final demo gate.

Implement the typed contracts and extract view derivation before adding chat UI.

- Create the focused backend/frontend module boundaries in the architecture.
- Define InstrumentRef, resource descriptors, MarketViewState/Capture, observation,
  document/object/operation/receipt, and MarketTurnContext schemas. Keep one canonical
  field vocabulary across RPC, Python, TS, tools, and artifacts.
- Add synthetic contract fixtures shared by backend validation and frontend serialization.
  Version stored contracts from the first release; reject unknown versions explicitly.
- Extract `useTickerViewModel` and chart viewport adapter. Both rendering and capture
  consume the same data. Derive exact selected row IDs from the actual chart time axis.
- Add typed panel contributions for the supported dock. Include filters, frequency,
  visibility and the panel's real alignment (financial explorer versus price overlay).
- Extract live quote subscription into a narrowly subscribed view store and provide the
  capture getter. Preserve the existing single connection and visibility lease behavior.

Proof: deterministic tests change ticker, viewport, indicator config, research story,
financial frequency and live quote; captured values equal the rendered model for that
revision. No historical indicator recomputation on quote-only updates. Existing loading,
symbol transitions, comparison behavior and chart interactions remain intact.

Commit boundary: `refactor(market): expose shared ticker view state` plus its contracts/tests.

## Milestone 2 — Durable observations and manual chart documents

Implement a useful chart subsystem before connecting a model.

- Add the indexed SQLite store, atomic capture, resource hashes, bounded retention/capacity,
  exact query pagination, document revision CAS, operation dedupe and compensating undo.
  Freeze the displayed drawing records along with other observation resources.
- Add thin chart RPC handlers, client methods and document-change events. Add pre-parse
  transport limits without breaking valid existing attachment/chat paths.
- Add the four drawing shapes using a series primitive and coordinate adapter; manual
  create/select/edit/delete/hide uses the same document operations planned for agent tools.
- Add object provenance display, batch undo and explicit render receipts. Restore document
  state after reconnect/reload; filter every event by its document/view identity.
- Capture underlying view data through `market.chart.capture`; inspect exact snapshot
  resources through a development test harness, without making a paid model call.

Proof: use real temp SQLite stores, crash/transaction failure injection, concurrent writers,
retry/different-payload dedupe, undo after unrelated and conflicting edits, capacity limits,
expired orphan captures, and references beyond 500 artifacts. In a visible browser, verify
pan, zoom, log scale, resizing, DPR and comparison/interval applicability. A hidden browser
result is not evidence of successful chart painting.

Commit boundaries: `feat(market): persist chart observations and documents`, then
`feat(market): add editable chart drawing layers` with focused verification for each.

## Milestone 3 — Ordinary agent sessions with chart tools

- Extract explicit-session sending from `wsChatActions`; keep the current Agents UI as a
  caller. Add stable request IDs and ensure optimistic message/error routing remains tied
  to the captured session, even if the user navigates during an await.
- Create Market-local draft state and durable workspace → normal session linkage. Reuse
  transcript/composer primitives without changing the globally selected Agents session.
- Add validated `marketContext` to `chat.send`/ChatSendRequest. Validate and bind chart
  context before reporting the chart run accepted; preserve the existing in-flight lock.
  Same idempotency key binds exactly one capture and run, including interrupted retries.
- Persist chart admission fingerprint/state and reconcile with existing run/session/transcript
  stores after restart. Never automatically reexecute an uncertain admitted request. Stable
  first-send session keys also prevent duplicate Market sessions after a lost create response.
- Inject MarketTurnContext into message construction/tool execution; persist its observation
  reference in run/transcript metadata and a compact artifact manifest. Handle native
  provider resume and history replay explicitly rather than relying on the UI transcript.
- Extract/generalize approval execution so chart writes show their exact batch rather than
  a shell-command prompt. Preserve Barricade's descriptor-based write gating and propagate
  captured external-prose trust. Verify approval never bypasses scope/revision validation.
- Implement the five exact chart tools. Add chart-write category/scoped policy and enforce
  the per-turn tool intersection at registry execution, not only prompt construction.
- Feed model results through existing tool previews/inspector. Ship any new drawing receipt
  preview type with its renderer and preview renderability tests.

Proof: orchestrator tests with deterministic fake providers execute inspect → apply → read
document → revise → undo. Direct execution attempts without bindings, against another
document, against a protected object, or through an unapproved tool fail. Normal sessions
without marketContext preserve their existing behavior. Cross-provider/profile/workspace
locks remain unchanged; same-provider model and Access switches remain explicit and audited.
Test resumed Claude CLI input as well as structured provider messages. Exercise existing
session taint, exact-batch approval/rejection/timeout/abort, and account exclusion with prior
conversation context; never claim an exclusion toggle removes data already sent.
Crash at capture, admission, transcript append, provider dispatch and document commit boundaries;
retries must report the known/interrupted state without duplicating dispatch or drawing batches.
Verify historical observation reads respect current resource inclusion scope.

Commit boundary: `feat(agents): support scoped chart context and actions`.

## Milestone 4 — Companion UX and evidence depth

- Add the resizable right companion beside the chart, retaining the research dock below it.
  Use existing market typography/tokens and conversation components; avoid another app shell.
- Include context header, Quick/Balanced/Deep slider, chart read/annotate control, account
  inclusion state, model selector, message/stop controls, and context-used disclosure.
  Account inclusion describes new context; a reused session retains its earlier knowledge.
- Implement selection chips and links between messages, drawings, and evidence inspector.
  Show target symbol/observation attribution on turns and saved/pending/rendered drawing status.
- Capture current state automatically on every send. Freeze one submission through retries;
  changing a view while capture is in flight does not replace its payload.
- Budget initial context and tool queries against remaining provider context. Preserve the
  complete stored observation, label omissions, and keep exact selected values available.
- Define initial loading, capture failure, stale data, disconnected host, archived session,
  busy session, missing capability, conflict, render failure, and exhausted budget states.
- Narrow screens use chart/chat switching with preserved context/selection and accessible
  controls; desktop keyboard resizing, focus restoration and Escape are verified.

Proof: UI → real RPC → isolated stores with synthetic data, followed by one deliberate real
provider run against that synthetic fixture. Verify actual streamed tool calls and drawing
receipts, not a prerecorded assistant answer. Verify another tool-capable provider with
deterministic adapters; label live providers unverified until separately exercised.

Commit boundary: `feat(market): add chart agent companion and detail controls`.

## Milestone 5 — Demo gate and documentation

Run the full acceptance story, regressions, and measurements. Complete every critical row
below before calling the demo complete. Fix failures at their owner boundary rather than
silently reducing source detail or disabling a scenario.

| Check | Pass condition |
| --- | --- |
| Shared data | Selected bars, plotted indicator values and panel values match captured resources |
| Independent revisions | Quote updates do not conflict with edits; viewport changes do not rewrite a run's observation |
| Invocation | Newly displayed settings/data enter the next turn without manual attachment |
| Session isolation | Market and Agents drafts/sends/errors never target one another accidentally |
| Draw grounding | Shape anchors and evidence references resolve to the run's observation |
| Control | Requested edit works; operator-controlled object is protected; batch undo is safe |
| Delivery | Stored versus rendered is accurate under navigation, hidden tabs, disconnect and renderer failure |
| Persistence | Conversation, drawings and exact evidence survive reload/process restart |
| Interrupted retry | Durable admission status prevents automatic redispatch; existing batches remain inspectable |
| Replay | Earlier turns retain observation attribution after model switch/resume/compaction |
| Bounded context | Detail changes inspected evidence; context and query limits are explicit; raw artifact isn't blindly replayed |
| Market integrity | Split basis, partial candles, missing values and filing-date semantics remain correct |
| Provider fit | Existing harness carries actual chart calls; unsupported tool/vision capabilities are honest |
| Approval | Existing Barricade rules hold; drawing batches are shown accurately; rejection/abort cannot execute them |
| Privacy | Scope exclusion enforced across captures/queries/tools; fixtures/screenshots are synthetic |

Use `npm run lint`, `npm run build`, relevant frontend tests, Python syntax smoke, and
targeted backend tests. Build precedes tests requiring the generated indicator evaluator.
Add `scripts/verify_chart_agent.py` following existing Market verification scripts; use
isolated stores and controlled data acquisition. Follow the repository's browser preference
and document any genuine visible-render validation that still requires operator execution.

Initial performance targets are budgets to measure, not claims: with 10,000 candles,
six plotted indicator instances and 100 drawings, no capture-related main-thread task over
50 ms; local capture/commit p95 below 500 ms excluding model latency; quote-only updates
do not trigger historical chart computation. Measure on the target host and record results.
If serialization exceeds the budget, move pure serialization/hash work off the render thread
and reuse immutable resources; do not discard detail to pass. Avoid O(history) work per tick.

Evaluate selected-candle precision, an old event outside the summary window, a null/gap,
and a pattern missed by the initial summary at each detail. Record correctness, ranges
inspected, tool count, estimated/reported usage, and latency. No invented token savings.

Capture fresh sanitized screenshots under `docs/imgs/`, refresh the matching README section,
update initiative status with what actually works, and commit/push coherent units following
privacy/syntax checks. No temporary probes or real account data in commits.

## Follow-on work after the demo

1. Indicator and financial-plot actions, with canonical config/state ownership; derived
   calculations use the registry/headless evaluator, never a second formula implementation.
2. Market landing-panel adapters and explicit current-view capture during a running turn.
3. Event-triggered live commentary, prioritization, cadence/budget controls, and explicit
   handoff to existing persisted alerts. User input takes priority; no per-tick LLM loop.
4. Exchange-specific crypto ingestion and canonical order-book reducer. Add sequence/gap,
   reconnect, precision and depth-coverage tests before exposing order-book analysis.
5. Retained depth/trade windows, liquidity history/heatmaps, and reproducible replay with
   deliberate storage policy. Optional vision complements these structured resources.

## Decisions resolved for the build

- The demo is a production-shaped slice of CopeNet; it does not create a throwaway chat server.
- Drawing documents belong to the market workspace/instrument; observations belong to turns.
- Exact render inputs are stored as browser-captured evidence; no silent refetch on capture.
- Bounded annotation access is separate from shell/filesystem Full Access.
- The initial agent can mutate its own layer; human-controlled objects require separate scope.
- First demo uses existing equity/ETF data and user-triggered quote snapshots. No crypto vendor
  is selected, and no exchange credentials/subscriptions are needed to begin.
- API/resource identity includes source/time/basis now; order-book infrastructure is built when
  a feed is chosen. This avoids making D/W/M US-equity assumptions permanent in the new domain.

The initial implementation is available. Browser long-task profiling and provider-specific
latency/quality comparisons remain follow-on measurements; they must not weaken the
shared-state or exact-evidence contract.
