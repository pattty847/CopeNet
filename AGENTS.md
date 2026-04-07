# CopeNet Contributor Guide

This document is the shared working agreement for human contributors and coding agents in this repo. Read it before touching a subsystem that affects sessions, providers, prompts, or the UI.

## What CopeNet Is

CopeNet is a local agent gateway. It provides:

- a FastAPI + WebSocket host
- pluggable provider adapters for Codex CLI, LM Studio, and Ollama
- persisted session and transcript storage
- a browser UI for locked chat sessions
- a CopeNet-native harness layer that normalizes provider execution and future tool capability work

The current product direction is:

- sessions lock to provider, model, profile, and task mode after the first send
- local runtimes should feel plug-and-play
- prompt behavior should be layered but simple
- harness/tooling should stay provider-agnostic

## Major Subsystems

| Subsystem | Location | Role |
|---|---|---|
| Host / RPC | `src/copenet/host/` | FastAPI app, WebSocket server, frame protocol, static UI |
| Orchestrator | `src/copenet/orchestrator.py` | Coordinates sessions, transcripts, provider execution, run lifecycle |
| Harness | `src/copenet/harness.py` | Normalizes model capabilities and turn execution |
| Providers | `src/copenet/providers/` | Codex CLI and local HTTP provider adapters |
| Sessions | `src/copenet/sessions/` | Session index and transcript persistence |
| Prompts | `src/copenet/prompts/` | Profile and task-mode loaders plus prompt content |
| Client | `src/copenet/client.py` | Programmatic gateway client |
| Web UI | `src/copenet/host/static/` | Vanilla HTML/JS/CSS app with no build step |

See [docs/architecture.md](/Users/copeharder/Programming/CopeNet/docs/architecture.md) for the current request flow.

## Architectural Principles

**Thin providers.** Providers should translate runtime-specific APIs into shared provider events and model metadata. Session policy, prompt composition, and run lifecycle belong elsewhere.

**Harness before specialization.** Shared capability reasoning should live in the harness layer, not be copied into each provider or the UI.

**Append-only transcripts.** Transcript history is durable by design. Do not add mutation paths for stored messages.

**Atomic session writes.** `SessionStore` must keep the temp-file + rename pattern for index updates.

**Session identity is sacred.** Once a session is used, do not silently mutate its provider/model/profile/task binding.

**UI stays simple.** The frontend is intentionally framework-free. Avoid adding build steps, bundlers, or heavy abstractions unless there is a strong product reason.

## Coding Style

- Match the existing file style before introducing new patterns.
- Prefer focused edits over broad refactors.
- Keep helpers small and justified.
- Make errors actionable.
- Do not add speculative abstraction for features we have not chosen yet.

## Data Flow and Validation Discipline

Keep runtime validation strict at trust boundaries and intentionally minimal everywhere else.

### Trust boundaries (validate here)

- WebSocket frame parsing and RPC request envelopes (`host/ws_server.py`, `host/rpc_schema.py`)
- External provider HTTP responses and runtime API payloads
- CLI/user input parsing
- Any raw payload entering CopeNet from outside the process

### Internal flows (trust contracts here)

- RPC layer → orchestrator → harness → providers
- normalized client RPC payloads after `_rpc()` return
- typed provider events and metadata (`ProviderEvent`, session/transcript models)

Inside these internal flows, do **not** add duplicate `isinstance`, `type(...)`, extra `None` guards, or repeated `str()/int()` coercion once data was already normalized upstream.

### Normalization rule

- Normalize once per flow at the boundary.
- Reuse that normalized shape downstream.
- If repeated guards appear, move validation earlier instead of re-checking in each layer.

### Function shape preferences

- Prefer short functions with early returns and low branching.
- Avoid nested ternaries deeper than one level.
- Prefer small typed DTOs (dataclass/Pydantic) between layers over ad-hoc dict shape checks.

## Session Semantics

This is the easiest place to create confusing regressions, so treat it carefully.

Rules:

