# CopeNet Architecture

This is a concise map of the current system. For contributor rules and working norms,
see [AGENTS.md](../AGENTS.md).

## Subsystem Map

High-level layout of `src/copenet/` (main packages and feature boundaries). Many `__init__.py` files are thin re-exports; substantive code lives in the sibling modules shown below.

```text
copenet/
├── _paths.py                          ← install / data path helpers
├── client.py                          ← stable external GatewayClient
├── core/                              ← business logic and run lifecycle (no imports from host/)
│   ├── apps/
│   │   └── app_store.py               ← external-app registry (bearer tokens, mappings)
│   ├── attachments/                    ← chat attachment persistence and resolution
│   ├── briefing/                       ← return-briefing assembly
│   ├── coordination/
│   │   └── lane_runner.py              ← shared provider-lane execution primitive
│   ├── fleet/                          ← durable multi-provider rooms and lane events
│   ├── harness/
│   │   ├── capabilities.py            ← capability profiles and routing
│   │   ├── planning.py                ← provider capability plan ahead of execution
│   │   ├── tool_loop.py               ← public tool-loop facade
│   │   ├── tool_loop_native.py        ← Chat Completions tool-call loop
│   │   ├── tool_loop_responses.py     ← Responses API tool-call loop
│   │   ├── tool_loop_prompted.py      ← prompted text-protocol tool loop
│   │   └── tool_loop_common.py        ← shared loop execution helpers
│   ├── media/
│   │   ├── downloader.py              ← yt-dlp / URL fetch
│   │   ├── transcriber.py             ← audio transcription
│   │   ├── store.py                   ← media asset persistence
│   │   └── service.py                 ← MediaIngestionService facade
│   ├── market/                         ← Market Monitor data, evidence, signals, replay, reads
│   ├── memory/
│   │   ├── store.py                   ← MemoryStore (preferences, conventions, facts)
│   │   └── service.py                 ← MemoryService API
│   ├── messaging/
│   │   ├── store.py                   ← MessagingConfigStore
│   │   └── routing_store.py           ← TelegramSessionRouteStore
│   ├── movies/                         ← Movie Lab import, enrichment, analysis, recommendations
│   ├── nasa/                           ← APOD store, fetch, and wallpaper support
│   ├── orchestrator/
│   │   ├── __init__.py                ← Orchestrator facade, ChatSendRequest
│   │   ├── facade_*.py                ← identity, messaging, provider auth, runtime workspace, approvals, apps
│   │   ├── catalog.py                 ← session catalog + provider registry build
│   │   ├── runtime.py                 ← send_chat run lifecycle
│   │   ├── titles.py                  ← async title generation
│   │   ├── merge.py                   ← merged-session creation/hydration
│   │   ├── messaging.py               ← messaging config / route helpers
│   │   ├── messages.py                ← build_chat_messages: transcript → Responses input[] (Phase 1)
│   │   ├── starter_intent.py          ← starter intent + tag normalization (was personal_history.py)
│   │   └── pulse.py                   ← Inbox Pulse helpers
│   ├── profile/
│   │   ├── __init__.py                ← Pat Profile public exports
│   │   ├── service.py                 ← layered profile loader, changelog, briefing builder
│   │   └── templates/                 ← repo-visible generic profile templates
│   ├── permissions/                    ← persisted operator shell approvals
│   ├── persona/                        ← persona storage, resolution, and authoring
│   ├── provider_auth/
│   │   ├── openai_codex.py            ← OpenAI Codex OAuth flow
│   │   └── store.py                   ← provider auth credential store
│   ├── pulse/
│   │   └── store.py                   ← PulseStore (Inbox pulses)
│   ├── research_lab/                   ← evidence-first research dossiers and calculations
│   ├── runtime/
│   │   ├── runs.py                    ← RunStore (durable run records)
│   │   ├── artifacts.py               ← ArtifactStore (per-session artifacts)
│   │   └── turn_state.py              ← per-turn structured state
│   ├── sessions/
│   │   ├── session_store.py           ← SessionStore, SessionIndexEntry
│   │   ├── transcript_store.py        ← TranscriptStore, TranscriptMessage
│   │   └── (state store re-exports)
│   ├── tools/
│   │   ├── contracts.py               ← ToolDescriptor, ToolExecutionContext, etc.
│   │   ├── policy.py                  ← ToolPolicy + policy_for_task_mode
│   │   ├── registry.py                ← ToolRegistry
│   │   ├── builtin_readonly.py        ← registers all built-ins (read + write + artifact; name is historical)
│   │   └── handlers/                  ← built-in tool implementations
│   │       ├── files.py               ← files.read/rg/write/edit (manifest); list/search registered but off-manifest
│   │       ├── git.py                 ← git.diff/status (off-manifest; use shell.exec git)
│   │       ├── shell.py               ← shell.exec
│   │       ├── artifacts.py           ← artifact.create (off-manifest, deferred)
│   │       ├── workspace_intel.py     ← repo.map + test.discover (off-manifest)
│   │       └── _shared.py
│   │   (context.py / context.prepare removed in Phase 0.3. The model-facing
│   │    manifest is the explicit MANIFEST_TOOL_IDS set in builtin_readonly.py.)
│   ├── tracing/
│   │   └── __init__.py                ← RunTraceWriter
│   ├── user_notes/                     ← draft-first USER.md change proposals
│   ├── workspace_intel/
│   │   ├── models.py                  ← workspace intel DTOs
│   │   ├── service.py                 ← repo mapping + verification discovery
│   │   └── store.py                   ← durable workspace cache
│   ├── knowledge_runtime.py           ← knowledge runtime entrypoint (Meme Lab and friends)
│   ├── meme_ideation.py               ← Meme Lab ideation public facade
│   ├── meme_ideation_*.py             ← Meme Lab constants, models, parsing, prompts, scoring, runtime
│   ├── meme_knowledge.py              ← Meme knowledge index
│   └── web_ingest.py                  ← WebIngestionService
│
├── host/                              ← HTTP / WebSocket transport (no business logic)
│   ├── main.py                        ← uvicorn entry + `auth` subcommands (`uv run copenet`)
│   ├── api.py                         ← FastAPI app, `/`, `/ws`, `/health`, `/api/v1`, static mounts
│   ├── ws_server.py                   ← WebSocket RPC server + frame protocol
│   ├── rpc_schema.py                  ← request/response/event shapes
│   ├── rpc_dispatch.py                ← method routing
│   ├── rpc_chat.py                    ← chat.send/abort/history handlers
│   ├── rpc_sessions.py                ← session + pulse + artifact handlers
│   ├── rpc_fleet.py                    ← Fleet room handlers
│   ├── rpc_market*.py                  ← Market dashboard/watchlist/calendar/yield handlers
│   ├── rpc_nasa.py                     ← NASA APOD handlers
│   ├── rpc_permissions.py              ← persisted approval allowlist handlers
│   ├── rpc_catalog.py                 ← compatibility export for catalog-style handlers
│   ├── rpc_catalog_core.py            ← provider/model/tool catalogs
│   ├── rpc_profile.py                 ← profile + briefing handlers
│   ├── rpc_persona.py                 ← persona handlers
│   ├── rpc_memory.py                  ← memory handlers
│   ├── rpc_messaging.py               ← messaging config + route handlers
│   ├── rpc_provider_auth.py           ← provider auth handlers
│   ├── rpc_runtime.py                 ← runtime context handlers
│   ├── app_api.py                     ← `/api/v1` REST + SSE for external apps (Subtext, etc.)
│   ├── frontend/                      ← Vite + React/TypeScript UI (primary surface)
│   │   ├── src/
│   │   │   ├── App.tsx, main.tsx
│   │   │   ├── components/            ← AppShell, AgentsPage, HomePage, RightPanel, …
│   │   │   ├── runtime/               ← adapter, types, mocks, activityProof
│   │   │   ├── store/                 ← useAppStore.ts (Zustand)
│   │   │   ├── workflows/             ← Meme Lab and other workflow surfaces
│   │   │   ├── lib/                   ← wsClient facade, normalizers, RPC/action/event helpers
│   │   │   └── types/                 ← backend.ts (typed RPC payloads)
│   │   ├── vite.config.ts
│   │   └── dist/                      ← production build served by the host
│
├── providers/                         ← runtime adapters
│   ├── base.py                        ← Provider, ProviderEvent, ProviderModel
│   ├── codex_cli.py                   ← Codex CLI subprocess
│   ├── claude_cli.py                  ← Claude CLI subprocess
│   ├── openai_codex.py                ← OpenAI Codex (subscription-backed via OAuth)
│   └── local_http.py                  ← LM Studio + Ollama (HTTP)
│
├── prompts/
│   ├── loader.py                      ← profile + Access-overlay composition
│   ├── optimizer.py                   ← prompt optimization variants
│   └── presets/                       ← profiles/, task-modes/, shared markdown
│
├── runner/
│   └── cli_runner.py                  ← shared CLI subprocess runner used by Codex/Claude CLI providers
│
├── browser_agent/                     ← deterministic browser-control prototype (Playwright)
│   ├── cli.py, loop.py, decision.py, observer.py, validator.py, session.py, trace.py, models.py
│
├── probes/
│   └── runtime_bundle.py              ← runtime probe payload helper
│
└── (legacy compatibility shims at top-level: orchestrator.py, harness.py, tracing.py,
   sessions/, tools/  — re-export from core/ for backward compatibility)
```

