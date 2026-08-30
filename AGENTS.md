# CopeNet Contributor Guide

This document is the shared working agreement for human contributors and coding agents in this repo. Read it before touching a subsystem that affects sessions, providers, prompts, or the UI.

## What CopeNet Is

CopeNet is an agent harness. It provides:

- a FastAPI + WebSocket host (with a secondary REST + SSE `/api/v1` lane for external apps)
- pluggable provider adapters for Claude CLI, OpenAI Codex (OAuth), LM Studio, and Ollama
- persisted session and transcript storage, plus per-run records and per-session artifacts
- operator-side stores for Pulse, memory, messaging routes, profile, and external-app credentials
- a React operator workspace UI with a Home dashboard and agent console
- a CopeNet-native harness layer that normalizes provider execution and tool capability work

The current product direction is:

- sessions lock provider/profile/persona/workspace after first send; the operator may
  change model within that provider and may change Access
- local runtimes should feel plug-and-play
- prompt behavior should be layered but simple
- harness/tooling should stay provider-agnostic

## Major Subsystems

| Subsystem      | Location                                     | Role |
|----------------|----------------------------------------------|------|
| Host / RPC     | `src/copenet/host/`                          | FastAPI app, `/ws` JSON-RPC, `/api/v1` REST+SSE, static UI mounting |
| Orchestrator   | `src/copenet/core/orchestrator/`             | Coordinates sessions, transcripts, provider execution, run lifecycle, merges, pulse, messaging |
| Harness        | `src/copenet/core/harness/`                  | Capability profiles, turn planning, tool loops (native Responses / Chat Completions / prompted), `responses_items` replay shapes. See `docs/plans/HARNESS_REBUILD_V2.md` for the current architecture. |
| Sessions       | `src/copenet/core/sessions/`                 | Session index, transcript store, structured session state |
| Runtime        | `src/copenet/core/runtime/`                  | RunStore (durable run records), ArtifactStore, per-turn state |
| Tools          | `src/copenet/core/tools/`                    | Tool contracts, policy (`policy_for_task_mode`), registry, built-in handlers |
| Tracing        | `src/copenet/core/tracing/`                  | Per-run JSONL trace writer |
| Coordination   | `src/copenet/core/coordination/`             | Shared provider-lane execution primitive |
| Fleet          | `src/copenet/core/fleet/`                    | Durable multi-provider rooms and attributed lane events |
| Market Monitor | `src/copenet/core/market/`                   | Slow-timeframe market radar: yfinance price signals, CopeTech-Edgar fundamentals/insider evidence, model reads, portfolio backtesting/scenario simulation. See "Market Monitor" under Working In Each Area. |
| Research Lab   | `src/copenet/core/research_lab/`             | Evidence snapshots, benchmark calculations, and durable research dossiers |
| Movie Lab      | `src/copenet/core/movies/`                   | Spreadsheet import, TMDB enrichment, analysis, and recommendations |
| NASA           | `src/copenet/core/nasa/`                     | APOD persistence, fetching, and wallpaper support |
| Profile        | `src/copenet/core/profile/`                  | Pat Profile loader, changelog, return-briefing builder |
| Memory         | `src/copenet/core/memory/`                   | User-visible memory items (preferences, conventions, facts) |
| Pulse          | `src/copenet/core/pulse/`                    | Inbox pulse store |
| Messaging      | `src/copenet/core/messaging/`                | Messaging config + Telegram chat→session route store |
| Media          | `src/copenet/core/media/`                    | URL/audio ingestion + transcription + asset store |
| Web ingest     | `src/copenet/core/web_ingest.py`             | Web URL ingestion service |
| Knowledge runtime | `src/copenet/core/knowledge_runtime.py` + `meme_*.py` | Meme Lab knowledge runtime + ideation API |
| External apps  | `src/copenet/core/apps/`                     | Bearer-token registry for `/api/v1` consumers |
| Provider auth  | `src/copenet/core/provider_auth/`            | Provider-owned auth state (e.g. OpenAI Codex OAuth) |
| Providers      | `src/copenet/providers/`                     | Adapters: `codex-cli`, `claude-cli`, `openai-codex`, `lm-studio`, `ollama` |
| CLI runner     | `src/copenet/runner/cli_runner.py`           | Shared CLI subprocess runner used by Codex/Claude CLI providers |
| Prompts        | `src/copenet/prompts/`                       | Profile + Access-overlay loaders, optimizer, preset markdown |
| Client         | `src/copenet/client.py`                      | Programmatic GatewayClient |
| Web UI         | `src/copenet/host/frontend/`                 | React + Vite workspace app (primary surface) |
| Browser agent  | `src/copenet/browser_agent/`                 | Playwright-backed deterministic browser-control prototype (separate CLI lane) |
| Probes         | `src/copenet/probes/`                        | Runtime probe payload helper for `scripts/live_probe_matrix.py` |

