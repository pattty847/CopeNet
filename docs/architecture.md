# CopeNet Architecture

This is a concise map of the current system. For contributor rules and working norms, see [AGENTS.md](/Users/copeharder/Programming/CopeNet/AGENTS.md).

## Subsystem Map

```text
copenet/
├── host/
│   ├── api.py
│   ├── ws_server.py
│   ├── rpc_schema.py
│   └── static/
├── orchestrator.py
├── harness.py
├── providers/
│   ├── base.py
│   ├── codex_cli.py
│   └── local_http.py
├── runner/
├── sessions/
│   ├── session_store.py
│   └── transcript_store.py
├── prompts/
│   ├── loader.py
│   └── presets/
└── client.py
```

## Request Flow

```text
Browser / GatewayClient
        |
        | WebSocket RPC
        v
CopeNetWsServer
  - auth handshake
  - request dispatch
  - streaming event fanout
        |
        | chat.send
        v
Orchestrator.send_chat
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
