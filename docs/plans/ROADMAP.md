# CopeNet Roadmap / Backlog

This is the canonical running backlog. Git history records what shipped; this file
records unfinished work, deferred decisions, and ideas worth circling back to.

Keep implementation detail in code and current architecture docs. Keep a separate
feature plan only while that feature is actively being designed or built. When the
work ships or is abandoned, move any remaining items here and remove the old plan.

## Active Work

- **Fleet Rooms:** durable multi-provider rooms and independent-first response lanes.
  Current contract: [FLEET_ROOMS.md](FLEET_ROOMS.md).
- **Research Lab:** evidence-first company research, benchmark comparison, and durable
  dossiers. Current design: [RESEARCH_LAB_V1.md](RESEARCH_LAB_V1.md).
- **Market Monitor:** slow-timeframe monitoring, evidence-backed reads, and forward
  evaluation. Current direction:
  [MARKET_MONITOR.md](MARKET_MONITOR.md),
  [MARKET_INSIGHT_ENGINE.md](MARKET_INSIGHT_ENGINE.md), and
  [MARKET_DESIGN_REVIEW.md](MARKET_DESIGN_REVIEW.md).

## Sessions And Runtime

- Support an explicit cross-provider switch within an existing session. Rebuild context
  from the append-only transcript for the new provider and keep every run stamped with
  the provider/model actually used.
- Move the run-lock setup fully inside the lifecycle cleanup boundary so a setup failure
  cannot strand a session until process-start recovery.
- Make the in-flight check-and-set safe across multiple CopeNet processes sharing the
  same session index.
- Guarantee one terminal run record. A failure while emitting the final event must not
  append a contradictory second record under the same `run_id`.
- Persist an assistant-visible failure/terminal transcript entry when a durable user turn
  fails, so reload never leaves an unexplained one-sided conversation.
- Add token-budget-aware history compaction instead of relying on a silent fixed message
  cap.
- Design conversation branching/forking so a user can explore an alternative without
  rewriting the original transcript.
- Reconcile provider-native session ids with replayed transcript context. Never silently
  claim continuity when a provider actually started fresh.
- Verify whether same-turn tool calls execute concurrently. If they do, serialize
  conflicting operations against the same path while preserving safe parallel reads.

## Fleet And Multi-Agent Coordination

- Decide which collaboration modes are product-visible:
  - fallback after a provider failure;
  - independent answers followed by reveal;
  - sequential draft/review;
  - deliberate debate or synthesis.
- Keep provider selection explicit and inspectable. Surface fallback rather than silently
  changing providers.
- Add role mapping only for providers that really exist. Revisit a Gemini/breadth lane
  when a supported provider adapter is available.
- Add coordinator-level retry, abort, and partial-failure behavior without weakening
  one-run-per-session or append-only transcript guarantees.
- Decide how evidence receipts move between lanes after the independent-first barrier.

## Personas, Memory, And AI-Built Workspaces

- Add project-scoped personas under `<project>/.copenet/personas`, with project-before-
  global discovery and an explicit scope choice during creation.
- Reconcile the Persona picker with per-model overrides so the UI always shows which
  persona will actually run.
- Add the Persona picker to the in-session runtime panel.
- Add project-scoped memory under `<workspace>/.copenet/memory.json`; keep draft proposals
  excluded from prompt injection until the operator approves them.
- Define a declarative workspace manifest that can select:
  - navigation and layout;
  - tools and data sources;
  - default persona/profile;
  - scoped memory;
  - scheduled jobs or workflows.
- Make AI-built workspaces a draft → validate → preview → approve flow. The model authors
  a manifest; the runtime validates registered capabilities and materializes only what the
  operator approves. Preserve provenance for every generated manifest.
- Start with domain templates such as OSINT and cybersecurity rather than a general
  drag-and-drop builder.

## Approvals, Messaging, And Remote Continuity

- Finish modified approvals end to end. The UI can represent a modified payload, but the
  live tool-approval backend currently treats non-approved outcomes as rejection.
- Ensure a paused approval survives reload/reconnect and cannot execute twice after an
  approve/abort race. Define explicit process-restart semantics; a persisted approval
  record alone cannot resume a parked coroutine.