The `src/copenet/core/` package owns all business logic and run lifecycle. Transport, hosting, and provider adapters stay outside it.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the current request flow.

## Architectural Principles

**Thin providers.** Providers should translate runtime-specific APIs into shared provider events and model metadata. Session policy, prompt composition, and run lifecycle belong elsewhere.

**Harness before specialization.** Shared capability reasoning should live in the harness layer, not be copied into each provider or the UI.

**Append-only transcripts.** Transcript history is durable by design. Do not add mutation paths for stored messages.

**Atomic session writes.** `SessionStore` must keep the temp-file + rename pattern for index updates.

**Session identity is sacred.** Once a session is used, never silently mutate its binding — provider/profile/persona/workspace lock after first send, and model/Access change only via an explicit operator-driven request. Full rules and current state: see Session Semantics below.

**UI stays honest.** The frontend now uses React + Vite, but should still stay straightforward, typed, and product-driven. Avoid unnecessary abstractions, state sprawl, or design churn without a clear product reason.

## No Back-Compat By Default

When we change course, **change it all the way**. Do not leave the old path working "just in case" unless the operator explicitly asks for a migration window.

Compatibility shims are how this codebase drifts: the old name survives beside the new one, a later contributor reads the old one and assumes it is current, and the two meanings diverge silently. A concrete case — the frontend guessed preview shapes from field names because the backend never declared a `type`. Everything rendered, so nothing looked broken, and the real contract was never written down. Three tools depended on a guess for months.

Rules:

- Rename in place; do not alias. One canonical name per concept, everywhere, in the same commit.
- Delete the superseded module, field, or branch in the commit that replaces it, and say so in the message.
- No `legacy_*` / `*_v2` / `*_old` pairs, no "deprecated but still supported" fields, no dual-read code paths.
- If a shim is genuinely unavoidable (persisted data written by an older build), it is a **migration** — write it as one, note the removal date or condition, and never let it become the permanent read path.
- When you find an existing shim while working nearby, report it rather than extending it. Removal is its own commit.

## Coding Style & Standards

Match the existing file style before introducing new patterns; prefer focused edits over broad refactors. Keep helpers small and justified, errors actionable, and skip speculative abstraction for features not yet chosen. Optimize for clear, stable, `rg`-grepable code over clever indirection — humans and agents both navigate this codebase by search first.

**Naming**

- One canonical term per product concept, consistent across every layer (`session`, `provider`, `task_mode`, `tool_execution`, `run_id`) — do not rename the same concept per layer without a strong reason.
- Name handlers and actions by domain plus verb (`handle_chat_send`, `archive_session`, `list_models`); avoid generic names like `process`, `handle`, `manager`, `data` with no domain context.
- Prefer full words over abbreviations unless already standard in the codebase. Keep RPC methods, event names, and tool identifiers stable and obvious.

**Structure**

- One subsystem concern per directory, one primary responsibility per file (see Extraction-Before-Expansion Rule below for size thresholds).
- Put similar logic in predictable places so searches land in the expected layer; avoid generic dumping-ground modules (broad `utils` files) when a domain-specific home exists.
- Extract registration/mapping tables into obviously named modules when they are part of how the product is wired together.

**Data shapes & control flow**

- Preserve field names across boundaries unless there's a clear normalization reason to rename; prefer small typed DTOs over ad-hoc dicts with shifting keys.
- Centralize canonical event/method names instead of rebuilding them dynamically — avoid dynamic string construction for important identifiers when a stable constant would do.
- Prefer explicit dispatch tables and named handlers over hidden registration magic or metaprogramming; keep entrypoints easy to locate by name in transport, orchestrator, and UI layers.
- Use indirection only when it buys clear reuse or product clarity, not abstraction for its own sake.

