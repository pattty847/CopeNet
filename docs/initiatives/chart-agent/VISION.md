# Chart Agent — Vision & Execution Brief

Status: shaped for discussion; implementation has not started.
Date: 2026-09-04.

## Product intent

An agent works beside the operator inside the ticker workspace. It understands the
actual chart being viewed, can inspect its underlying data, and can express an
analysis through editable drawings and plots. Conversation, chart, and evidence
remain connected as the operator changes symbols, explores history, or follows prices.

The core promise is **shared attention with inspectable evidence**: “this candle,”
“that zone,” and “the divergence I highlighted” refer to durable, identifiable things.
Full detail remains accessible without placing every historical bar in every prompt.

## The experience

Open a ticker and open Agent beside the chart. A compact context line shows the
symbol, interval, visible dates, freshness, and whether the conversation follows the
view or is pinned to an earlier observation. The agent uses a normal CopeNet session,
with the same provider/model controls, transcript, stop action, and tool inspection.

Example interaction, using synthetic data:

1. Select a region and ask, “What changed here? Mark the levels that matter.”
2. The agent inspects that region, its indicator values, and relevant wider context.
3. It draws two zones and a trendline, with a short explanation linking to each.
4. Click a zone to see its exact bounds, anchor candles, source observation, and rationale.
5. Say, “Use the candle bodies for that upper boundary.” The same object changes.
6. Undo that edit or the entire drawing batch. Hide the agent layer without losing it.
7. Ask, “What would invalidate this?” The answer links a condition to the drawing;
   creating an actual monitoring rule is a separate, explicit action.

Desktop: collapsible, resizable right companion panel; chart remains the primary surface.
Keep the existing research dock below the chart. At narrow widths, use a switchable
chart/chat surface with a persistent selection chip instead of squeezing three panels.
Agent findings can open the corresponding Fundamentals or SEC & Events view.

The conversation follows ticker navigation between turns by default. Every turn freezes
its own subject. A visible pin keeps an investigation on one symbol while browsing others.
Changing the ticker never changes a session's locked filesystem workspace or provider.
Messages retain symbol and observation attribution, including after returning from Market.

## Detail and live participation

Use a Detail slider with three named stops. Its effect is evidence depth, not answer length.

| Detail | Initial evidence | Further inspection |
| --- | --- | --- |
| Quick | Scene inventory, visible-range summary, latest values, selected objects, freshness | Exact bounded queries when the question needs them |
| Balanced (default) | Quick plus recent exact bars, active indicator context, relevant events | Targeted history and panel reads within a larger budget |
| Deep | Wider exact windows, additional timeframe comparisons, more evidence inspection | Bounded multi-step research and optional visual inspection |

Even Quick can resolve an exact selected candle. Deep does not silently enable broad
acquisition or unlimited context. If evidence is missing or a budget is exhausted, say
what was inspected and what remains unknown. Show a compact “Context used” disclosure
with sources, ranges, omissions, approximate input size, and available usage measurements.
Do not present an estimate as billed usage or imply Detail changes model reasoning settings.

No fixed token targets yet: benchmark representative questions and provider context limits.
Preserving source detail is achievable; lossless compression of all evidence into a tiny
prompt is not. Summary selection can miss an unexpected pattern. Counter this with raw
range access, explicit coverage, user-selected regions, and evaluation against exact data.

“Follow live” is a separate, off-by-default control. Initially, conversation is user-driven;
each question can include the latest received quote and its timestamp. Later, an enabled
follow mode can react to explicit conditions or a bounded cadence. A deterministic gate
coalesces events, applies cooldowns and a run budget, and allows at most one run per session.
Ordinary quote ticks do not become messages or repeated full-chart image submissions.

Follow states must include paused, watching, analyzing, delayed, disconnected, and budget
reached. Leaving the visible ticker view pauses its ephemeral follow lane. Persistent
background monitoring belongs to the existing scans/alerts system, with its own consent.
User input takes priority over scheduled commentary; pending events are coalesced and
rechecked against a fresh observation before starting the next run.

## What exists today — inspected repository facts

- `TickerWorkspace.tsx` owns timeframe/range, indicators, comparisons, overlays, evidence,
  research tabs, and symbol transitions. `ChartStage.tsx` composes chart presentation.