**Web UI:** `host/api.py` serves the React SPA from `host/frontend/dist/` at `/`, with `/assets` for hashed bundles and `/imgs` for public images. If the production build is missing, `/` returns an actionable `503`; build the frontend before starting a UI-serving host or packaging a wheel.

The `core/` boundary is strict: nothing under `core/` imports from `host/`. Transport concerns never leak into business logic.

## Request Flow

```text
Browser / GatewayClient / external app
        |
        | WebSocket RPC (`/ws`)  — or REST + SSE (`/api/v1` for external apps)
        v
CopeNetWsServer  (host/ws_server.py)
  - auth handshake
  - websocket transport
  - task lifecycle
        |
        v
RPC dispatch + handlers  (host/rpc_dispatch.py, rpc_chat.py, rpc_sessions.py, rpc_catalog*.py)
  - chat
  - sessions / pulses / artifacts / merges
  - catalogs (providers, models, prompts, tools)
  - profile, memory, messaging, providerAuth, runtime context
        |
        | chat.send
        v
Orchestrator facade  (core/orchestrator/__init__.py + facade_*.py mixins)
  - public API
  - provider registry construction (catalog.build_default_provider_registry)
  - profile / briefing access
  - workspace root validation
        |
        v
core/orchestrator/runtime.send_chat
  - idempotency check
  - session resolve / binding check
  - in-flight lock
  - transcript append (user)
  - Pat Profile context injection
        |
        v
ChatHarness.run_turn  (core/harness/)
  - capability normalization
  - native tool-loop selection when provider tool calls are available
  - direct provider passthrough for CLI and non-native providers
        |
        v
Provider  (providers/)
  - codex-cli (subprocess)        - claude-cli (subprocess)
  - openai-codex (HTTP, OAuth)    - lm-studio / ollama (HTTP)
        |
        v
Provider events
  - session continuity metadata
  - deltas
  - final
        |
        v
Orchestrator
  - transcript append (assistant)
  - session metadata update
  - run record persistence (RunStore)
  - artifact persistence (ArtifactStore) when tools produce them
  - post-run Pat Profile maintenance
  - return briefing generation
  - final event emission
  - async title generation when appropriate
```

