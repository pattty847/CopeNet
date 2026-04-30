# CopeNet Contributor Guide

This document is the shared working agreement for human contributors and coding agents in this repo. Read it before touching a subsystem that affects sessions, providers, prompts, or the UI.

## What CopeNet Is

CopeNet is a local agent gateway. It provides:

- a FastAPI + WebSocket host
- pluggable provider adapters for Codex CLI, LM Studio, and Ollama
- persisted session and transcript storage
- a React operator workspace UI with a Home dashboard and agent console
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
| Orchestrator | `src/copenet/core/orchestrator/` | Coordinates sessions, transcripts, provider execution, run lifecycle |
| Harness | `src/copenet/core/harness/` | Normalizes model capabilities and turn execution |
| Tracing | `src/copenet/core/tracing/` | Per-run JSONL trace writer |
| Sessions | `src/copenet/core/sessions/` | Session index and transcript persistence |
| Tools | `src/copenet/core/tools/` | Tool contracts, policy, registry, and built-in handlers |
| Providers | `src/copenet/providers/` | Codex CLI and local HTTP provider adapters |
| Prompts | `src/copenet/prompts/` | Profile and task-mode loaders plus prompt content |
| Client | `src/copenet/client.py` | Programmatic gateway client |
| Web UI | `src/copenet/host/frontend/` | React + Vite workspace app served by the host when built |
| Legacy UI | `src/copenet/host/static/` | Old vanilla fallback UI kept for compatibility |

The `src/copenet/core/` package owns all business logic and run lifecycle. Transport, hosting, and provider adapters stay outside it.

Old top-level shims (`orchestrator.py`, `harness.py`, `tracing.py`, `sessions/`, `tools/`) re-export from `core/` for backward compatibility.

See [docs/architecture.md](docs/architecture.md) for the current request flow.

## Architectural Principles

**Thin providers.** Providers should translate runtime-specific APIs into shared provider events and model metadata. Session policy, prompt composition, and run lifecycle belong elsewhere.

**Harness before specialization.** Shared capability reasoning should live in the harness layer, not be copied into each provider or the UI.

**Append-only transcripts.** Transcript history is durable by design. Do not add mutation paths for stored messages.

**Atomic session writes.** `SessionStore` must keep the temp-file + rename pattern for index updates.

**Session identity is sacred.** Once a session is used, do not silently mutate its provider/model/profile/task binding.

**UI stays honest.** The frontend now uses React + Vite, but should still stay straightforward, typed, and product-driven. Avoid unnecessary abstractions, state sprawl, or design churn without a clear product reason.

## Coding Style

- Match the existing file style before introducing new patterns.
- Prefer focused edits over broad refactors.
- Keep helpers small and justified.
- Make errors actionable.
- Do not add speculative abstraction for features we have not chosen yet.

## Coding Standards For Searchability

CopeNet code should be easy for humans and agents to navigate with `rg` before any heavier tooling is involved. Optimize for clear, stable, grepable code over clever indirection.

### Naming

- Use one canonical term per product concept and keep it consistent across layers.
- Prefer explicit domain names like `session`, `provider`, `task_mode`, `tool_execution`, and `run_id` over local synonyms.
- Name handlers and actions by domain plus verb, e.g. `handle_chat_send`, `archive_session`, `list_models`.
- Prefer full words over abbreviations unless the abbreviation is already standard in the codebase.
- Keep important RPC methods, event names, and tool identifiers stable and obvious.

### Structure

- Keep one subsystem concern per directory and one primary responsibility per file.
- Put similar logic in predictable places every time so searches land in the expected layer.
- Avoid generic dumping-ground modules like broad `utils` files when a domain-specific home exists.
- Extract registration or mapping tables into obvious named modules when they are part of how the product is wired together.

### Data Shapes And Interfaces

- Preserve the same field names across boundaries unless there is a clear normalization reason to rename them.
- Prefer small typed DTOs or named payload models over ad-hoc dicts with shifting keys.
- Make important persisted and streamed fields easy to trace end-to-end through search.
- Centralize canonical event and method names instead of rebuilding them dynamically.

### Control Flow