**Comments, docs, and tests**

- Use the same domain vocabulary in code, comments, docs, and tests so search results reinforce each other.
- Write test names in searchable, product-behavior language.
- Add short intent comments only where they explain a non-obvious boundary — not what the code already says.

## Extraction-Before-Expansion Rule

Before adding new logic to an existing file, check whether the file is already over threshold:

- Python modules: ~400 lines soft threshold
- JavaScript modules: ~350 lines soft threshold
- More than 3 distinct responsibilities in one file → extract by concern first

If a file is over threshold, extract a focused sub-module before expanding it. Prefer small, single-responsibility files over growing an existing one.

## Data Flow and Validation Discipline

Validate strictly at trust boundaries; trust the shape everywhere else. Once data is normalized upstream, do not add duplicate `isinstance`/`type(...)`/`None`-guard/`str()`-`int()` coercion downstream.

- **Validate here:** WebSocket frame parsing and RPC envelopes (`host/ws_server.py`, `host/rpc_schema.py`), external provider HTTP responses, CLI/user input, any raw payload entering the process.
- **Trust the contract here:** RPC → orchestrator → harness → providers; normalized `_rpc()` return payloads; typed provider events and session/transcript models.
- Normalize once per flow at the boundary and reuse that shape downstream. If repeated guards start appearing in internal flows, that's a signal to move validation earlier — not to add another guard.

## Session Semantics

This is the easiest place to create confusing regressions, so treat it carefully.

Rules:

- mutate session metadata only through `SessionStore`
- never write `index.json` directly
- never edit or delete stored transcript entries
- preserve `in_flight_run_id` locking
- preserve provider/profile/persona/workspace locks and explicit model/Access reconciliation
- if you add a new session field, give old entries a safe fallback

For current behavior, assume:

- draft sessions are editable before first send
- after first send, **provider, profile, persona, and workspace** stay locked; changing
  any of those is still a new-chat / future-branch flow, not an in-place mutation
- **model (same provider) and Access (task mode) are mutable mid-session** as of the
  Mid-session Runtime Mutability change (A + B1): `assert_session_binding` reconciles the
  stored binding to the requested model/Access instead of raising. Every run is stamped
  with the provider/model it used (transcript + run record), so switching stays auditable
  per-turn, and Full Access escalation is still provider-gated in `policy_for_task_mode`.
  Cross-provider switching (B2) and multi-model orchestration (B3) remain future work.
- renaming is allowed after lock

## Working In Each Area

### Providers

- Implement provider-specific request/response translation only.
- Return rich model metadata when available.
- Keep runtime detection, model listing, and chat execution consistent with the shared provider contract.
- Do not leak LM Studio or Ollama quirks into the orchestrator unless absolutely required.

### Prompts

- Profiles and Access overlays are authored as `.md` files under `src/copenet/prompts/presets/`.
- Composition logic belongs in `src/copenet/prompts/loader.py`.
- Avoid turning prompt authoring into a config DSL.
- Keep prompts readable and editable by humans first.

### Harness

- Add shared capability logic here before touching providers or UI.
- Keep the abstractions practical.
- Do not commit to one vendor’s tool-calling shape as the system architecture.
- Tool manifests expose exact registered tool ids plus category, schema, side-effect, confirmation, and evidence-role metadata. The model chooses exact ids; the harness validates structure and policy authority.
- `HarnessDecisionRecord` is trace-only in v1. The model may declare request kind, route, next action, evidence requirements, and `trace_note`, but production control flow must not branch on prose fields or keyword matching.

### Tools runtime