- mutate session metadata only through `SessionStore`
- never write `index.json` directly
- never edit or delete stored transcript entries
- preserve `in_flight_run_id` locking
- preserve provider/model/profile/task-mode binding checks
- if you add a new session field, give old entries a safe fallback

For current behavior, assume:

- draft sessions are editable before first send
- after first send, the session is locked to provider, model, profile, and task mode
- renaming is allowed after lock
- changing runtime/model for an existing conversation should become a new chat or future branch flow, not an in-place mutation

## Working In Each Area

### Providers

- Implement provider-specific request/response translation only.
- Return rich model metadata when available.
- Keep runtime detection, model listing, and chat execution consistent with the shared provider contract.
- Do not leak LM Studio or Ollama quirks into the orchestrator unless absolutely required.

### Prompts

- Profiles and task modes are authored as `.md` files under `src/copenet/prompts/presets/`.
- Composition logic belongs in `src/copenet/prompts/loader.py`.
- Avoid turning prompt authoring into a config DSL.
- Keep prompts readable and editable by humans first.

### Harness

- Add shared capability logic here before touching providers or UI.
- Keep the abstractions practical.
- Do not commit to one vendor’s tool-calling shape as the system architecture.

### WebSocket / RPC

- Add RPC methods in `ws_server.py`.
- Keep streaming events and request/response frames clearly separated.
- Prefer extending response payloads over changing existing field meaning.
- Be careful with client compatibility because the browser UI and `GatewayClient` both depend on this layer.

### Web UI

- Keep `app.js` plain browser JavaScript.
- Preserve the single-page, no-build workflow.
- If a feature needs backend support, add and verify the RPC first.
- Make session state obvious: active session, provider, model, profile, task mode, lock state.

## Safe Collaboration Rules

1. Read the file you are changing first.
2. Prefer one subsystem per change when possible.
3. Do not revert unrelated user edits.
4. Do not swallow provider or storage errors silently.
5. Verify protocol changes against both UI and client expectations.
6. If you touch session semantics, check the whole flow: create, send, list, resolve, archive, history.

## Verification Expectations

There is not a deep automated suite yet, so manual and targeted verification matter.

Common checks:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `node --check src/copenet/host/static/app.js`
- `uv run cope`
- browser validation of the affected session/runtime flow

### Tracing

When `COPNET_TRACE=1` is enabled, CopeNet writes one JSONL trace per run to `~/.copenet/logs/runs/<run-id>.jsonl`.

Full event reference: [docs/TRACING.md](docs/TRACING.md)
Debugging runbook: [docs/DEBUGGING.md](docs/DEBUGGING.md)
Known gaps and past findings: [docs/TRACE-FINDINGS.md](docs/TRACE-FINDINGS.md)

**Triage order for a bad run:**

1. Check `harness_planned` — was `willAttemptToolLoop` correct? Was `promptedToolUse: true`?
2. Check `tool_requested` — did the model invoke the expected tool with correct arguments?
3. Check `tool_executed` or `tool_blocked` — was this a policy rejection or a real failure?
4. Check `assistant_finalized` — was `toolExecutionAttached` as expected?
5. Check `run_failed` — the `error` field is the primary diagnostic.

**No trace file?** The provider failed to initialize before the run started. Check provider availability via `providers.list` or startup logs.

**Tool loop not triggering despite available tools?** Check `harness_planned.capabilityProfile.promptedToolUse`. This is the gate, not `availableToolIds`.

Use traces to explain behavior differences, policy rejections, and provider/tool mismatches before proposing architectural changes.

When adding tests:

- test storage against real temp directories
- mock only true I/O boundaries
- prefer orchestrator-level verification over UI-mocking when feasible

## When To Add Docs Vs Code

| Situation | Preferred action |
|---|---|
| New reusable behavior preset | Add prompt markdown |
| New runtime/provider | Add provider code |
| Shared capability routing | Extend harness |
| Session/routing product rule | Code plus brief doc update |
| Contributor workflow guidance | Update this file |

## Default Mindset

Build the smallest thing that keeps product semantics clear. Favor trustworthy session behavior, transparent UI state, and straightforward architecture over cleverness.