- Prefer explicit dispatch tables and named handlers over hidden registration magic.
- Make entrypoints easy to locate by name in transport, orchestrator, and UI layers.
- Keep side effects close to clearly named functions rather than burying them in generic helpers.
- Use indirection only when it buys clear reuse or product clarity, not just abstraction for its own sake.

### Comments, Docs, And Tests

- Use the same domain vocabulary in comments, docs, and tests that the code uses.
- Write test names so they describe product behavior in searchable language.
- Keep architecture docs aligned with real code names so search results reinforce each other.
- Add short intent comments only where they improve navigation or explain a non-obvious boundary.

### Avoid

- Renaming the same concept in each layer without a strong reason.
- Overly generic helper names like `process`, `handle`, `manager`, or `data` without domain context.
- Dynamic string construction for important identifiers when a stable constant or literal would be clearer.
- Large files with unrelated responsibilities that make search results noisy and misleading.
- Metaprogramming or registration patterns that make definitions and call paths hard to find.

## Extraction-Before-Expansion Rule

Before adding new logic to an existing file, check whether the file is already over threshold:

- Python modules: ~400 lines soft threshold
- JavaScript modules: ~350 lines soft threshold
- More than 3 distinct responsibilities in one file → extract by concern first

If a file is over threshold, extract a focused sub-module before expanding it. Prefer small, single-responsibility files over growing an existing one.

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

- The primary frontend lives in `src/copenet/host/frontend/`.
- The app now has a product shell with sections:
  - `Home`
  - `Agents`
  - `Workflows`
  - `Data & Tools`
  - `Observability`
  - `Experiments`
- `Agents` owns the live session console and must preserve:
  - client-side draft sessions before first send
  - first-send runtime lock
  - inline `toolExecution` rendering
  - archive/restore
  - right-panel runtime + tool telemetry
- Real backend wiring is still concentrated in `Agents`; the other sections are intentional direction-setting shells for now.
- Global app state lives in `src/copenet/host/frontend/src/store/useAppStore.ts`. Keep it explicit and small.
- If a feature needs backend support, add and verify the RPC first.
- Make session state obvious: active section, active session, provider, model, profile, task mode, lock state, and connection state.
- Treat the legacy UI in `src/copenet/host/static/` as fallback compatibility code, not the primary product surface.

## Safe Collaboration Rules

1. Read the file you are changing first.
2. Prefer one subsystem per change when possible.
3. Do not revert unrelated user edits.
4. Do not swallow provider or storage errors silently.
5. Verify protocol changes against both UI and client expectations.
6. If you touch session semantics, check the whole flow: create, send, list, resolve, archive, history.

## Parallel Review

CopeNet contributors should actively use parallel review capacity when it helps de-risk a change or speed up investigation.

- Assume the team has access to two additional AI reviewers beyond the current coding agent.
- Use those extra reviewers for fresh eyes on traces, provider behavior, UI/UX flows, or patch plans when the problem feels ambiguous or suspicious.
- Treat outside-model reviews as advisory, not authoritative. Always verify claims against CopeNet code, traces, and runtime behavior before acting.
- Prefer giving parallel reviewers tightly scoped questions, concrete file paths, and exact run bundle directories instead of broad “figure it out” prompts.
- Record useful findings from outside reviewers in repo docs or investigation notes so the team can build on them rather than re-discovering them.

## Verification Expectations

There is not a deep automated suite yet, so manual and targeted verification matter.

Common checks:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `npm run lint` in `src/copenet/host/frontend`
- `npm run build` in `src/copenet/host/frontend`
- `uv run copenet`
- browser validation of the affected session/runtime flow

For current integration coverage, also know about:

- `uv run --extra dev pytest -q`
- `tests/integration/test_tool_prompt_matrix.py` — deterministic fake-provider prompt/tool-loop matrix
- `scripts/live_probe_matrix.py` — nondeterministic live provider/model probe runner for real runtimes

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

For live runtime flake triage:

- use `scripts/live_probe_matrix.py --provider <provider> --model <model>` to probe one real provider/model pair at a time
- prefer fresh sessions for baseline probes and one deliberate same-session repeat to expose resume drift
- compare live probe outcomes against the deterministic fake-provider matrix before blaming the harness

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