- Handlers live under `src/copenet/core/tools/handlers/`; `builtin_readonly.py` aggregates them (the filename is historical). `context.py` / `context.prepare` were retired in Phase 0.3. The model-facing surface is the explicit `MANIFEST_TOOL_IDS` set: core file/shell/plan/web tools plus approved Market, persona, memory, and user-note tools. Treat that set—not an old numeric count in documentation—as canonical. `files.list`/`files.search` were consolidated into `files.rg`; `artifact.create` remains registered but off-manifest.
- Categories: `repo-read`, `repo-write`, `shell-read`, `context`, `artifact`, `mcp`. Effective policy is **`policy_for_task_mode(session task_prompt_id)`**: baseline Access allows read/shell/context/artifact; **Full Access** (`full-access`) adds **`repo-write`** (`files.edit`, `files.write`) and unrestricted user-level `shell.exec`.
- Full-access shell commands run with the current OS user's permissions and may use normal shell syntax (`|`, `&&`, redirects, scripts, etc.). High-risk command patterns return `policyDecision: "approval_required"` instead of executing; wire operator confirmation before allowing those proposal records to resume.
- Permission claims should be tested with the direct matrix before trusting a live model's self-report: `uv run python scripts/permission_probe_matrix.py`. A model that only proves `pwd` works has proven shell-read, not full-access.
- **`artifact.create`** persists session artifacts when `artifact_store`, `session_key`, and `run_id` are present.

### WebSocket / RPC

- `ws_server.py` owns the WS connection/frame lifecycle; actual method routing is an `elif req.method == "..."` chain in `rpc_dispatch.py` — add new RPC methods there, not in `ws_server.py` directly.
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
  - right-panel runtime + tool telemetry (**Tool Activity proof** groups `SessionRunRecord.toolSteps` and run-scoped artifacts via `runtime/activityProof.ts` + `ToolActivityProof.tsx`)
  - one **grouped tool block per turn** (`components/transcript/TurnToolGroup.tsx`)
- **Previews declare their `type`; the client does not guess.** `_preview_payload` emits `file_read` (with `lines`, not `content`), `repo_search` (with `snippet`, not `text`), `raw`, `diff`, `plan`, `web_search`, `web_doc`. The normalizer used to infer `file_read` from `{path, content}` and `repo_search` from `{matches}`; that shim is gone, so an undeclared preview is genuinely raw. Add the `type` in the same commit as the projection.
- **A preview type with no renderer renders blank.** `_preview_payload` in `core/tools/contracts.py` hand-projects a per-tool preview; the frontend's `ToolResultPreview` union is the list of shapes that can actually be displayed. The five `market_*` types were emitted for months with no renderer, so every market tool call showed the call and no output. `tests/unit/test_preview_renderability.py` now fails on any orphan — ship the renderer with the projection, or omit the branch and let `_generic_preview` return a raw body. Also note a tool step may carry its preview on `effect.preview` rather than `preview`; normalize before branching.
- **Three levels in the thread, not two.** Group header (`TurnToolGroup`) → one row per action → the row expands **in place** into a `max-h-80` scroll box.
- **Expand answers "what did it return"; Inspect answers "what was this call".** Split by purpose, never by size — the drawer also holds arguments, policy decision, scope, evidence role, and the artifact, so it always needs a door. `Inspect call →` is present on every expanded row; only the label changes. When the body was clipped it reads `Showing 8 of 1823 matches · Inspect full output →` (`clipNotice` + `hasMoreThanShown`). Hiding the affordance when the output happened to fit was the earlier mistake: it left long-but-complete results with no way into the panel at all.
- **The drawer shows the artifact, not the preview.** When a tool step carries an `artifactId`, `ToolBody` loads that `tool_output` artifact — the whole body. Without it the panel is the same clipped preview at a larger size, which is what it used to be.
- **Thread detail lives in the overlay, never inline.** Every tool row and the per-turn internals row open `InspectorDrawer` (a portal overlay: 680px, own scroll, Escape) via `setInspectorTarget`. Nothing expands inside the transcript — tool output is routinely a whole file or a command dump, and rendering that between two chat messages is what made the thread unreadable. Do not add a new inline expander; add an `InspectorTarget` kind.
- **One derivation renders run internals everywhere.** `runtime/runInternals.ts` turns a `SessionRunRecord` plus its lifecycle trace into the stat line and the what-it-saw / what-it-did / why-it-stopped / raw-trace sections; `components/runtime/RunInternals.tsx` renders it in the drawer (`showDid={false}` — the thread already lists the calls) and in the Observability inspector (`showDid` default), with `internalsPalette.ts` selecting `operator-*` vs `shell-*` classes. Add to the derivation, not to a per-surface renderer. Three rules that are easy to break: a chat-only turn must keep its "Context it saw" row (that is the `promptedToolUse: false` case, where the question is asked most); grouping is by run, not adjacency, so narration between calls must not split a turn; and `inputTokenEstimate` counts **messages only** — never label it as everything the model saw.
- Run records for the thread come from `runtime/runIndex.ts` (one `sessions.runs` call per session, module-level promise cache); trace events load lazily on expand. Do not add a per-message fetch.
- Section status, verified 2026-08-01 — keep this current, because a stale entry here sends the next contributor to rebuild something that already ships:
  - **Live and load-bearing:** `Agents`, `Market`, `Observability` (run inspector over durable run records + `logs/runs/*.jsonl`, see `docs/plans/OBSERVABILITY.md`), `Home`.
  - **Still direction-setting shells:** `Workflows` and `Data & Tools` — neither issues a single RPC. `Experiments` is thin but wired.