## Current Runtime Model

CopeNet currently supports five providers, all behind the same harness:

| Provider id      | Adapter                          | Transport                          |
|------------------|----------------------------------|------------------------------------|
| `codex-cli`      | `providers/codex_cli.py`         | local subprocess (Codex CLI)       |
| `claude-cli`     | `providers/claude_cli.py`        | local subprocess (`claude` CLI)    |
| `openai-codex`   | `providers/openai_codex.py`      | OpenAI Codex API via OAuth         |
| `lm-studio`      | `providers/local_http.py`        | LM Studio HTTP (OpenAI-style)      |
| `ollama`         | `providers/local_http.py`        | Ollama HTTP                        |

Provider responsibilities:

- runtime availability checks
- model listing
- chat execution
- emitting normalized provider events
- (subscription providers) exposing an `auth_service` for the `providerAuth.*` RPCs

The browser UI consumes provider and model catalogs so the user can start a session with a specific runtime/model pair. See [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md) for tool-loop and feature support per provider.

## Harness Control Model

CopeNet uses a model-driven harness with runtime-enforced policy. The current
implementation is described here and in
[HARNESS_REBUILD_V2.md](plans/HARNESS_REBUILD_V2.md).

The operating rule is:

- **Mode controls context**
- **Policy controls authority**
- **Model controls reasoning**

