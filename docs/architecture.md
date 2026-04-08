# CopeNet Architecture

This is a concise map of the current system. For contributor rules and working norms, see [AGENTS.md](../AGENTS.md).

## Subsystem Map

```text
copenet/
├── core/                        ← business logic and run lifecycle
│   ├── orchestrator/
│   │   ├── __init__.py          ← Orchestrator facade, ChatSendRequest
│   │   ├── catalog.py           ← session and provider catalog helpers
│   │   ├── runtime.py           ← send_chat run lifecycle
│   │   └── titles.py            ← async title generation
│   ├── harness/
│   │   └── __init__.py          ← ChatHarness, capability planning, tool loop
│   ├── sessions/
│   │   ├── session_store.py     ← SessionStore, SessionIndexEntry
│   │   └── transcript_store.py  ← TranscriptStore, TranscriptMessage
│   ├── tools/
│   │   ├── contracts.py         ← ToolDescriptor, ToolExecutionContext, etc.
│   │   ├── policy.py            ← ToolPolicy
│   │   ├── registry.py          ← ToolRegistry
│   │   └── builtin_readonly.py  ← built-in safe tool handlers
│   └── tracing/
│       └── __init__.py          ← RunTraceWriter
├── host/                        ← transport layer (no business logic)
│   ├── api.py
│   ├── ws_server.py
│   ├── rpc_schema.py
│   ├── rpc_dispatch.py
│   ├── rpc_chat.py
│   ├── rpc_sessions.py
│   ├── rpc_catalog.py
│   └── static/
│       ├── index.html
│       ├── app.js               ← ES module entry point (event wiring + connect())
│       └── js/
│           ├── state.js         ← shared state, DOM refs, catalog helpers
│           ├── rpc.js           ← sendReq WebSocket helper
│           ├── render/
│           │   ├── messages.js  ← markdown/math/tool-trace rendering
│           │   ├── sessions.js  ← session list DOM
│           │   └── header.js    ← badges + draft config selects
│           └── controllers/
│               ├── sessions.js  ← load/select/create/rename/archive
│               └── chat.js      ← connect, send, stream, bootstrap
├── providers/
│   ├── base.py
│   ├── codex_cli.py
│   └── local_http.py
├── runner/
├── prompts/
│   ├── loader.py
│   └── presets/
├── client.py                    ← stable external GatewayClient
│
│ — compatibility shims (re-export from core/) —
├── orchestrator.py
├── harness.py
├── tracing.py
├── sessions/
└── tools/
```

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
        |
        v
core/orchestrator/runtime.send_chat
  - idempotency check
  - session resolve / binding check
  - in-flight lock
  - transcript append (user)
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
  - final event emission
  - async title generation when appropriate
```

## Current Runtime Model

CopeNet currently supports:

- `codex-cli`
- `lm-studio`
- `ollama`

Provider responsibilities include:

- runtime availability checks
- model listing
- chat execution
- emitting normalized provider events

The UI consumes provider and model catalogs so the user can start a session with a specific runtime/model pair.

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

## Harness Direction

The harness exists to keep provider execution normalized and to prepare for richer capability routing and future tool work. It should remain a shared layer rather than becoming provider-specific glue.

## Configuration

CopeNet is configured primarily through environment variables for host/runtime endpoints and tokens. Runtime-specific local endpoints such as LM Studio and Ollama are injected from the environment rather than hardcoded throughout the app.

## Additional Reference

- [EVENT-CONTRACT.md](EVENT-CONTRACT.md)
- [SESSION-CONTINUITY.md](SESSION-CONTINUITY.md)
- [CAPABILITY-MATRIX.md](CAPABILITY-MATRIX.md)
