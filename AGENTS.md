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

Old top-level shims (`orchestrator.py`, `harness.py`, `tracing.py`, `sessions/`, `tools/`) re-export from `core/` for backward compatibility.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the current request flow.

## Architectural Principles

**Thin providers.** Providers should translate runtime-specific APIs into shared provider events and model metadata. Session policy, prompt composition, and run lifecycle belong elsewhere.

**Harness before specialization.** Shared capability reasoning should live in the harness layer, not be copied into each provider or the UI.

**Append-only transcripts.** Transcript history is durable by design. Do not add mutation paths for stored messages.

**Atomic session writes.** `SessionStore` must keep the temp-file + rename pattern for index updates.

**Session identity is sacred.** Once a session is used, never silently mutate its binding. Provider/profile/persona/workspace stay locked. Model (same provider) and Access (task mode) may change mid-session, but only via an explicit operator-driven request — the model can never alter its own runtime — and each run is stamped with what it actually used. See Session Semantics below.

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
- **Before committing any README screenshot, check the frame for operator-specific data** — the Market Monitor "since you last looked" strip and daily-briefing header render a real portfolio dollar figure (`Book`/`Portfolio $…`), and the Agents Console Inspector's Destinations panel can show a real phone number or other personal identifier. Either crop those elements out, capture a clean state (empty portfolio / no destinations configured), or skip that panel and note in the PR/commit body which section still needs a sanitized screenshot. This is a live case, not hypothetical: a full pass was needed on 2026-07-31 (commit `fca5acb`) to strip already-committed screenshots that leaked exactly this data. See the operator-data rule under Git Hygiene below — it applies to screenshots the same as it does to fixtures and logs.

### Market Monitor

- Lives in `src/copenet/core/market/`: `data_sources.py` (yfinance — includes `search_symbols()` for live ticker/company lookup and `fetch_daily_price_history()`, the one split-only fetch backing `PriceCache`), `signals.py`/`features.py` (technical signals, RRG, soft-bottoming pattern), `edgar.py` (CopeTech-Edgar adapter — insider Form 4/8-K evidence and legacy fundamentals), `financials.py` (canonical point-in-time CopeTech-Edgar financial-series boundary), `interpretation.py`/`fact_packets.py` (the LLM read pipeline), `replay.py`/`base_rates.py` (point-in-time pattern calibration), `backtester.py` (portfolio backtesting + scenario stress simulation), `webull/` (read-only broker lane: portfolio `sync.py`, fill history `orders.py`, all-time FIFO P&L `pnl.py`, `watchlists.py` import; surface audit in `docs/plans/WEBULL_API_SURFACE.md`), `store.py` (`MarketStore`, caches bars/signals/dashboard/reads to disk), `price_cache.py`/`price_history.py` (durable split-only daily history; every candle and P/E price now reads from here), `quotes.py` (watchlist rows off that cache, bounded concurrency rather than a per-symbol fan-out), `watchlist_store.py` (`WatchlistStore` — user-curated add/remove ticker list, distinct from the fixed `UNIVERSE` in `universe.py`; RPC handlers in `host/rpc_market_watchlist.py`: `market.watchlist.get/add/remove`, `market.symbols.search`).
- **Candle history comes from `PriceCache`, not from a fresh fetch.** `price_cache.py` + `price_history.py` hold one durable daily history per symbol and derive weekly/monthly by resampling and total-return by applying dividends at read time. Before it existed, one ticker view cost ~8 yfinance requests and the morning sweep 2 per symbol; both now cost one. New price consumers read the cache. Full design: `docs/plans/PRICE_CACHE.md`.
- **Cache invariant: dividends never invalidate the cache; splits always do.** `auto_adjust=True` hides *two* adjustments behind one flag. Splits are mechanical and must always be applied. Dividends are not: adjusting for them turns a price chart into a total-return chart, and because every dividend retroactively shifts all prior adjusted prices, an append-only cache of that basis drifts invisibly at the seam. The cache therefore stores split-only bars plus the split and dividend histories. A split rewrites Yahoo's own history, so it forces a full rebuild — detected on the delta fetch.
- **Load-bearing invariant: every `fetch_ohlcv()` call must be split-adjusted.** The function defaults to `auto_adjust=True`; do not call it with `auto_adjust=False` and do not add a new caller that skips this. Every consumer sharing `MarketStore`'s bar cache does so under the same `(symbol, timeframe)` key with no adjustment-basis tag, so one caller writing a different basis silently corrupts every other reader — including fake price cliffs on splits (this happened for real, 2026-07-06 — see `[[project_market_monitor]]`). The one sanctioned split-only path is `fetch_daily_price_history()`, a separate function that never writes that cache. Both rules are pinned by `tests/unit/test_market_data_contracts.py`.
- **Trailing P/E divides split-only price by point-in-time TTM diluted EPS.** The numerator must be the price that actually traded. Dividend-adjusted prices back-shift history downward, so the same EPS over a lower price reads as a lower multiple — measured understatement at the 10-year mark before this was fixed: XOM 35%, KO 27%, AAPL 8%, decaying to zero at the right edge, i.e. the shape of a de-rating that never happened.
- **Financial overlay invariant: price charts and backtests align fundamentals to `availableAt`/filing date, never `periodEnd`.** Period-end alignment is accounting analysis only; using it against price leaks future information. Preserve accession provenance, derivation flags, and point-in-time `asOf` filtering through new financial metrics.
- **Lightweight Charts' time axis is index-based, and its coordinates are pane-relative.** Two traps, both of which shipped as visible bugs (see the 2026-07-31 findings in `docs/plans/FINANCIAL_SERIES.md`):
  - Every unique timestamp across *every attached series* takes one equal-width slot regardless of real spacing. An overlay point on its own filing date does not sit between two candles, it **inserts** a slot — which compresses the candles and corrupts the `barSpacing` other decorations size themselves from. Snap overlay points onto candle timestamps (`snapOverlayToCandles`), forward only, since snapping backward would draw a filing before it was public.
  - `timeToCoordinate()` and `param.point.x` are relative to the **pane**, which begins after the left price axis. Anything positioned against the chart wrapper must add `priceScale('left').width()` back. This is 0 until a financial overlay makes that axis visible, so the bug hides until someone toggles an overlay.