- `CandleChart.tsx` renders candles, indicators, financial series, event markers, and
  alert lines. It has hover and alert-placement callbacks. No general drawing document
  or agent scene API was found in this path. Actual pan/zoom lives inside the chart;
  the toolbar's selected range alone cannot describe the visible viewport.
- `TickerReadPanel.tsx` explicitly says ad hoc zoom and overlay state are excluded.
  Its synthesis uses the separate one-shot `market.interpret` flow.
- `core/tools/handlers/market.py` provides dashboard/ticker/comparison/backtest tools;
  evidence and financial tools register there through focused modules. `market.ticker`
  fetches per-symbol data and defaults to the last 60 bars per timeframe. It is not a
  frozen read of the browser's chart and cannot substitute for one.
- The indicator registry owns pure calculations. The alerts build already executes
  registry math in a headless Node bundle. Reuse that approach for agent calculations;
  do not recreate indicator formulas in Python or ask the model to calculate long series.
- Market Tape already separates frozen evidence artifacts from compact model presentation.
  Reuse its provenance/completion conventions; keep its market-wide job separate.
- `chat.send`, the orchestrator, RunStore, ArtifactStore, and tool execution provide the
  conversation backbone. Image attachments and replay already exist; provider-specific
  vision behavior still needs verification before promising it on every model.
- Live quotes are ephemeral, leased to a visible browser connection. Chart intervals are
  D/W/M. A live quote is not a canonical intraday candle feed.

Relevant references: [Market Tape](../../plans/MARKET_TAPE_PACKET.md),
[Financial Series](../../plans/FINANCIAL_SERIES.md),
[Chart Indicators](../../plans/CHART_INDICATORS.md),
[Architecture](../../ARCHITECTURE.md).

## Proposed architecture and state ownership

These are design recommendations, not existing contracts or final API names.

1. **Live scene.** The browser publishes a typed description of the rendered symbol,
   chart instance, actual visible range, interval, scales, panes, indicator instances and
   configuration, comparisons, drawings, selection, and panel availability. Distinguish
   displayed symbol from a requested symbol that is still loading. Hover only becomes
   a durable reference when selected or captured at send time.
2. **Frozen observation.** On send, validate the scene at the RPC boundary and persist an
   immutable observation tied to the session/run. Resolve market data through canonical
   sources with revision identifiers matching the displayed data. Preserve exact consumed
   ranges/values or immutable references; a reference to a mutable latest cache is insufficient.
   Each source carries its own observation time, completion state, units, and coverage.
3. **Compact context plus retrieval.** Give the model the scene inventory and a budgeted
   evidence packet. Tools inspect exact bars, indicator series, objects, and market panels
   by observation ID and explicit range. Return row counts, omitted ranges, and continuation
   handles. Freeze any additional evidence acquired during a run as a separately timestamped
   source; never quietly replace the initial observation with fresher data.
4. **Typed chart actions.** Tool calls submit declarative edits to a revisioned chart
   document. Validate object IDs, anchors, units, target symbol/pane, and revision before
   committing. Broadcast the new revision to attached views; record browser render
   acknowledgement separately from document persistence. Never claim “drawn” from an
   unacknowledged fire-and-forget command. Reconnect reconciles from the saved revision.
5. **Existing session loop.** Route through the ordinary harness, manifest, policy, tool
   results, and inspector. Pass observation/chart bindings as validated turn context;
   do not create a second market chatbot or inject them as a replacement system prompt.

Suggested homes: `core/market/chart_agent/` for observations, queries, and document actions;
`sections/market/chartAgent/` for the companion UI and scene capture; a focused drawing
module for chart rendering; focused market tool handlers registered through the existing
aggregation point. Chart read tools use the existing context category. Chart mutations
need explicit descriptor side effects and scoped authorization in the shared policy path.
They must not be disguised as reads or require granting unrestricted shell access.

Durable drawing state belongs on the backend; the frontend projects it and owns temporary
pointer gestures/selection. One chart document can carry manual and agent layers. Object
records include identity, owner, symbol, applicable interval, pane/scale, time/value anchors,
style, rationale, evidence references, originating run, and revision. An agent batch is
undoable. Agent edits must not overwrite a subsequent human edit: check revisions and return
a conflict requiring a fresh read. Retries use operation IDs to prevent duplicate objects.

First primitives: horizontal levels, bounded zones, anchored trendlines, and labels.
Indicator add/configure/remove and existing financial plots reuse their canonical actions.
Later primitives: channels, measurements, and derived series with declared formula, units,
inputs, warm-up, and provenance. Arbitrary generated JavaScript is not the initial plotting API.