- Global app state lives in `src/copenet/host/frontend/src/store/useAppStore.ts`. Keep it explicit and small.
- If a feature needs backend support, add and verify the RPC first.
- Make session state obvious: active section, active session, provider, model, profile, Access, lock state, and connection state.
- Prefer Browser Use against the Codex in-app browser for localhost UI verification when the plugin is available. Use it to reproduce interaction bugs, verify fixes, and catch runtime UI failures that lint/build will miss.
- For Codex specifically, treat `[@Browser](plugin://browser-use@openai-bundled)` as the canonical browser-validation path when the plugin is available. Read the Browser skill first, use the in-app browser workflow for localhost verification, and only fall back to Playwright or Computer Use if that path is genuinely unavailable. Claude and Gemini do not share this Codex-only browser surface, so do not assume they can follow the same workflow.
- When a UI pass materially improves the product surface, capture a fresh product screenshot right away, store it under `docs/imgs/`, and update the matching `README.md` section in the canonical GitHub repo (`github.com/pattty847/CopeNet`). Prefer Browser Use for the capture flow when available; otherwise use a trustworthy automated localhost fallback such as Playwright. `gh` is installed, so repo docs/screenshot refreshes should be treated as part of finishing polished UI work rather than a nice-to-have.
- **Before committing any README screenshot, check the frame for operator-specific data** — the Market Monitor "since you last looked" strip and daily-briefing header render a real portfolio dollar figure (`Book`/`Portfolio $…`), and the Agents Console Inspector's Destinations panel can show a real phone number or other personal identifier. Either crop those elements out, capture a clean state (empty portfolio / no destinations configured), or skip that panel and note in the PR/commit body which section still needs a sanitized screenshot. This is a live case, not hypothetical: a full pass was needed on 2026-07-31 (commit `fca5acb`) to strip already-committed screenshots that leaked exactly this data. See the operator-data rule under Version Control & Commit Discipline below — it applies to screenshots the same as it does to fixtures and logs.

### Market Monitor

