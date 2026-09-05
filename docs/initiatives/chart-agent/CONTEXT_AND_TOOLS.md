# Chart agent: context, tools and evidence efficiency

Research and design review, 2026-09-04. The shipping behavior is documented in
[DEMO.md](DEMO.md). Recommendations below are next slices, not implemented capabilities.
This review uses the implementation and operator-supplied output; it does not independently
verify the vendor candles or treat a model's description of its own calls as a trace.

## Current data path

1. Market acquisition owns data loading. `useTickerViewModel` and `viewState/`
   expose the same committed inputs used by the chart and mounted research panels.
2. Each send serializes an immutable observation: loaded D/W/M candles, viewport,
   selection, plotted indicators, financial/comparison data, displayed quote, drawings,
   settings and contributed panels. Capture does not fetch newer data behind the UI.
3. `chart_workspace/projection.py` introduces the instrument, resource inventory,
   settings, coverage counts and bounded exact samples. It prioritizes the active
   candle interval, then indicators. Unselected samples favor the recent visible tail;
   a selected region starts at its beginning. These samples are not a whole-chart summary.
4. `market.chart.read` supports time ranges, fields, offsets and metadata paths. It
   reads the immutable source rather than a lossy summary. Loaded source rows and rows
   delivered to the model are different quantities, visible through inspection.
5. Ordinary harness sessions execute five registered chart tools. Drawing writes are
   revision checked and scoped to the agent's layer; saved and rendered are separate.
   The next send captures a new observation; in-flight evidence remains fixed.

This is structured context plus targeted retrieval. A screenshot could later supplement
layout or visual-pattern questions, but numeric evidence should remain addressable data.
The agent cannot currently browse every Market section, add indicators, start scans,
configure alerts, or consume crypto order books simply because those features exist elsewhere.

## What external implementations tell us