In practice that means:

- the harness exposes the policy-visible capability surface
- the model decides when repo inspection, planning, or edits are useful
- the runtime still enforces what is actually allowed

`core/harness/planning.py` does not read prompt text. It records provider/model capabilities and selects the tool-execution mode: `responses` (native Responses API, when the provider declares `responsesApi` — openai-codex), `native` (Chat Completions tool calls — LM Studio/Ollama), `prompted` (text-protocol fallback), or `none`.

`core/harness/tool_loop.py` is the public facade for turn-level tool continuation. The concrete loops live in `tool_loop_responses.py` (`run_with_responses_tools`, streaming the native function_call lifecycle and appending `function_call`/`function_call_output` items to the input[] array), `tool_loop_native.py` (`run_with_native_tools`, Chat Completions), and `tool_loop_prompted.py` (`run_with_prompted_tools`). Shared execution helpers live in `tool_loop_common.py`, and model-facing result artifact materialization lives in `tool_result_materialization.py`. All loops stream normalized events and let the model decide when to finalize (cap: `MAX_TOOL_STEPS=100`, with an explicit stop note when hit). The harness does not classify prompt text, keyword-match intent, or force a tool sequence; routing and evidence sufficiency are the model's responsibility, with the runtime enforcing authority via `ToolPolicy`.

`core/orchestrator/messages.py` builds the real multi-turn message history (Phase 1): `build_chat_messages` walks the durable transcript into a Responses-API `input[]` array (used directly by the responses loop) and `flatten_messages_to_prompt` renders it as a transcript-style string for prompt-only providers. This replaced the synthetic `working_set` blob and the keyword auto-mutation of session state.

`core/harness/decision.py` adds a trace-only `HarnessDecisionRecord` for providers that expose an isolated decision hook. The model declares enum fields such as request kind, route, next action, risk, and evidence requirements, plus prose `trace_note` fields for inspector/debug display. In v1 this record never steers execution: normal planning, provider output, tool calls, and final answers continue exactly as they would if the decision were unavailable.

## Session Model

Sessions carry:

- session key and session id
- provider, model, profile (`systemPromptId`), Access (`taskPromptId`)
- workspace root
- title, archived state
- provider session id (when the provider emits one)
- run lifecycle metadata (`lastRunId`, `inFlightRunId`)
- created / updated timestamps

Important invariants:

- sessions are draft-editable before first send
- after first send, provider/profile/persona/workspace remain locked
- the operator may change model within the same provider and may change Access
- every run records the provider/model it actually used
- transcripts are append-only
- only one in-flight run is allowed per session

## Prompt Layer

Prompt behavior splits into:

- base profiles
- Access overlays (stored under the historical `task-modes/` directory)

`prompts/loader.py` composes them into the final system prompt sent with a turn. Authoring stays in markdown files under `prompts/presets/`. `prompts/optimizer.py` produces optimized variant suggestions.

## Identity Layer (Pat Profile)

CopeNet has a separate **Pat Profile** layer that models the operator independently from any one session.

V1 surface area:

- active priorities, current goals, tone preferences, noise filters
- schedule basics, recurring constraints
- observed tendencies, guidance rules

Storage model is layered:

- repo-visible generic templates under `core/profile/templates/`
- private local overlay under `~/.copenet/profile/` or `COPNET_DATA_DIR/profile`

Repo templates and examples are safe to commit; real overlay data is local-only and should stay out of git.

Runtime usage:

- normal agent sessions can receive Pat Profile context in the system prompt
- post-run maintenance may append conservative profile updates
- Home / briefing surfaces consume normalized profile and changelog payloads

## Operator Adjacencies (beyond chat)

These subsystems are owned by `core/` but are not part of the core chat path. They power the broader operator console:

