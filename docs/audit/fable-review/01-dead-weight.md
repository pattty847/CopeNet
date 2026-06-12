# Dead Weight

Code, surfaces, RPCs, and components that serve nothing live today. Verdicts: DEAD (no reachable path), PARTIAL (some of it is live), LIVE-BUT-DISHONEST (reachable but fakes its result).

## Backend

### `core/multiagent/` — DEAD (test-only scaffold)
`delegation.py` (137 lines), `fallback_executor.py`, `orchestrator_adapter.py`, `provider_selector.py` — added in HEAD commit `ab3b288`. The only importer outside the package is `tests/unit/test_multiagent_orchestrator.py`. Nothing in the orchestrator, harness, or tools layer calls it; no `agent.*`/delegate tool is registered. The default role map targets `breadth: "gemini"` (`provider_selector.py:50`) — a provider id that does not exist in `src/copenet/providers/`. The package docstring says "wired in incrementally" so this may be intentional staging per `docs/plans/MULTI_AGENT_ORCHESTRATOR.md`, but as of HEAD it is unreachable.

### `host/agents_api.py` — DEAD
21 lines; the sole route is `GET /api/v1/agents/ping` (`agents_api.py:14`) returning a static payload. Mounted in `api.py:50`; only callers are tests. Part of the same `ab3b288` sub-agents scaffold.

### External-app lane (`core/apps/` + half of `app_api.py`) — effectively DEAD
`register_app` (`app_store.py:103`) is callable only from a plain orchestrator method (`orchestrator/__init__.py:813`) — no RPC, no CLI subcommand, no script mints a token. Every `Depends(require_app)` route in `app_api.py:322-415,585-643` (`/providers`, `/models`, `/sessions*`, `/messages*`, `/runs/{id}/cancel`) is therefore unreachable until a registration surface exists. The `require_media_access` routes (media, memes, web/extract) remain live via the gateway token.

### `/api/v1/messaging/telegram/inbound` — DEAD (no producer)
`app_api.py:417` is a webhook endpoint with no webhook registration, poller, or bridge anywhere in the repo (zero `getUpdates`/`setWebhook` hits). The inbound route→session machinery (`core/messaging/routing_store.py`, `resolve_messaging_route`) is exercised only by this endpoint and the dead RPC below.

### RPC `messaging.routes.resolve` — DEAD
Dispatched (`rpc_dispatch.py:193`), implemented (`rpc_catalog.py:640`), advertised in the connect hello (`ws_server.py:176`) — zero callers in `frontend/src` and `client.py`. Its only logical consumer is the nonexistent Telegram bridge.

### `messaging.test` — LIVE-BUT-DISHONEST
`orchestrator/messaging.py:237-270`: if a token string merely exists, it persists `connection_status="connected"` with a fresh `last_verified_at` and returns "looks ready." No call to `api.telegram.org` exists anywhere. A Test button that always passes — backend-side violation of the "UI stays honest" principle.

### Off-manifest tool handlers — PARTIAL (documented as pending Phase 5 deletion)
`builtin_readonly.py:29-38` filters the model-facing manifest to 8 tools, but `git.status`/`git.diff` (duplicate of `shell.exec git …`), `memory.read`/`memory.write`, `artifact.create`, `repo.map`, `test.discover` remain registered and model-unreachable. The comment at `builtin_readonly.py:25-28` says the handler files get deleted "in the Phase 5 sweep" — the sweep hasn't happened.

### `core/workspace_intel/` — PARTIAL
`get_summary()` is live via the `runtime.context` RPC (`orchestrator/__init__.py:637`). `get_workspace_map`/`discover_tests` (`service.py:53,57`) are reachable only through the off-manifest `repo.map`/`test.discover` tools — stranded.

### `browser_agent/` — PARTIAL (sealed prototype)
Has its own entry point (`copenet-browser-demo`, `pyproject.toml:29`); importers outside the package are 4 unit tests. Zero references from host/orchestrator/harness/tools. If the demo CLI isn't being run, it's dead weight to the gateway product.

### Meme knowledge chain — LIVE, but `knowledge_runtime.py` oversells itself
`knowledge_runtime.py` (118 lines) is imported solely by `meme_knowledge.py` → `meme_ideation.py` → `app_api.py:450/508` + MemeLab UI. It works, but the generic name suggests a shared knowledge subsystem; it serves only meme ideation.

## Frontend