- TrendSpider documents Sidekick's access to chart context, watchlists, market data,
  annotations, scans and alerts, along with product knowledge. This supports the product
  direction of an assistant that understands both evidence and available operations.
  Its public documentation does not establish its internal snapshot schema, context
  allocation, or compression algorithm; we should not claim to copy those internals.
  [TrendSpider Sidekick](https://help.trendspider.com/kb/sidekick/trendspider-sidekick)
- Anthropic recommends a compact initial context with identifiers that let the agent
  retrieve detail as needed. Its guidance also describes the latency tradeoff: too little
  orientation can cause unnecessary exploration. Our design should give useful orientation
  immediately, with exact evidence available for deeper questions.
  [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Tool names, descriptions and outputs are part of the model's interface. Anthropic
  recommends clear responsibilities, range/filter/pagination controls, and evaluating
  formats against actual tasks rather than assuming one serialization always wins.
  [Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Coinbase's documented Level 2 feed uses a snapshot followed by updates; quantities
  replace the size at a price level and zero removes it. Other channels have different
  sequencing contracts. This is an example of why the eventual crypto adapter must own
  feed-specific reconstruction before exposing a coherent book to an agent.
  [Exchange WebSocket channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels)

These are useful patterns and vendor-documented capabilities, not a universal industry
standard or proof of analytical accuracy.

## Make features discoverable without making every button a tool

Extend the existing resource contributions and tool descriptors; do not build a second
registry that duplicates their schemas or authority. Keep three concepts distinct:

| Concept | Model needs to know | Existing home / proposed extension |
| --- | --- | --- |
| Environment | Bound instrument, active interval, visible range, selected region, scale and units | Observation/settings; add concise typed capability status |
| Evidence | What is loaded, stale, missing or excluded; fields, coverage, provenance, how to read it | `ViewResource`, projection and `market.chart.read` |
| Actions | Exact registered operation, prerequisites, scope, effect and receipt | Tool descriptors, harness policy and domain handlers |

Contributor rule for new Market features:

1. Identify the committed render model. Publish that model through `useViewResource`
   or the existing capture path, retaining symbol scoping and cleanup on unmount.
   Never create an extra fetch or private model-only calculation to imitate the screen.
2. Declare a stable resource key, domain kind, row fields, units, source time, availability
   time where relevant, price basis, active filters, completeness and account scope.
   Report not-loaded/empty/error/stale/excluded honestly; resource existence is not proof
   that the model has inspected it. Preserve nulls and exact evidence references.
3. Reading a new panel normally extends the resource inventory, not the tool count.
   Add a tool only for a distinct operation with a real domain contract. A model changing
   an indicator must use the same indicator registry/config validation as a user.
4. Keep action authorization explicit. Existing scan preview/scope admission and alert
   delivery consent still apply if tools are introduced. Chart annotation access must
   never silently become permission to scan broadly, send messages or place orders.
5. Ship the registered descriptor, validation, bounded result, user-visible inspector
   representation and behavior verification together. Record unsupported actions until
   implemented; never describe a roadmap capability as callable.

The first extension should be a compact environment/resource description, derived from
actual registered capabilities. Include field descriptions, source/basis/freshness and
coverage before numeric samples consume the budget. Full tool discovery is unnecessary
for today's five tools; introduce on-demand schemas only when the catalog warrants it.

## Spend tokens on evidence that changes the answer

Current Quick/Balanced/Deep targets are approximately 2k/5k/10k tokens for the initial
chart payload, with 4/8/12 explicit reads and 100/500/2,000 rows per read. Initial sample
ceilings are 12/40/100 rows per eligible resource, subject to the shared character budget.
These are character-derived estimates, not tokenizer measurements or total-turn limits.
Instructions, conversation history, tool definitions, subsequent tool responses and
model output add cost; growing inputs may be sent again across tool-loop requests.

A local measurement of compact JSON containing only each current tool's name,
description and argument schema totals **5,115 characters** (roughly 1,279 tokens using
characters/4). That excludes provider wrappers, other instructions and actual tokenization.
It is evidence that schema cost belongs in accounting, not a billed usage claim.

Recommended sequence:

- **Measure first.** Extend existing run/inspection telemetry with chart-context,
  tool-schema and tool-result estimates; keep them separate from provider-reported usage.
  Track every model request, cached input where reported, output/reasoning according to
  provider semantics, calls, latency, rows inspected and repeated reads. Never double-count
  reasoning tokens included in a provider's output total. Missing usage stays unknown.
- **Reserve orientation.** Source/basis, quote freshness, forming-candle caveats, selected
  region and coverage should survive sample allocation. Today resource metadata generally
  requires an exact read, and the sample loop stops at the first non-fitting sample. A
  large earlier resource can crowd out a later quote or indicator. Test this explicitly.
- **Summarize deterministically, retain exact source.** Offer bounded range extrema,
  returns, gaps and indicator values computed by shared chart/market math. Each result
  should name the observation, time window, method and supporting rows. A broad market
  question needs overview across the requested range, not only its most recent candles.
- **Let questions select detail.** Reading all weekly bars can be reasonable for broad
  price structure. A question about one candle should retrieve that candle and relevant
  neighbors. Re-reading `market.chart.context` repeats a payload already attached to
  the initial message; the environment explanation should make this clear.
- **Benchmark serialization.** Compare current row objects with a declared column list
  and row arrays on the same tasks and tokenizer. Repeated field names may cost tokens,
  but column confusion can cost accuracy. Never round prices, collapse nulls or replace
  source candles with downsampled rows merely to report a smaller payload.
- **Separate numerical and prose retrieval.** Time/field queries and deterministic
  calculations suit candles and order books. Search over filings or research prose can
  retrieve passages with filing dates and source references. Semantic similarity does
  not replace exact numeric queries or point-in-time availability rules.

The optimization objective is lower total cost and latency at the same evidence accuracy
and coverage. A detail slider should expand inspection depth; it should not silently
lower numeric precision or discard the stored evidence.

## Evaluation and next slices

Keep tests synthetic; do not commit operator screenshots or live transcripts. The shared
example suggests a working read/write/receipt sequence, but that does not prove that
drawn levels are predictive or that every claimed viewport candle was inspected.

Use a small question suite across D/W/M, with indicators, financial panels and new assets:

- Exact selected-candle OHLCV, including null indicator warm-up and incomplete bars.
- Full-range analysis with a major early extreme outside the recent sample.
- Correct source/basis/staleness and distinction between quote time and candle time.
- Financial observations unavailable before their filing/availability date.
- Unsupported action recognition, scope exclusions and manual drawing ownership.
- Drawing anchors, evidence links and saved/rendered status after hide, switch or reload.

Run the same tasks at all three detail settings and across representative providers.
Score numeric correctness, cited-row correctness, coverage, unsupported claims, successful
operations, actual usage where available and latency. A valid drawing is an annotation;
an inferred trendline or continuation scenario needs an explanation of its method and
uncertainty. Connecting two endpoints alone does not establish a tested support line.

The pasted output also contains progress sentences concatenated without separators and
lengthy receipt diagnostics. Investigate response/message boundaries with a synthetic
multi-tool-turn reproduction; preserve provider streaming chunks and append-only history.
Do not guess boundaries by inserting whitespace into arbitrary text deltas. Keep technical
diagnostics in inspection for ordinary research answers, but honor explicit tool-test requests.

Proposed order: (1) environment orientation and usage/coverage evaluation;
(2) shared deterministic range analysis and compact exact-read formats;
(3) indicator/financial-plot actions through their existing domain contracts;
(4) broader Market resources and actions once each has scoped admission.

For the operator's future crypto backend, reconstruct and validate the stream in the data
service, preserving venue/product identity, decimal precision, exchange and receipt times,
depth coverage, feed-specific sequence/gap handling and reconnect behavior. Agents should
receive coherent snapshots and bounded event windows with retained evidence, not every
WebSocket update as a new prompt. Proposed live commentary should use explicit activation,
meaningful event triggers, coalescing, cooldowns and a user-visible spending budget.