- **Chart decorations must track the price scale, which publishes no event.** Lightweight Charts has a visible-time-range subscription and nothing at all for vertical changes, so absolutely-positioned overlays drift on axis drag, vertical pan, autoscale shift, and the log/linear toggle. `CandleChart` samples both mappings and recomputes on change, driven by pointer/wheel listeners with an rAF loop as catch-all — the rAF loop carries no load-bearing case on purpose, because rAF does not run while the document is hidden. Note that `applyOptions` only *invalidates* a price scale: `priceToCoordinate` keeps returning the old mapping until the chart repaints, so recomputing synchronously after a mode change reads stale coordinates. Invalidate and defer a frame instead.
- **SEC Company Facts returns only non-dimensional facts.** Anything an issuer reports broken out by segment or share class is simply absent, and no amount of widening the concept list will recover it. Alphabet tagged weighted-average diluted shares per share class until mid-2024, so the consolidated divisor did not exist — the fix was to derive it as `net income / diluted EPS` (agrees within 0.22% where both exist), not to hunt for another tag.
- **A financial fact belongs to the issuer CIK, not to a ticker.** Multi-ticker issuers (GOOG/GOOGL, BRK.A/BRK.B, FOX/FOXA) file once. The fact ledger keys identity and uniqueness by CIK, so reads must match on CIK too; filtering reads by symbol left whichever ticker was ingested second with no history at all.
- The model-facing `market.*` tools (`market.dashboard`, `market.ticker`, `market.compare`, `market.backtest`, `market.evidence`, `market.financials`) are registered through `core/tools/handlers/market.py`, category `context` (read-only, auto-allowed at every Access level) — add new read-only market tools there, not under a new category.
- The backtest lab's named scenario presets (`2022_tech_dump`, `2020_covid_crash` in `backtester.py`'s `SCENARIOS` dict) are **hand-typed shock magnitudes projected onto a synthetic cosine curve, not a real historical replay** — `run_portfolio_backtest` (the real engine, already correct) could replay the actual historical window instead; this just hasn't been done yet.
- Full history: `docs/plans/MARKET_MONITOR.md`, `docs/plans/MARKET_INSIGHT_ENGINE.md`, and this session's memory (`project_market_monitor.md`) for the blow-by-blow of what shipped and why.

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
  `dev-token` is loopback-only.
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
