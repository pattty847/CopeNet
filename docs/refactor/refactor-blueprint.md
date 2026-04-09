# CopeNet Architecture Consolidation Blueprint

This blueprint is the source of truth for the refactor phase. It now lives under `docs/refactor/` so the active plan and the remaining cleanup list stay together.

## Status Snapshot

- Completed: frontend ES-module split, core package consolidation, and contributor-standard updates.
- Partial: boundary cleanup and naming normalization.
- Remaining: cleanup passes that remove legacy compatibility debt and finish the no-back-compat simplification.

## Accomplishments So Far

- `src/copenet/host/static/app.js` is now a bootstrap entry point and the UI is split across `static/js/controllers/`, `static/js/render/`, `static/js/rpc.js`, and `static/js/state.js`.
- Core runtime modules now live under `src/copenet/core/` for orchestrator, harness, sessions, tools, and tracing.
- Compatibility shims exist for old import paths, which kept the consolidation move mechanical.
- Contributor guidance was tightened in `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` around trust boundaries, normalized internal flows, and extraction discipline.

## Goals

- Keep product behavior stable while improving maintainability.
- Make responsibility boundaries obvious across core runtime, host transport, providers, and UI.
- Preserve no-build frontend simplicity while splitting `app.js` into browser-native ES modules.
- Codify validation discipline: strict at trust boundaries, minimal in normalized internal flows.
- Add extraction thresholds so large files are split before they become bottlenecks.

## Non-Goals

- No framework migration for the web UI.
- No bundler/build-step introduction in this phase.
- No behavior redesign of session locking, transcript semantics, or RPC contract.
- No broad provider contract rewrite.

## Current Pressure Points

- Naming and normalization are still spread across the RPC layer, storage deserialization, and client helpers instead of one clear boundary codec.
- Legacy compatibility shims and duplicate tool implementations remain even though the repo direction is now toward dropping backward compatibility.
- `src/copenet/core/tools/builtin_readonly.py` is still oversized and mixes several unrelated handlers.
- `src/copenet/host/static/js/state.js` still owns DOM references and a browser-side dev token.
- Several frontend paths still swallow errors with `catch (_) {}`.
- There is still no real automated test suite.

## Target Package Shape

Keep boundaries under `src/copenet/` to preserve package coherence and avoid root-level fragmentation.

```text
src/copenet/
├── core/
│   ├── orchestrator/
│   ├── harness/
│   ├── sessions/
│   ├── tools/
│   └── tracing/
├── host/
│   ├── api.py
│   ├── ws_server.py
│   ├── rpc_*.py
│   └── static/
│       ├── js/
│       │   ├── controllers/
│       │   └── render/
│       └── app.js
├── providers/
│   ├── base.py
│   ├── codex_cli.py
│   └── local_http.py
├── prompts/
├── client.py
└── runner/
```

### Boundary Intent

- `core/`: business logic and run lifecycle.
- `host/`: transport, RPC envelope parsing, websocket lifecycle, static hosting.
- `providers/`: provider-specific translation and runtime interaction only.
- `prompts/`: prompt composition and preset authoring.
- `client.py`: stable remote interface for external callers.
- `runner/`: CLI entry points and execution orchestration.

## Frontend ES Module Strategy

### Target split

- `static/app.js` — bootstrap only
- `static/js/state.js` — shared state only, not long-term DOM ownership
- `static/js/rpc.js` — websocket and request/response helpers
- `static/js/render/messages.js` — markdown/math/tool-trace rendering
- `static/js/render/sessions.js` — session list rendering
- `static/js/render/header.js` — active session + draft header state
- `static/js/controllers/chat.js` — send/receive/stream lifecycle
- `static/js/controllers/sessions.js` — create/select/rename/archive flows

### Constraints

- Preserve behavior and event semantics exactly during extraction.
- Keep exports small and explicit.
- Keep DOM query ownership localized to rendering/controller modules.
- Keep protocol types centralized near RPC helpers.

## Validation and Type Discipline

### Validate at trust boundaries

- WebSocket frame parsing and RPC envelopes.
- Provider HTTP/CLI responses.
- User-submitted payloads and CLI args.
- Transcript/session payloads loaded from storage.

### Trust normalized internal contracts

Once data is normalized at the boundary:

