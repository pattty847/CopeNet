# Market Scans & Alerts — Vision & Execution Brief

Status: FORGE shaping; configurable scans and technical alerts are not yet implemented.
The separately authorized scheduler safety fix is tracked in STATUS.md.

## Product intent

The operator should always know **what CopeNet will inspect, when it will inspect it,
what that costs in data requests, and what can interrupt them**. Small focused scans
must not secretly become a whole-universe refresh. Watching a symbol is not permission
to repeatedly fetch every data source for it.

User decisions: default morning sweep at **09:45**; skip missed runs rather than catch up
at startup; customizable asset baskets, sources, and multiple schedules; Telegram alerts;
**daily, weekly, monthly before intraday**; reuse Market/ticker visual language.

## Core experience

Add one Market destination, **Scans & Alerts**, with local views for Scans, Alerts, and
Activity. Use the existing square-edged instrument frame, compact tables, restrained
orange actions, monospace symbols/times, and quiet status labels. No new design system,
drag-and-drop workflow canvas, dashboard-card mosaic, or permanently split page.

The Market header gains a compact next-scan affordance, e.g. `Next scan · 09:45 ET`.
Opening it shows the actual configured job, effective timezone and next date, asset count,
source plan, and latest result. Never render a hard-coded schedule that can disagree with
the backend. Refresh becomes an explicit scan action with scope visible before execution.

### Scan table and editor

Rows show name, resolved assets, sources, schedule, next run, and last outcome. Primary
actions: New scan, Run now, Pause; secondary actions: Duplicate, Edit, Archive.
Selecting a row opens a temporary editor; on phones, it becomes a full-width sheet with
one vertical scroll owner. Tabs remain reachable, validation preserves input, Escape
closes safely, and focus returns to the invoking row. No nested vertical list scroll traps.

Editor groups:

1. **Assets:** choose named watchlists and/or individual symbols, with exclusions. Show
   the resolved, deduplicated list and why each symbol is included. Add/remove using the
   shared ticker search. Editing this scan must not edit the source watchlist. Linked
   lists follow future membership changes; direct symbols remain fixed. Required context
   such as a benchmark appears separately and counts toward data work. Missing/deleted
   references pause the scan instead of silently widening its universe.
2. **Work:** choose prices/technical screens, SEC filing types, financial statements,
   rates, or calendar sources that have a real adapter. Distinguish per-asset work from
   global sources. SEC-only work must not fetch Yahoo prices implicitly. Unsupported
   combinations explain the limitation. Model interpretation is an explicit optional
   follow-on, not an invisible cost of every refresh.
3. **When:** named timezone, selected days, and one or multiple times. Show upcoming
   occurrences before saving. Default morning time is 09:45; default missed-run policy
   is Skip. Recommend US market-session days for price-heavy scans, while SEC/global
   jobs may deliberately run on other days. Existing daily behavior is preserved until
   the operator saves a different schedule.
4. **Notify:** in-app findings, optional Telegram destination, and material-change/digest
   behavior. Quiet scans do not need a message. Show configuration/authorization status.

Before Run now, show scope and estimated fetch work: fresh-cache hits, symbols requiring
refresh, newly added symbols needing initial history, and source-specific limits. Do not
label a symbol count as an exact HTTP request count—vendor adapters can make several calls.

### Alert creation and evaluation

From a ticker indicator's menu, **Create alert** pre-fills symbol, D/W/M timeframe,
indicator parameters, price basis, and output series. The central Alerts view offers the
same editor. Start with clear expressions: output crosses above/below a threshold or
another output, including price vs SMA, EMA crossovers, RSI thresholds, and MACD vs signal.
Do not start with arbitrary code or an unbounded nested boolean builder.

Show the rule as a readable sentence plus its latest valid observation. Distinguish
**candle timeframe** from **evaluation schedule**: a 09:45 scan evaluates the previous
completed daily candle, not today's open and not an alert delivered yesterday at close.
Offer a separate small post-close scan when earlier notification is desired; it should
not rerun the large morning universe. W/M alerts wait for completed W/M periods.

Default crossing semantics: establish a baseline when armed; fire on a subsequent
transition, never retroactively. One-shot or repeat-on-new-crossing; repeating rules
re-arm only after leaving the condition. Rechecking the same bar does not emit another
event. Missing history, insufficient warm-up, provisional bars, and fetch failures are
visible evaluation states, not false conditions or zero-valued indicators.

Telegram messages carry symbol, condition, timeframe, observed values, candle close time,
evaluation time, and a ticker deep link. A configured destination is not proof of delivery.
Show queued, authorization-required, sent, and failed states. Test message is explicit.

## Existing-system fit and required changes