- File map (`src/copenet/core/market/`): `data_sources.py` (yfinance), `signals.py`/`features.py` (technical signals, RRG, soft-bottoming), `edgar.py` (CopeTech-Edgar insider/8-K evidence + legacy fundamentals), `financials.py` (canonical point-in-time financial-series boundary), `interpretation.py`/`fact_packets.py` (LLM read pipeline), `replay.py`/`base_rates.py` (point-in-time pattern calibration), `backtester.py` (portfolio backtest + scenario stress), `webull/` (read-only broker lane — `sync.py` portfolio, `orders.py` fills, `pnl.py` all-time FIFO P&L, `watchlists.py` import; audit in `docs/plans/WEBULL_API_SURFACE.md`), `store.py` (`MarketStore` disk cache), `price_cache.py`/`price_history.py` (durable split-only daily history — every candle and P/E price reads from here), `quotes.py` (watchlist rows off that cache), `watchlist_store.py` (`WatchlistStore`, distinct from the fixed `UNIVERSE` in `universe.py`).
- **Splits always invalidate the price cache; dividends never do.** `auto_adjust=True` hides two different adjustments behind one flag — dividend-adjusting retroactively shifts all prior prices, which would drift an append-only cache invisibly at the seam, so the cache stores split-only bars plus separate split/dividend histories. Every `fetch_ohlcv()` call must stay split-adjusted (pinned by `tests/unit/test_market_data_contracts.py`); the one sanctioned split-only bypass is `fetch_daily_price_history()`, which never writes the shared cache.
- **Trailing P/E divides split-only price by point-in-time TTM diluted EPS**, not a dividend-adjusted price — the wrong basis silently understates the multiple (measured up to 35% at the 10-year mark before this was fixed).
- **Financial overlays align to `availableAt`/filing date, never `periodEnd`** — period-end alignment leaks future information into a price chart. Preserve accession provenance and point-in-time `asOf` filtering on new financial metrics.
- **A financial fact belongs to the issuer CIK, not the ticker** — multi-ticker issuers (GOOG/GOOGL, BRK.A/BRK.B) file once, so reads must match on CIK or the second-ingested ticker gets no history. SEC Company Facts also has no segment/share-class breakdown — derive it (e.g. `net income / diluted EPS`) rather than hunting for a tag that doesn't exist.
- **Lightweight Charts' time axis is index-based and pane-relative** — coordinate traps here already shipped as visible bugs twice; read `docs/plans/FINANCIAL_SERIES.md` before touching overlay positioning or `CandleChart.tsx`.
- The model-facing `market.*` tools register through `core/tools/handlers/market.py`, category `context` — add new read-only market tools there, not a new category.
- The backtest lab's named scenario presets (`SCENARIOS` in `backtester.py`) are hand-typed shock magnitudes on a synthetic curve, not a real historical replay — `run_portfolio_backtest` could replay the actual window instead; just hasn't been done.
- **Chart indicators are registry-driven; adding one touches one file.** The subsystem lives in
  `host/frontend/src/sections/market/indicators/`: a typed registry entry declares inputs,
  outputs, placement, warm-up and a PURE compute function, and that single entry drives the
  picker, the settings form, the legend, the persisted layout and the renderer. Calculations
  never import React or `lightweight-charts`; `render.ts` is the only module that knows both
  sides. Two invariants the registry-wide test sweep enforces for every indicator, including
  ones added later: `null` is the only way to say "no value" (never NaN/Infinity), and every
  calculation is causal — which is what lets indicators warm up over full history and then be
  sliced to the visible range, so changing 6M/1Y/5Y does not restart them. Indicator points
  carry **candle** timestamps for the index-based-axis reason in `FINANCIAL_SERIES.md`. When
  you add a guarded call to `render.ts`, add that method to `tests/fakeChart.ts` in the same
  commit — an incomplete fake hides the failure inside the renderer's own `try`/`catch`.
  See `docs/plans/CHART_INDICATORS.md`.
- Full history: `docs/plans/MARKET_MONITOR.md`, `docs/plans/MARKET_INSIGHT_ENGINE.md`.

## Safe Collaboration Rules

1. Read the file you are changing first.
2. Prefer one subsystem per change when possible.
3. Do not revert unrelated user edits.
4. Do not swallow provider or storage errors silently.
5. Verify protocol changes against both UI and client expectations.
6. If you touch session semantics, check the whole flow: create, send, list, resolve, archive, history.

## Version Control & Commit Discipline

Working code that only exists in the working tree has no rewind point. Treat committing as part of finishing work, not an afterthought.

- **Commit in logical, self-contained groups.** One subsystem or feature per commit (e.g. `feat(fleet): ...`, `feat(market): ...`, `docs: ...`), not one giant blob spanning unrelated areas. Each commit should be a coherent state you'd be willing to `git revert` or `git checkout` back to.
- **Commit and push once a coherent unit of work lands.** Do not let large amounts of work accumulate uncommitted. If you discover a big pile of uncommitted changes, group it into themed commits and get it into history before starting new work.
- **Use conventional-commit subjects** with a scope: `feat(scope):`, `fix(scope):`, `docs:`, `chore(scope):`, `refactor(scope):`. Keep the subject imperative and specific; add a short body when the "why" isn't obvious.
- **Keep the working tree clean.** Don't commit scratch/temporary files (`tmp_*`, one-off probes) — delete them or leave them untracked. Never commit secrets; `.env*` stays gitignored.
- **Keep operator data local.** Never commit live broker/account output, holdings, quantities, cost basis, balances, fills, P&L, account-derived watchlists, personal names/emails, local usernames, screenshots of private data, or fixtures copied from a real account. Use synthetic fixtures and keep raw probes under `~/.copenet` or ignored `docs/private/`.
- **Before pushing to the public remote:** sweep for secret-shaped strings and run at least a syntax/compile smoke check. Prefer branching for risky or reversible-only-with-effort changes; direct commits to `main` are fine for docs and captured-state checkpoints.
- **Group deletions/renames with their rationale** in the same commit (e.g. removing a superseded module in the commit that replaces it), so history reads as a story rather than a diff dump.

