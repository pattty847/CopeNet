# CopeNet Architecture

This is a concise map of the current system. For contributor rules and working norms, see [AGENTS.md](../AGENTS.md).

## Subsystem Map

High-level layout of `src/copenet/` (main packages and feature boundaries). Many `__init__.py` files are thin re-exports; substantive code lives in the sibling modules shown below.

```text
copenet/
├── _paths.py                    ← install / data path helpers
├── client.py                    ← stable external GatewayClient
├── core/                        ← business logic and run lifecycle (no imports from host/)
│   ├── orchestrator/
│   │   ├── __init__.py          ← Orchestrator facade, ChatSendRequest
│   │   ├── catalog.py           ← session and provider catalog helpers
│   │   ├── runtime.py           ← send_chat run lifecycle
│   │   └── titles.py            ← async title generation
│   ├── harness/
│   │   ├── __init__.py          ← ChatHarness entry
│   │   ├── capabilities.py      ← capability profiles and routing
│   │   ├── planning.py          ← turn planning ahead of provider execution
│   │   └── tool_loop.py         ← tool invocation loop
│   ├── profile/
│   │   ├── __init__.py          ← Pat Profile public exports
│   │   ├── service.py           ← layered profile loader, changelog, briefing builder
│   │   └── templates/           ← repo-visible generic profile templates
│   ├── sessions/
│   │   ├── session_store.py     ← SessionStore, SessionIndexEntry
│   │   └── transcript_store.py  ← TranscriptStore, TranscriptMessage
│   ├── tools/
│   │   ├── contracts.py         ← ToolDescriptor, ToolExecutionContext, etc.
│   │   ├── policy.py            ← ToolPolicy
│   │   ├── registry.py          ← ToolRegistry
│   │   ├── builtin_readonly.py  ← read-only built-ins
│   │   └── handlers/            ← built-in tool implementations (files, git, shell, …)
│   │       ├── context.py
│   │       ├── files.py
│   │       ├── git.py
│   │       ├── shell.py
│   │       └── _shared.py
│   └── tracing/
│       └── __init__.py          ← RunTraceWriter
├── host/                        ← HTTP/WebSocket transport (no business logic)
│   ├── main.py                  ← uvicorn entry (`uv run copenet`)
│   ├── api.py                   ← FastAPI app, `/`, `/ws`, static mounts
│   ├── ws_server.py             ← WebSocket RPC server
│   ├── rpc_schema.py            ← request/response shapes
│   ├── rpc_dispatch.py          ← method routing
│   ├── rpc_chat.py
│   ├── rpc_sessions.py
│   ├── rpc_catalog.py
│   ├── frontend/                ← Vite + React/TypeScript UI
│   │   ├── src/                 ← App shell, chat workspace, WebSocket client, store, types
│   │   ├── vite.config.ts
│   │   └── dist/                ← production build (served when present; see note below)
│   └── static/                  ← legacy vanilla ES module UI + assets under `/static`
│       ├── index.html
│       ├── app.js
│       └── js/                  ← state, rpc, render/*, controllers/*
├── providers/                   ← runtime adapters
│   ├── base.py
│   ├── codex_cli.py
│   └── local_http.py            ← LM Studio, Ollama, etc.
├── prompts/
│   ├── loader.py
│   └── presets/                 ← profiles/, task-modes/, shared markdown
├── runner/
│   └── cli_runner.py            ← non-gateway CLI helper
│
│ — compatibility shims (re-export from core/) —
├── orchestrator.py
├── harness.py
├── tracing.py
├── sessions/
└── tools/
```

**Web UI:** `host/api.py` serves the SPA from `host/frontend/dist/` at `/` (and `/assets` for hashed bundles) when `frontend/dist` exists; otherwise it falls back to `host/static/index.html`. The legacy tree under `host/static/` remains available at `/static/` for the vanilla client and shared assets.

The `core/` boundary is strict: nothing under `core/` imports from `host/`. Transport concerns never leak into business logic.

## Request Flow

```text
Browser / GatewayClient
        |
        | WebSocket RPC
        v
CopeNetWsServer
  - auth handshake
  - websocket transport
  - task lifecycle
        |
        v
RPC dispatch + handlers
  - chat
  - sessions
  - catalogs
  - tools
        |
        | chat.send
        v
Orchestrator facade
  - public API
  - provider construction
  - profile / briefing access
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
ChatHarness.run_turn
  - choose capability profile
  - normalize provider execution path
        |
        v
Provider
  - Codex CLI subprocess
  - LM Studio HTTP
  - Ollama HTTP
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
  - post-run Pat Profile maintenance
  - return briefing generation
  - final event emission
  - async title generation when appropriate
```

## Current Runtime Model

CopeNet currently supports:

- `openai-codex`
- `codex-cli`
- `lm-studio`
- `ollama`

Provider responsibilities include:

- runtime availability checks
- model listing
- chat execution
- emitting normalized provider events

The browser UI (built React app or legacy static client) consumes provider and model catalogs so the user can start a session with a specific runtime/model pair.

## Session Model

Sessions now carry:

- session key and session id
- provider
- model
- profile (`systemPromptId`)
- task mode (`taskPromptId`)
- title
- provider session id
- run lifecycle metadata

Important invariants:

- sessions are draft-editable before first send
- after first send, provider/model/profile/task mode are treated as locked
- transcripts are append-only
- only one in-flight run is allowed per session

## Prompt Layer

Prompt behavior is split into:

- base profiles
- task-mode overlays

`prompts/loader.py` composes them into the final system prompt that is sent with a turn. Prompt authoring stays in markdown files under `prompts/presets/`.

## Identity Layer

CopeNet now has a separate **Pat Profile** layer that models the operator independently from any one session.

V1 is intentionally narrow:

- active priorities
- current goals
- tone preferences
- noise filters
- schedule basics
- recurring constraints
- observed tendencies
- guidance rules

The storage model is layered:

- repo-visible generic templates under `core/profile/templates/`
- private local overlay under `~/.copenet/profile/` or `COPNET_DATA_DIR/profile`

Important rule:

- repo templates and examples are safe to commit
- real overlay data is local-only and should stay out of git

Runtime usage today:

- normal agent sessions can receive Pat Profile context in the system prompt
- post-run maintenance may append conservative profile updates
- Home / briefing surfaces consume normalized profile and changelog payloads

## Harness Direction

The harness exists to keep provider execution normalized and to prepare for richer capability routing and future tool work. It should remain a shared layer rather than becoming provider-specific glue.

## Configuration

CopeNet is configured primarily through environment variables for host/runtime endpoints and tokens. Runtime-specific local endpoints such as LM Studio and Ollama are injected from the environment rather than hardcoded throughout the app.

## Additional Reference

- [EVENT-CONTRACT.md](EVENT-CONTRACT.md)
- [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md)
- [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md)