- **`core/runtime` (RunStore + ArtifactStore + turn state)** — durable per-run records and per-session artifacts. Backs Tool Activity proof in the UI.
- **`core/pulse`** — Inbox pulses surfaced on Home and convertible into agent sessions.
- **`core/memory`** — explicit user-visible memory items (preferences, conventions, ongoing priorities, facts).
- **`core/messaging`** — messaging config + Telegram chat-to-session route mapping (Chat Anywhere foundations).
- **`core/media`** — URL/audio ingestion and transcription used by Data & Tools workflows.
- **`core/web_ingest`** — web ingestion service used by Data & Tools.
- **`core/apps`** — external-app registry and bearer-token mapping for `/api/v1` clients (e.g. Subtext).
- **`core/provider_auth`** — provider-owned auth state (currently OpenAI Codex OAuth).
- **`core/knowledge_runtime` / `meme_*`** — Meme Lab knowledge runtime + ideation workflow.
- **`core/market`** — Market Monitor data, evidence, signals, model reads, replay, and
  backtesting.
- **`core/fleet` + `core/coordination`** — durable multi-provider rooms over shared lane
  execution.
- **`core/research_lab`** — evidence snapshots, benchmark calculations, and research
  dossiers.
- **`core/nasa` / `core/movies`** — APOD and Movie Lab operator workflows.

These are surfaced through dedicated RPC namespaces (`pulse.*`, `memory.*`,
`messaging.*`, `runtime.*`, `providerAuth.*`, `sessions.merge.*`, `fleet.*`,
`market.*`, `nasa.*`) — see `host/rpc_dispatch.py` for the canonical method list.

## Browser Agent (prototype lane)

`src/copenet/browser_agent/` is a deterministic Playwright-backed browser-control prototype (observe → decide → validate → act → trace). It is not part of the chat run lifecycle; it has its own CLI entrypoint (`uv run copenet-browser-demo`) and its own JSONL trace under `~/.copenet/logs/runs/browser-agent/`. See [BROWSER-AGENT-PROTOTYPE.md](BROWSER-AGENT-PROTOTYPE.md).

## Harness Direction

The harness keeps provider execution normalized and prepares for richer capability routing and future tool work. It should remain a shared layer rather than becoming provider-specific glue.

### Prompted tools and policy (today)

- **Categories** (`ToolCategory` in `core/tools/contracts.py`): `repo-read`, `repo-write`, `shell-read`, `context`, `artifact`, and reserved `mcp`.
- **Task mode drives policy**: `policy_for_task_mode()` in `core/tools/policy.py` builds the effective policy from the persisted session **`task_prompt_id`**. Baseline modes allow **`repo-read`**, **`shell-read`**, **`context`**, **`artifact`**. **`full-access`** adds **`repo-write`** so `files.edit` / `files.write` register in `available_tools` for that run.
- **Model-facing manifest** is the explicit `MANIFEST_TOOL_IDS` set in
  `core/tools/builtin_readonly.py`. It includes the core file/shell/plan/web tools plus
  approved domain tools for Market, personas, memory, and user-note proposals.
  `ToolRegistry.list_tools()` returns that policy-filtered manifest;
  `list_registered_tools()` returns the larger internal/compatibility set.
- **`ToolExecutionContext`** carries **`task_prompt_id`**, **`run_id`**, and optional **`artifact_store`** so prompts and artifact writes stay session-scoped.
- Prompted tool use accepts exact JSON tool objects such as `{"tool_id":"files.read","arguments":{"path":"README.md"}}`. The current permissive shorthand parser is retained for compatibility, but the target contract is exact tool ids and structured arguments.
- Tool manifests attach deterministic capability metadata: registered id, JSON schema, category, evidence role, side effect, and confirmation posture. The harness branches on these enum/id fields and policy decisions, not prose explanations.

## Configuration

CopeNet is configured primarily through environment variables for host/runtime endpoints and tokens. Runtime-specific local endpoints (LM Studio, Ollama) are injected from the environment rather than hardcoded throughout the app. See `README.md` for the canonical env var list.

## Additional Reference

- [EVENT-CONTRACT.md](EVENT-CONTRACT.md) — `/ws` frame contract and `chat` event payload
- [APP-API.md](APP-API.md) — `/api/v1` REST/SSE for external apps
- [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md) — session lock/draft semantics
- [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md) — provider feature matrix
- [TRACING.md](TRACING.md) + [DEBUGGING.md](DEBUGGING.md) — run-trace observability
- [OPERATOR-UX-MODEL.md](OPERATOR-UX-MODEL.md) — three-layer tool-truth model (transcript / activity / inspector)
- [BROWSER-AGENT-PROTOTYPE.md](BROWSER-AGENT-PROTOTYPE.md) — Playwright prototype lane