## Parallel Review

CopeNet contributors should actively use parallel review capacity when it helps de-risk a change or speed up investigation.

- Assume the team has access to two additional AI reviewers beyond the current coding agent.
- Use those extra reviewers for fresh eyes on traces, provider behavior, UI/UX flows, or patch plans when the problem feels ambiguous or suspicious.
- Treat outside-model reviews as advisory, not authoritative. Always verify claims against CopeNet code, traces, and runtime behavior before acting.
- Prefer giving parallel reviewers tightly scoped questions, concrete file paths, and exact run bundle directories instead of broad “figure it out” prompts.
- Record durable findings in the relevant canonical document or `docs/plans/ROADMAP.md` so the team can build on them rather than re-discovering them.

### AI Collaboration

Codex, Claude, and Gemini are all capable full-stack collaborators. Do not assign permanent frontend, backend, product, or architecture ownership based on the model name. The agent actively leading a task owns its implementation, integration, and verification unless the human explicitly assigns those responsibilities differently.

- The human may mostly act as prompt/orchestration support while juggling work and life. The active lead agent is expected to carry autonomous project-management load: propose the next work, use available collaborators when helpful, and keep progress moving without repeated reminders.
- The lead coding agent should default toward action, implementation, debugging, and cleanup. Do not sit idle waiting for the human to remember available help, enumerate every next step, or manually orchestrate every lane.
- Choose collaborators by the task at hand, current context, and available tools. Familiar strengths can inform an assignment, but they are preferences rather than ownership boundaries.
- When parallel work would materially accelerate delivery, give collaborators bounded, mergeable assignments with explicit files, goals, and constraints. 
- Treat every collaborator's output as useful but advisory until it is verified against the current code, traces, tests, and runtime behavior.

## Verification Expectations

There is not a deep automated suite yet, so manual and targeted verification matter.

Common checks:

- `python3 -m py_compile $(rg --files src/copenet -g '*.py')`
- `npm run lint` in `src/copenet/host/frontend`
- `npm run build` in `src/copenet/host/frontend`
- `uv run copenet`
- **Restart the host after changing `copetech_sec`.** The running process holds the module in memory, so accounting changes do not appear on a page reload — only a server restart picks them up. A frontend-only change needs `npm run build` plus a reload; a CopeTech change needs both.
- Browser Use validation in the Codex/Claude in-app browser for the affected session/runtime flow when available
- browser validation of the affected session/runtime flow

### Browser Verification Targets

- Prefer `http://127.0.0.1:17123/` for checks running on the host Mac.
- The private tailnet URL is also valid when the current browser is already using
  it or remote-device behavior is what needs verification. Resolve the current
  address with `tailscale ip -4`; do not hard-code a personal hostname or IP in
  code, tests, or documentation.