- avoid repeated `isinstance` and shape checks in internal hops;
- avoid redundant `str()`, `int()`, or `bool()` coercions downstream;
- prefer typed DTO and dataclass contracts between modules.

### Naming standard

Use one protocol standard without fighting each language:

- Python code: `snake_case`
- JavaScript code: `camelCase`
- RPC and browser payloads: `camelCase`
- Storage and disk models: `snake_case`
- Conversion boundary: host RPC layer and explicit serialization helpers only

## No-God-File Thresholds and Extraction Rules

Use these thresholds as prompts for extraction:

- JavaScript UI modules: about 350 lines
- Python service modules: about 400 lines
- More than 3 distinct responsibilities in one file means split by concern
- Repeated condition clusters across call sites mean move normalization earlier

Extraction principles:

- preserve public behavior first;
- avoid broad renames and call-site churn in a single pass;
- remove compatibility layers once the repo no longer wants backward compatibility.

## Execution Plan

### Pass 1 — Blueprint Lock And Boundary Cleanup

Status: Partial

- [x] Blueprint accepted as the refactor source of truth
- [x] Module ownership clarified across `core/`, `host/`, `providers/`, and UI
- [x] Extraction thresholds documented in contributor guidance
- [ ] Centralize wire-to-Python normalization at the RPC boundary
- [ ] Remove repeated downstream coercion in `client.py`, RPC handlers, and storage helpers
- [ ] Make provider capability metadata less loose and less defensive downstream

Verification:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `uv run cope`
- smoke the Python client methods that wrap `providers.list`, `models.list`, `sessions.list`, `tools.list`, and `chat.history`

### Pass 2 — Frontend Split

Status: Completed

- [x] `app.js` reduced to bootstrap wiring
- [x] `static/js/*` modules created for controllers, renderers, RPC, and shared state
- [x] No intended RPC method rename as part of the split
- [ ] Follow-up cleanup: move DOM element ownership out of `state.js`
- [ ] Follow-up cleanup: replace swallowed browser-side exceptions with observable handling

Verification:

- `node --check src/copenet/host/static/app.js`
- `node --check $(rg --files src/copenet/host/static/js -g '*.js')`
- manual smoke: connect, sessions list/create/select, first-send lock behavior, stream rendering, tool trace rendering

### Pass 3 — Backend Boundary Cleanup

Status: Not complete

- [ ] Finish storage normalization cleanup in `SessionIndexEntry.from_json()`
- [ ] Tighten client `_rpc()` so downstream wrappers can trust the payload shape
- [ ] Reduce repeated field coercion in `host/rpc_chat.py`
- [ ] Make provider metadata and orchestrator wiring easier to test and reason about

Verification:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `uv run cope`
- trace-enabled smoke for one Codex or local-model tool run

### Pass 4 — Core Package Consolidation

Status: Completed

- [x] Orchestration, harness, sessions, tools, and tracing moved under `core/`
- [x] Stable import surfaces preserved during the move
- [x] Frontend split and backend move landed without introducing a build step
- [ ] Follow-up cleanup: delete obsolete shims and duplicate legacy tool implementations once imports are updated

Verification:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `uv run cope`

### Pass 5 — Standards And Worker Guidance

Status: Completed

- [x] `AGENTS.md` updated
- [x] `CLAUDE.md` updated
- [x] `GEMINI.md` updated
- [x] Boundary-validation and extraction rules documented

### Pass 6 — Post-Consolidation Feature Work

Status: Not started

- [ ] Local model tool reliability tuning
- [ ] Tool mode and profile controls
- [ ] Subtext bridge design exploration

## Compatibility and Safety Invariants

Must remain stable across all passes:

- RPC method names and payload semantics
- session lock semantics after first send
- append-only transcript behavior
- in-flight run locking semantics
- tool descriptor and tool-trace payload shape consumed by UI
- provider interface behavior (`describe`, `list_models`, `run`)
- current prompted local-model tool loop semantics unless explicitly being tuned in a post-consolidation feature pass

## Definition of Done for Consolidation Phase

Consolidation is complete when:

- frontend responsibilities are modularized with no build step;
- backend package boundaries are clearer and navigable;
- contributor standards consistently enforce boundary validation discipline;
- naming conversion happens at one explicit boundary instead of being reimplemented in multiple layers;
- legacy compatibility shims and duplicate pre-core implementations are removed;
- adding a feature no longer implies touching a single oversized orchestration or UI file.