| Existing boundary | Reuse / correction |
| --- | --- |
| `core/market/sentinel.py` | One schedule owner; replace env-only timing with persisted named scan definitions, not a second scheduler. |
| `core/market/watchlist_store.py`, `universe.py` | Reuse asset/list selection. Replace the hidden fixed-universe union with an inspectable per-scan resolver. Resolve stable list identity/rename behavior once when introducing references. |
| `core/market/runtime.py` | Extract acquisition from dashboard assembly: assembly currently fetches SEC evidence. Small jobs require explicit symbol/source inputs and scoped results. |
| `core/market/price_cache.py`, `price_history.py` | Canonical split-only daily history, freshness, and D/W/M derivation. Add completed-period eligibility with exchange calendar and cache provenance. |
| `core/market/edgar.py`, `financials.py`, `economic_calendar.py`, `yield_curve.py` | Source adapters, each with honest refresh capability and cadence; not every source currently belongs to the morning sweep. |
| `core/market/alerts.py` | Evolve the existing durable alert concept rather than adding a parallel TA-alert store. One explicit migration for existing price rules. |
| Frontend `market/indicators/` | Stable IDs, parameters, outputs, warm-up rules, pure math. Alerts must agree with chart calculations; existing backend RSI uses different smoothing. |
| `core/messaging/`, `core/orchestrator/messaging.py` | Reuse destinations and policy, but implement actual outbound delivery: the current test/configuration surface does not send messages. |
| Market workstation, ticker controls, shared popovers/search/tokens | Reuse interaction and visual primitives; server-owned definitions survive browsers/devices. |

### Proposed state and execution contract

- **ScanDefinition:** stable ID/revision, name, enabled state, asset selection, source work,
  schedule/timezone, skip policy, optional interpretation and notification settings.
- **ScanRun:** definition revision and resolved asset/source snapshot, scheduled/manual
  reason, timestamps, cache/fetch counts, partial failures, result references. Append-only
  history; distinguish skipped/interrupted from completed. A small scan never overwrites
  the global briefing or makes missing global panels appear empty.
- **AlertRule:** existing alert identity evolved with operands, settings, D/W/M, schedule
  association, repeat mode, enabled state, destinations, and last evaluated candle/revision.
- **TriggerEvent / DeliveryAttempt:** immutable condition evidence separate from mutable
  delivery attempts. Retrying Telegram cannot rerun the scan or reevaluate the indicator.

Execution: resolve job → plan scoped fetches → acquire/cache → derive completed-bar
signals/evidence → persist results and trigger events → deliver notifications. One
coordinator owns scheduled/manual work with a market-root process lock, shared per-source
request budgets, and coalescing across overlapping jobs. A process-local asyncio lock
alone does not protect two running CopeNet instances. Do not replay an offline backlog.
For failures, use bounded adapter retries for failed requests, not repeated full sweeps.

Persist definitions and current state atomically under the Market data root. Validate
at RPC/persistence boundaries. Route selection/edit state in the URL; forms local; no
second global frontend store. Record definition revisions so editing a live job cannot
silently change its in-flight scope. Preserve cached results with their original freshness.

### Two technical gates before promising the full feature

1. **Chart-identical evaluator.** Prototype a bundled headless evaluator over the existing
   pure TypeScript indicator graph, invoked via a bounded JSON contract. This avoids
   silently different Python arithmetic and supports the existing catalogue. Node becomes
   a declared runtime dependency: verify packaging, cold-start cost, timeout/output limits,
   and unavailable-runtime UX before adopting it. If that cost is disproportionate, bring
   back a limited Python subset with explicit cross-language parity tests—not a second
   independently maintained indicator catalogue.
2. **Completed candle + delivery correctness.** D/W/M requires exchange-session completion
   (holidays, early closes, DST, cached pre-close tails), not calendar resampling alone.
   Begin with US equities/ETFs; unsupported markets must say so. Telegram needs a real
   adapter plus durable outbox, rate-limit/backoff handling, policy rechecks, and credential
   isolation. Guarantee deduplicated internal events, not impossible exactly-once external
   delivery after an ambiguous network timeout.

## Delivery slices and acceptance

1. **Safety now:** 09:45 default; no boot/page-load catch-up; explicit Run now still works;
   completed daily prices for existing price alerts. No live vendor fetches in tests.
2. **Scan control, end to end:** source/universe audit and extraction, persisted definitions,
   schedule preview, exact scope UI, pause/run, durable run history, overlap protection.
   Preserve the current full morning job as one visible definition via a one-time migration;
   remove the old environment scheduler path once migrated.
3. **D/W/M alert vertical slice:** evaluator feasibility/parity, complete-bar selection,
   alert schema migration, ticker creation and central management, deterministic event
   evidence. First proving set: price, SMA, EMA, RSI, MACD.
4. **Telegram and polish:** adapter/outbox, explicit destination authorization, test-message
   flow, failure/retry UI, source coverage feedback, keyboard/mobile verification.

Acceptance scenarios include: start after scan time with no stored brief and issue zero
full-scan requests; add one symbol to a focused scan without widening the default job;
run SEC-only with no Yahoo requests; overlapping scans reuse fresh fetches; Friday/holiday
weekly and month-end alerts match the chart; 09:45 never treats today's open as a daily
close; restarts/repeated scans produce one event per rule revision/candle; retrying a
failed delivery issues no market-data calls. Test empty/stale/partial/error states, 320px
through large desktop, focus restoration, history navigation, and a physical phone pass.

Non-goals for this initiative: intraday/live trading feeds, order execution, arbitrary
strategy scripting, cloud hosting/always-on service, natural-language rules without an
inspectable deterministic expression, or forcing every source into every scan.

Recommended next move: implement slice 2 and the evaluator feasibility gate together,
then deliver the first D/W/M alert through Telegram before broadening the rule catalogue.
