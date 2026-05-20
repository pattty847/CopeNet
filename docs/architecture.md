# CopeNet Architecture

This is a concise map of the current system. For contributor rules and working norms, see [AGENTS.md](../AGENTS.md). For per-subsystem scope and ownership intended for multi-agent routing, see [SUBSYSTEMS.md](SUBSYSTEMS.md) when present.

## Subsystem Map

High-level layout of `src/copenet/` (main packages and feature boundaries). Many `__init__.py` files are thin re-exports; substantive code lives in the sibling modules shown below.

```text
copenet/
├── _paths.py                          ← install / data path helpers
├── client.py                          ← stable external GatewayClient
├── core/                              ← business logic and run lifecycle (no imports from host/)
│   ├── apps/
│   │   └── app_store.py               ← external-app registry (bearer tokens, mappings)
│   ├── harness/
│   │   ├── capabilities.py            ← capability profiles and routing
│   │   ├── planning.py                ← provider capability plan ahead of execution
│   │   └── tool_loop.py               ← native provider tool-call loop
│   ├── media/
│   │   ├── downloader.py              ← yt-dlp / URL fetch
│   │   ├── transcriber.py             ← audio transcription
│   │   ├── store.py                   ← media asset persistence
│   │   └── service.py                 ← MediaIngestionService facade
│   ├── memory/
│   │   ├── store.py                   ← MemoryStore (preferences, conventions, facts)
│   │   └── service.py                 ← MemoryService API
│   ├── messaging/
│   │   ├── store.py                   ← MessagingConfigStore
│   │   └── routing_store.py           ← TelegramSessionRouteStore
│   ├── orchestrator/
│   │   ├── __init__.py                ← Orchestrator facade, ChatSendRequest
│   │   ├── catalog.py                 ← session catalog + provider registry build
│   │   ├── runtime.py                 ← send_chat run lifecycle
│   │   ├── titles.py                  ← async title generation
│   │   ├── merge.py                   ← merged-session creation/hydration
│   │   ├── messaging.py               ← messaging config / route helpers
│   │   ├── personal_history.py        ← starter intent + tag normalization
│   │   ├── pulse.py                   ← Inbox Pulse helpers
│   │   └── working_set.py             ← session working set helpers
│   ├── profile/
│   │   ├── __init__.py                ← Pat Profile public exports
│   │   ├── service.py                 ← layered profile loader, changelog, briefing builder
│   │   └── templates/                 ← repo-visible generic profile templates
│   ├── provider_auth/
│   │   ├── openai_codex.py            ← OpenAI Codex OAuth flow
│   │   └── store.py                   ← provider auth credential store
│   ├── pulse/
│   │   └── store.py                   ← PulseStore (Inbox pulses)
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
│   │       ├── files.py               ← files.list/read/search/rg/write/edit
│   │       ├── git.py                 ← git.diff/status
│   │       ├── shell.py               ← shell.exec
│   │       ├── context.py             ← context.prepare
│   │       ├── artifacts.py           ← artifact.create
│   │       ├── workspace_intel.py     ← repo.map + test.discover
│   │       └── _shared.py
│   ├── tracing/
│   │   └── __init__.py                ← RunTraceWriter
│   ├── workspace_intel/
│   │   ├── models.py                  ← workspace intel DTOs
│   │   ├── service.py                 ← repo mapping + verification discovery
│   │   └── store.py                   ← durable workspace cache
│   ├── knowledge_runtime.py           ← knowledge runtime entrypoint (Meme Lab and friends)
│   ├── meme_ideation.py               ← Meme Lab ideation API
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
│   ├── rpc_catalog.py                 ← provider/model/tools/profile/messaging handlers
│   ├── app_api.py                     ← `/api/v1` REST + SSE for external apps (Subtext, etc.)
│   ├── frontend/                      ← Vite + React/TypeScript UI (primary surface)
│   │   ├── src/
│   │   │   ├── App.tsx, main.tsx
│   │   │   ├── components/            ← AppShell, AgentsPage, HomePage, RightPanel, …
│   │   │   ├── runtime/               ← adapter, types, mocks, activityProof
│   │   │   ├── store/                 ← useAppStore.ts (Zustand)
│   │   │   ├── workflows/             ← Meme Lab and other workflow surfaces
│   │   │   ├── lib/                   ← wsClient, RPC helpers
│   │   │   └── types/                 ← backend.ts (typed RPC payloads)
│   │   ├── vite.config.ts
│   │   └── dist/                      ← production build (served when present; see note below)
│   └── static/                        ← legacy vanilla ES module UI + assets under `/static`
│
├── providers/                         ← runtime adapters
│   ├── base.py                        ← Provider, ProviderEvent, ProviderModel
│   ├── codex_cli.py                   ← Codex CLI subprocess
│   ├── claude_cli.py                  ← Claude CLI subprocess
│   ├── openai_codex.py                ← OpenAI Codex (subscription-backed via OAuth)
│   └── local_http.py                  ← LM Studio + Ollama (HTTP)
│
├── prompts/
│   ├── loader.py                      ← profile + task-mode composition
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

**Web UI:** `host/api.py` serves the SPA from `host/frontend/dist/` at `/` (and `/assets` for hashed bundles) when the dist exists; otherwise it falls back to `host/static/index.html`. The legacy tree under `host/static/` remains available at `/static/` for the vanilla client and shared assets. The React app is the primary surface; the vanilla UI is fallback only.

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
RPC dispatch + handlers  (host/rpc_dispatch.py, rpc_chat.py, rpc_sessions.py, rpc_catalog.py)
  - chat
  - sessions / pulses / artifacts / merges
  - catalogs (providers, models, prompts, tools)
  - profile, memory, messaging, providerAuth, runtime context
        |
        | chat.send
        v
Orchestrator facade  (core/orchestrator/__init__.py)
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

CopeNet is moving toward a model-driven harness with runtime-enforced policy. The active design note is [Model-Driven Harness, Policy-Enforced Runtime](roadmaps/model-driven-harness-policy-runtime.md).

The operating rule is:

- **Mode controls context**
- **Policy controls authority**
- **Model controls reasoning**

In practice that means:

- the harness exposes the policy-visible capability surface
- the model decides when repo inspection, planning, or edits are useful
- the runtime still enforces what is actually allowed

`core/harness/planning.py` does not read prompt text. It records provider/model capabilities and selects only between native tool calling and plain provider passthrough.

`core/harness/tool_loop.py` owns turn-level tool continuation. It executes provider-native or prompted tool calls under policy, streams normalized events, and lets the model decide when it has enough information to finalize. The harness does not classify prompt text or force a particular tool sequence before accepting a final answer; routing and evidence sufficiency are the model's responsibility, with the runtime enforcing authority via `ToolPolicy`.

## Session Model

Sessions carry:

- session key and session id
- provider, model, profile (`systemPromptId`), task mode (`taskPromptId`)
- workspace root
- title, archived state
- provider session id (when the provider emits one)
- run lifecycle metadata (`lastRunId`, `inFlightRunId`)
- created / updated timestamps

Important invariants:

- sessions are draft-editable before first send
- after first send, provider/model/profile/task mode/workspace are treated as locked
- transcripts are append-only
- only one in-flight run is allowed per session

## Prompt Layer

Prompt behavior splits into:

- base profiles
- task-mode overlays

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

These are surfaced through dedicated RPC namespaces (`pulse.*`, `memory.*`, `messaging.*`, `runtime.*`, `providerAuth.*`, `sessions.merge.*`) — see `host/rpc_dispatch.py` for the canonical method list.

## Browser Agent (prototype lane)

`src/copenet/browser_agent/` is a deterministic Playwright-backed browser-control prototype (observe → decide → validate → act → trace). It is not part of the chat run lifecycle; it has its own CLI entrypoint (`uv run copenet-browser-demo`) and its own JSONL trace under `~/.copenet/logs/runs/browser-agent/`. See [BROWSER-AGENT-PROTOTYPE.md](BROWSER-AGENT-PROTOTYPE.md).

## Harness Direction

The harness keeps provider execution normalized and prepares for richer capability routing and future tool work. It should remain a shared layer rather than becoming provider-specific glue.

### Prompted tools and policy (today)

- **Categories** (`ToolCategory` in `core/tools/contracts.py`): `repo-read`, `repo-write`, `shell-read`, `context`, `artifact`, and reserved `mcp`.
- **Task mode drives policy**: `policy_for_task_mode()` in `core/tools/policy.py` builds the effective policy from the persisted session **`task_prompt_id`**. Baseline modes allow **`repo-read`**, **`shell-read`**, **`context`**, **`artifact`**. **`full-access`** adds **`repo-write`** so `files.edit` / `files.write` register in `available_tools` for that run.
- **Built-in ids** include `context.prepare`, **`files.list`**, **`files.read`**, **`files.search`**, **`files.rg`**, **`files.write`**, **`files.edit`**, `git.diff`, `git.status`, **`shell.exec`**, **`artifact.create`**.
- **`ToolExecutionContext`** carries **`task_prompt_id`**, **`run_id`**, and optional **`artifact_store`** so prompts and artifact writes stay session-scoped.
- **TOOL_BATCH** executes only **`repo-read` + `context`** calls together. Writes or shell mixed into the same JSON batch are deferred and repaired (trace `tool_batch_split`; see `core/harness/tool_loop.py`).
- **`build_tool_prompt_section`** attaches a deterministic **capability manifest** next to the JSON action grammar (workspace root, allowed tool ids, unavailable capability classes, shell allowlist).

## Configuration

CopeNet is configured primarily through environment variables for host/runtime endpoints and tokens. Runtime-specific local endpoints (LM Studio, Ollama) are injected from the environment rather than hardcoded throughout the app. See `README.md` for the canonical env var list.

## Additional Reference

- [EVENT-CONTRACT.md](EVENT-CONTRACT.md) — `/ws` frame contract and `chat` event payload
- [APP-API.md](APP-API.md) — `/api/v1` REST/SSE for external apps
- [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md) — session lock/draft semantics
- [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md) — provider feature matrix
- [TRACING.md](TRACING.md) + [DEBUGGING.md](DEBUGGING.md) — run-trace observability
- [operator-ux-model.md](operator-ux-model.md) — three-layer tool-truth model (transcript / activity / inspector)
- [BROWSER-AGENT-PROTOTYPE.md](BROWSER-AGENT-PROTOTYPE.md) — Playwright prototype lane