### Mock leakage into live hooks — the worst offender, not dead but actively harmful
`runtime/mocks.ts` (650 lines) is imported by `adapter.ts:5-11`. `resolveKey()` (`mocks.ts:262-265`) returns the `__fallback__` dataset for **any** session key, so the mocks are never empty:
- `useArtifact` (`adapter.ts:149`) and `useBatch` (`adapter.ts:230`) fall back to mock artifacts/batches and ARE consumed by the live `InspectorDrawer.tsx:456-457`. The mock set includes a fabricated **pending approval** (`appr_c3d9f1a2`, `mocks.ts:119-130`).
- `useWorkingSet` (`adapter.ts:73`) serves a fabricated task for any session — though it now has zero component consumers, so it's dead code carrying a mock.
- `useRunActivity` (`adapter.ts:187`) mixes mock artifacts into real run mapping, while `RunActivityPanel.tsx:12` claims "Fully real ... no mock dependency."

Direct violation of CLAUDE.md's "never auto-seed mock data into hooks."

### `SendMessageComposer` — DEAD-END THEATER
`SendMessageComposer.tsx:181,199` → `simulateSendMessageComposed` (`adapter.ts:399-428`) fabricates an `OutboundMessageRecord` (`msg_sim_…`) and a fake approval. No `messaging.send` RPC exists; no delivery code exists in the backend. Approving the simulated approval even calls the real `chat.decideApproval` with a fabricated id the backend won't recognize.

### `useMockTransitions` — PARTIAL, misnamed, in four production components
`adapter.ts:332-439`, consumed by `ApprovalQueuePanel.tsx:74`, `OperatorActionCenter.tsx:75`, `RunTimeline.tsx:239`, `SendMessageComposer.tsx:181`. `simulateApprove`/`simulateReject` call the **real** `decideApproval` RPC — live behavior behind a "simulate" name — while `simulateApprovalRequested`/`simulateModify`/`simulateRunResumed`/`simulateSendMessageComposed` are pure fakes. Splitting the real approve/reject out is the prerequisite to deleting the rest.

### `RunTimeline` — DEAD render path
`useRunTimeline` (`adapter.ts:484-497`) reads a store slice nothing ever populates (the only `setRunTimeline` call with a value is the clear-on-resume `null`). `RunTimeline.tsx` is mounted at `RightPanel.tsx:550` and can only render its empty branch. `MOCK_RUN_TIMELINE` (`mocks.ts:479-567`) has zero importers.

### Dead adapter hooks
`useWorkingSet` (`adapter.ts:51`), `useArtifacts` (`adapter.ts:87`), `useLastTurnState` (`adapter.ts:534`) — zero component consumers. The first two are also the worst mock-fallback offenders; deleting them removes mock leakage for free.

### Dead wsClient wrappers
`listPulses` (`wsClient.ts:1556`), `getMessagingConfig` (`:1563`), `listMessagingDestinations` (`:1568`), `listMessagingRoutes` (`:1575`), `resolveSessionRun` (`:1893`) — zero callers; bootstrap + push events already populate the store. The corresponding `messaging.destinations.list` / `messaging.routes.list` RPCs are consequently near-dead.

### `abortActiveRun` — DEAD wrapper hiding a missing feature
`wsClient.ts:2047` has zero component callers, but the backend RPC is live. This isn't code to delete — it's a Stop button waiting to be built (see `07-daily-driver-friction.md`).

### Rotting pure-mock exports
`getMockPendingApproval` (`mocks.ts:293`), `MOCK_APPROVAL_HISTORY` (`:303`), `MOCK_DESTINATIONS` (`:405`), `MOCK_MESSAGING_CONFIG` (`:449`), `MOCK_RUN_TIMELINE` (`:479`) and their getters — zero importers. **Caution before a delete sweep:** `buildInboxItems` (`mocks.ts:574-650`) is REAL derivation logic consumed by the live `useInboxItems` (`adapter.ts:471`) — it's mislocated in the mocks module and must move out first.

### MemeLab 404 fallback — leftover that masks failures
`memeClient.ts:240,281` — `allowMock` defaults true and substitutes local mock ideation on 404/network failure. The backend endpoints now exist (`app_api.py:450,508`), so this fallback converts real failures into fake successes. Flip to an error state.

### Stale connect-hello metadata
`ws_server.py:139-198` advertises the dead `messaging.routes.resolve` and omits the live `sessions.export`/`sessions.debugCopy`. Nothing consumes `features.methods` today, making the list itself arguably dead weight.