- Launch the tailnet bind with
  `COPNET_HOST=tailscale uv run --env-file .copenet.env copenet`. The root
  `.copenet.env` is gitignored and must contain a private `COPNET_TOKEN`;
  `dev-token` is loopback-only. This is also aliased as `copenet-tail` (function
  `copenet_tail` in the operator's `~/.zshrc`) — an agent shell inherits the
  profile, so `copenet-tail` works directly; no need to reconstruct the raw
  command from `main.py`.
- Reuse an existing authenticated browser tab when possible. A browser visiting a
  custom-token host needs the matching value entered through CopeNet's
  authentication banner once. Never read, print, commit, paste into prompts, or
  place the token in a shared URL.
- **The automated browser pane reports `document.visibilityState: "hidden"` and never paints.** `requestAnimationFrame` does not fire there and Lightweight Charts' price scale never recalculates, so chart interactions that depend on a repaint cannot be verified through it — a correct fix and a broken one both look like "nothing moved". Verify what the pane can actually show (DOM geometry, payload shape, console, network) and hand genuine interaction testing to the operator rather than reporting an unverified pass.
- Choose localhost for ordinary desktop UI verification and Tailscale when testing
  remote reachability, HTTPS/microphone behavior, or the exact URL the operator is
  currently using.

For current integration coverage, also know about:

- `uv run --extra dev pytest -q`
- `tests/integration/test_tool_prompt_matrix.py` — deterministic fake-provider prompt/tool-loop matrix
- `scripts/live_probe_matrix.py` — nondeterministic live provider/model probe runner for real runtimes

For real provider session probing during development, use the CopeNet CLI chat lane. It creates or continues a real
orchestrator-backed session, uses the same transcript/session stores as the UI, and prints streamed assistant text plus
tool calls/results:

- `uv run copenet chat send --session 69696469 --provider openai-codex --model gpt-5.5 "Run pwd, then tell me stdout."`
- `uv run copenet chat send --session 69696469 "What command did you just run?"`
- `uv run copenet chat history --session 69696469 --limit 12`

Session key `69696469` is the standing local probe session. Reuse it when checking continuity across turns; use a fresh
session key when you need a clean baseline. The CLI path is for live runtime verification and can spend provider quota
or execute allowed tools, so prefer targeted prompts and default guarded mode unless a full-access scenario is explicit.

### Tracing

CopeNet writes one JSONL trace per run to `~/.copenet/logs/runs/<run-id>.jsonl`, **unconditionally**. Every row carries a `tier`:

- **`lifecycle`** — always written. Run/session identity, provider and model, harness plan, tool requested/executed/blocked with tool id and status, token estimates, trim events, terminal reason, timings. Carries no prompt text, message history, reasoning content, or tool result bodies. Tool arguments ride along **digested** (`argument_digest` in `tool_loop_common.py`): short scalars verbatim — the `shell.exec` command and the `files.rg` pattern are the point of the trace — and anything over 400 chars replaced by `{"chars": n, "omitted": true}` so a `files.write` body never lands here.
- **`debug`** — only while Debug capture is on (Observability header toggle, `COPNET_TRACE=1` sets the initial default). Adds `run_input`, `model_input_snapshot`, `tool_arguments`, `tool_result_body`, and reasoning content.

The harness tool loops receive a bare `trace(event, payload)` callable, not the writer, so **`DEBUG_TIER_EVENTS` in `core/tracing/__init__.py` is what routes an event to the debug tier** — add a payload-heavy event's name there rather than assuming `record()` means lifecycle. Credential redaction applies to the debug tier as before.

Retention: 8 MiB per run (then a single `trace_truncated` row), oldest-first prune at startup against 256 MiB / 2,000 files, and a **Purge traces** button in the Observability header (`observability.traces.purge`). None of it touches run records, transcripts, or artifacts.

Full event reference: [docs/TRACING.md](docs/TRACING.md)
Debugging runbook: [docs/DEBUGGING.md](docs/DEBUGGING.md)
Open trace and observability work: [docs/plans/ROADMAP.md](docs/plans/ROADMAP.md)

**Triage order for a bad run:**

1. Check `harness_planned` — was `willAttemptToolLoop` correct? Was `promptedToolUse: true`? Does `availableToolIds` match Access expectations (**write tools only with `full-access`**)?
2. Check `harness_decision_recorded` when present — it is trace/UI data only, not a steering gate.
3. Check `tool_requested` — did the model invoke an exact registered tool id with correct structured arguments?
4. Check `tool_executed` or `tool_blocked` — was this a policy rejection or a real failure?
5. Check `assistant_finalized` — was `toolExecutionAttached` as expected?
6. Check `run_failed` — the `error` field is the primary diagnostic.

**No trace file?** Either the run predates always-on tracing (2026-08-02) or its trace was purged/pruned. If the run is recent and the file is genuinely missing, the provider failed to initialize before the run started — check provider availability via `providers.list` or startup logs.

**Payload you expected isn't there?** Check the row's `tier`. Arguments in `tool_requested` are digested by design; the full ones live in `tool_arguments`, which requires Debug capture *at the time the run happened* — no tier can be backfilled.

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