- Replace or deliberately configure the five-minute approval timeout and preserve a
  durable approval audit trail.
- Replace any remaining mocked outbound-message behavior with real transport receipts.
- Complete outbound Telegram delivery and live credential verification; preserve
  destination discovery, session routing, and source-channel provenance.
- Add an honest token-entry/recovery flow when the browser receives `auth_failed`.
- Add `providerAuth.updated` pushes and distinguish expired-but-refreshable credentials
  from a real login failure.
- Show a paused-run timeline in the inspector: started → tool activity → awaiting operator.

## Market Monitor And Research

- Replace hand-typed synthetic scenario curves with real historical-window replay.
- Decide whether the historical store should move to DuckDB for point-in-time research.
- Expand replay descriptors and model evaluation only when the live and historical paths
  use the same feature computation.
- Keep ticker packets factual. Let the model form bull/bear cases instead of persisting
  backend-authored conclusions.
- Continue Research Lab implementation with immutable evidence snapshots, explicit claim
  types, benchmark controls, honest missing-data states, and resumable stage history.
- Add Telegram delivery for material alerts or morning briefs only after messaging has a
  real outbound transport and receipt path.
- Treat portfolio advisory/Copilot behavior as a separate operator-approved phase; current
  monitoring and backtesting are not an advisory workflow.

## NASA And Mentionable Resources

- Build the Data & Tools NASA collection page from the existing `nasa.apod.list` RPC:
  featured media, collected-day navigation, video handling, copyright, and explanation.
- Generalize composer mentions into a capability-aware registry. A future `@NASA-IMOD`
  resolver should always inject title/explanation and attach an image only for
  vision-capable models.
- Reuse the mention registry for non-NASA resources; avoid feature-specific parser logic.

## Operator UI

- Add artifact editing to the inspector only after deciding where edited artifacts persist
  and how their original value is retained.
- Enrich Session Info with last-run age, artifact count, and error count.
- Perform a deliberate mobile density pass across shell gutters, cards, drawers, and
  composer spacing.
- Add dedicated `tool:called` / `tool:result` live events if the current aggregate feed
  cannot represent queued/running state honestly.
- Remove the Return Briefing development trigger and make the real `briefing.ready` path
  the only production source.
- Replace low-value provider-distribution charts with policy-decision breakdowns:
  allowed, blocked, and approval-required.
- Surface useful session context such as unresolved questions and constraints.

## Runtime And Code Health

- Continue extracting oversized modules by responsibility, especially
  `core/orchestrator/runtime.py`, `frontend/lib/wsClient.ts`, the frontend application
  store, `AgentComposer.tsx`, `DataToolsPage.tsx`, `types/backend.ts`,
  `ChatWorkspace.tsx`, and `InspectorDrawer.tsx`.
- Remove genuinely dead off-manifest handlers and compatibility types only after checking
  probes, tests, and internal callers. Do not delete registered-but-internal behavior by
  assumption.
- Decide whether the old test-only `core/multiagent` selector/fallback scaffold still has
  a product role now that Fleet and Research Lab share `core/coordination/LaneRunner`.
- Make the provider interface honest about system prompts; do not accept a system prompt
  in an adapter that silently discards it.
- Remove duplicate/unused legacy Responses request paths after verifying the active OAuth
  provider flow.
- Narrow `SessionStateRecord` only together with Pulse/Merge consumers.
- Make shell/tool output truncation explicit in result metadata.
- Replace substring-only high-risk shell matching with parsed command classification and
  evaluate every path-bearing argument for workspace scope.
- Add direct provider-turn elapsed timing and the provider-resolved model to traces.
- Decide whether provider-initialization failures should create an early run trace.
- Keep the React build/typecheck/unit suite in the standard verification loop and use
  browser validation for interaction behavior.

## Parked Ideas

- Make workspace intelligence actionable (for example, a recommended check that actually
  starts a run) before restoring it to the inspector.
- Consider syntax-aware editors only if the plain text editor becomes a real limitation.
- Expand NASA beyond APOD only after the APOD collection and mention pipeline are useful.
- Build additional domain workspaces after one manifest-driven workspace proves the model.
