# CopeNet Backend Refactor Blueprint

This document is the worker handoff for the backend-first refactor phase. It exists so fast worker models can execute bounded extraction tasks without improvising architecture.

## Target Module Map

### Host / RPC

- `src/copenet/host/ws_server.py`
  - websocket transport
  - connect challenge / auth gate
  - task cleanup
- `src/copenet/host/rpc_dispatch.py`
  - method routing only
- `src/copenet/host/rpc_chat.py`
  - `chat.send`
  - `chat.abort`
  - `chat.history`
- `src/copenet/host/rpc_catalog.py`
  - `prompts.list`
  - `providers.list`
  - `models.list`
  - `tools.list`
- `src/copenet/host/rpc_sessions.py`
  - `sessions.list`
  - `sessions.create`
  - `sessions.rename`
  - `sessions.archive`
  - `sessions.resolve`

### Tools

- `src/copenet/tools/__init__.py`
  - compatibility re-exports
- `src/copenet/tools/contracts.py`
  - tool types and parsing helpers
- `src/copenet/tools/policy.py`
  - `ToolPolicy`
- `src/copenet/tools/registry.py`
  - `ToolRegistry`
- `src/copenet/tools/builtin_readonly.py`
  - built-in read/search tool implementations

### Orchestrator

- `src/copenet/orchestrator.py`
  - public facade
  - construction
  - stable public method surface
- `src/copenet/orchestrator_runtime.py`
  - `send_chat` run lifecycle
- `src/copenet/orchestrator_catalog.py`
  - provider/model/tool/session catalog helpers
  - session payload shaping
- `src/copenet/orchestrator_titles.py`
  - async title generation helpers

## Invariants

These must not change during the extraction phase:

- WebSocket RPC method names and payload shapes
- connect challenge flow
- `GatewayClient` behavior
- session lock semantics
- transcript append-only behavior
- tool descriptor shape from `tools.list`
- provider contracts: `describe()`, `list_models()`, `run()`
- current tool ids and safety behavior
- tool trace UI event metadata shape
- tracing event names and general ordering

## Forbidden Cross-File Edits Per Task

### Task 1: `ws_server` extraction

Allowed:
- `src/copenet/host/*`

Forbidden:
- `src/copenet/orchestrator.py`
- `src/copenet/orchestrator_*.py`
- `src/copenet/tools*`
- `src/copenet/host/static/*`

### Task 2: tool extraction

Allowed:
- `src/copenet/tools*`

Forbidden:
- session store changes
- provider behavior changes
- UI changes

### Task 3: orchestrator catalog extraction

Allowed:
- `src/copenet/orchestrator.py`
- `src/copenet/orchestrator_catalog.py`

Forbidden:
- session-store semantic changes
- RPC payload changes

### Task 4: orchestrator runtime extraction

Allowed:
- `src/copenet/orchestrator.py`
- `src/copenet/orchestrator_runtime.py`
- `src/copenet/orchestrator_titles.py`

Forbidden:
- event payload changes
- transcript schema changes
- provider capability changes

## Required Checks Per Slice

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `node --check src/copenet/host/static/app.js`
- `uv run cope`

Manual smoke after the touched slice:

- connect handshake succeeds
- `sessions.list` works
- `providers.list` works
- `models.list` works
- `tools.list` works
- draft session creation still works
- first message still locks provider/model/profile/task mode
- Codex tool trace still attaches when a tool-backed run happens
- `COPNET_TRACE=1` still writes one run file

## Future Frontend Seams

Frontend modularization is deferred, but the intended seams are:

- websocket client / RPC layer
- session state store
- session list renderer
- message renderer
- markdown + math + tool trace renderer
- draft header controls

Do not split `app.js` during the current backend-first phase unless explicitly requested.
