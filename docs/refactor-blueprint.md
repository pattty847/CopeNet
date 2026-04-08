# CopeNet Architecture Consolidation Blueprint

This blueprint defines the next phase after proof-of-concept: consolidate architecture so future work lands in small, predictable modules instead of expanding existing "god files".

It is intentionally implementation-oriented so humans and coding agents can execute work in bounded slices with clear ownership.

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

- `src/copenet/host/static/app.js` is currently >1,100 lines and mixes state, RPC, rendering, and controllers.
- Runtime orchestration concerns remain spread across `orchestrator.py`, `orchestrator_runtime.py`, and adjacent modules with room for cleaner conceptual ownership.
- Tool and capability code paths are functional but should become easier to reason about and extend.
- Contributor standards describe intent, but need sharper enforcement language for data-flow-first coding.

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
├── providers/
│   ├── base.py
│   ├── codex_cli.py
│   └── local_http.py
├── prompts/
├── client.py
└── runner/
```

### Boundary Intent

- `core/`: business logic and run lifecycle (no transport/UI concerns).
- `host/`: transport, RPC envelope parsing, websocket lifecycle, static hosting.
- `providers/`: provider-specific translation and runtime interaction only.
- `prompts/`: prompt composition and preset authoring.
- `client.py`: stable remote interface for external callers.

## Frontend ES Module Strategy (No Build Step)

### Target split

- `static/app.js` — bootstrap only
- `static/js/state.js` — session/draft/catalog state container
- `static/js/rpc.js` — websocket and request/response helpers
- `static/js/render/messages.js` — markdown/math/tool-trace rendering
- `static/js/render/sessions.js` — session list rendering
- `static/js/render/header.js` — active session + draft header state
- `static/js/controllers/chat.js` — send/receive/stream lifecycle
- `static/js/controllers/sessions.js` — create/select/rename/archive flows

### Constraints

- Preserve behavior and event semantics exactly during extraction.
- Keep exports small and explicit (no global mutable singleton sprawl).
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

- avoid repeated `isinstance`/shape checks in internal hops;
- avoid redundant `str()/int()/bool()` coercions downstream;
- prefer typed DTO/dataclass contracts between modules.

### Guard rule

Before adding a defensive guard, ask:

1. What real external boundary can violate this value?
2. Can we normalize earlier instead?
3. If not, is this guard actionable and observable?

If the answer to (1) is "none", do not add the guard in internal flow.

## No-God-File Thresholds and Extraction Rules

Use these thresholds as prompts for extraction (not hard failures):

- JavaScript UI modules: ~350 lines soft threshold.
- Python service modules: ~400 lines soft threshold.
- More than 3 distinct responsibilities in one file => extract by concern.
- Repeated condition clusters across call sites => extract normalization helper at boundary.

Extraction principles:

- preserve public behavior first;
- avoid broad renames and call-site churn in a single pass;
- use compatibility re-exports/shims when moving Python modules.

## Execution Plan

### Pass 1 — Architecture Blueprint Lock

Deliverables:

- this blueprint accepted as source of truth;
- module ownership table for core/host/providers/ui boundaries;
- extraction thresholds documented in contributor standards.

### Pass 2 — Frontend Split (Behavior-Preserving)

Deliverables:

- `app.js` reduced to bootstrap wiring;
- new `static/js/*` modules created per target split;
- no RPC payload or event contract changes.

Verification:

- `node --check` on all touched JS modules.
- manual smoke: connect, sessions list/create/select, first-send lock behavior, stream rendering, tool trace rendering.

### Pass 3 — Core Package Consolidation

Deliverables:

- move orchestration/harness/sessions/tools/tracing under `core/` (or equivalent clear structure);
- keep stable import surfaces via shims where needed;
- no session semantic regressions.

Verification:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `uv run cope` smoke run.

### Pass 4 — Standards and Worker Guidance

Deliverables:

- update `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` with:
  - data-flow-before-code rule,
  - boundary-validation rule,
  - extraction-before-expansion rule.

### Pass 5 — Post-Consolidation Feature Work

Only after architecture passes are stable:

- local model tool reliability tuning;
- tool mode/profile controls;
- Subtext bridge design exploration.

## Compatibility and Safety Invariants

Must remain stable across all passes:

- RPC method names and payload semantics.
- session lock semantics after first send.
- append-only transcript behavior.
- in-flight run locking semantics.
- tool descriptor and tool-trace payload shape consumed by UI.
- provider interface behavior (`describe`, `list_models`, `run`).

## Suggested Worker Slice Template

For each extraction task, require workers to include:

1. Scope and explicit non-scope.
2. Files touched.
3. Behavior invariants checked.
4. Commands run.
5. Follow-up extraction opportunities (optional, max 3).

## Definition of Done for Consolidation Phase

Consolidation is complete when:

- frontend responsibilities are modularized with no build step;
- backend package boundaries are clearer and navigable;
- contributor standards consistently enforce boundary validation discipline;
- adding a feature no longer implies touching a single oversized orchestration/UI file.