Store semantic time/value anchors, never screen pixels. Handle candle-master timestamps,
pane-relative coordinates, log scale, split adjustments, and rebased comparison units
explicitly. Inapplicable drawings remain saved but are hidden with a reason. Interval
changes preserve original anchor semantics and never silently round an analysis to a
different candle. Forward projections require a separate explicit horizon contract.

## Awareness without automatic oversharing

The agent should discover everything supported in the market workspace: chart, ticker
research, comparison state, market structure, selected lists, and optionally portfolio
context. An inventory entry means “available to inspect,” not “already read.” Each panel
gets a typed, versioned projection with loaded/empty/stale/error status and source references.
Do not scrape DOM text or dump the entire app store into the prompt.

Keep account context separable and visibly included/excluded. Existing dashboard/ticker
tools can return operator context, so a UI toggle alone cannot enforce its exclusion:
the chart session's tool outputs must honor the same scope. A view refresh must not start
a full market scan. Fresh acquisition remains explicit and uses the established paths.

An optional chart-only image complements exact data for spatial interpretation. Capture
the same scene revision, account for HTML overlays that may not be in the chart canvas,
and surface capture failure or unsupported vision honestly. Images and indicator readings
are evidence, not instructions. The agent's ability to use data does not depend on vision.

## Delivery slices and proof

| Slice | User-visible outcome | Required proof |
| --- | --- | --- |
| 1. See and draw | Chat beside chart; Balanced context; exact visible-range reads; levels/zones/trendlines/labels; undo | One real session can inspect a selected range, draw grounded objects, revise one, and undo without losing manual work |
| 2. Explore in detail | Detail slider, region references, indicator/financial plot control, panel retrieval, optional vision | Exact values match the chart registry/source; low-detail omissions are visible; Deep retrieves needed history within budget |
| 3. Follow the discussion | Opt-in event/cadence commentary using leased quotes and frozen observations | Pause/disconnect, bursts, stale quotes, user interruption, session locking, and budgets behave deterministically |
| 4. Maintain a thesis | Save analysis with drawing layers and evidence; reopen and compare what changed; explicit alert handoff | Earlier claims reconstruct from their original evidence; later data never rewrites their basis |

The first slice must include actual drawing. A conversational explanation alone does not
prove this product. Keep the first tool surface small, but preserve the full observation
and action contracts so richer tools extend the same system.

Verification uses synthetic market/account fixtures and temporary stores. Exercise
symbol-switch and multi-tab races, stale document edits, reconnect/retry deduplication,
partial candles, missing data, full-history indicator warm-up, comparison/log scales,
pan/zoom/resize alignment, persistence/reload, and model/tool/vision capability differences.
Run backend contract tests, frontend lint/build and relevant tests, then a visible-browser
flow. Hidden browser panes cannot prove chart repaint behavior. Capture sanitized product
screenshots and refresh the README when implementation materially improves the UI.

Evaluate evidence depth with tasks that require a selected exact bar, an old event outside
the default window, and a pattern omitted by a summary. Measure correctness, source coverage,
tool calls, input volume, and latency; a shorter prompt alone is not success.

## Decisions and next move

Recommended defaults for founder review: right-side companion; one continuing market
conversation with explicit per-turn symbol context; Balanced detail; direct reversible
agent-layer drawing when requested; follow-live off. An unsolicited drawing can be a
preview. Editing a human-owned object needs a specific request identifying that scope.

Defer multi-agent competing analyses, autonomous trading, tick-by-tick narration, arbitrary
code execution, and a new intraday history pipeline. They are not prerequisites for shared
chart awareness. No automatic trading or outgoing messages are authorized by this brief.

Before build, resolve exact observation retention and baseline chart-write policy as part
of slice 1's implementation plan. Extract focused concerns before expanding the existing
571-line `TickerWorkspace.tsx` and 1,107-line `CandleChart.tsx`.

Discovery also confirmed the old `market.ticker.fundamentals.get` backend/client path still
exists beside canonical financial series. Reported here under the repository's no-shim
rule; do not extend it for this initiative. Removal is separate work.

Next move: implement slice 1 end to end. The acceptance demo is one request—“Inspect this
region and draw the levels you can justify”—followed by a targeted revision and undo.
