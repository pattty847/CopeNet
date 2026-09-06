# Inside CopeNet

[Back to the README](../README.md) · [Get started](STARTUP.md)

CopeNet combines a Market research workspace with the agent harness that powers its
conversations. This tour covers the broader platform; the README starts with chart agents
and forecast experiments. Some screenshots show earlier workspace chrome. Synthetic
captures are labeled and do not represent model performance.

## Market workspace

### Charts and evidence in one place

Each ticker has a dedicated research workspace with daily, weekly and monthly price
history, indicators, annotations, SEC events, and a collapsible research panel. Switch
between price action, fundamentals, filing evidence, and model synthesis without losing
the asset you are studying.

The financial explorer covers income, cash flow, margins, balance sheets, per-share
metrics, and valuation, with source filings attached to the underlying periods.
Financial overlays align to when information became public; unsupported historical P/E
values stay blank. Price history uses a split-adjusted basis.

![Financial explorer with annual income statements](imgs/market-ticker-workspace.png)

### Chart conversations and forecasts

The chart agent captures the committed render inputs on send. It can read captured
candles and indicator values, inspect supported research resources, and apply drawing
operations through scoped tools. The visible or selected range sets the focus; exact
surrounding captured history remains queryable. CSV tables carry numeric detail with
source metadata rather than repeating JSON keys in every row.

Annotations retain evidence references and document revisions. Manual edits protect
objects from later agent writes. A saved drawing and a confirmed render have separate
receipts. Account panels are excluded from new captures by default; a conversation's
existing history is a separate source of context.

Forecasts use isolated model runs with frozen evidence. Published entries, stops and
targets are separate from editable drawings. Scheduled price tracking evaluates
completed daily candles, without invoking a model, and preserves stopped, expired,
ambiguous and completed outcomes. The original setup chart shows a bounded historical
lead-in followed by observed closes across the forecast horizon.

![Forecast overlays in the chart companion — synthetic example](imgs/market-chart-forecasts.png)

![Forecast Ledger — synthetic trade and direction outcomes](imgs/market-chart-forecasts-ledger.png)

See [chart-agent behavior and verification](initiatives/chart-agent/DEMO.md),
[context/tool extension rules](initiatives/chart-agent/CONTEXT_AND_TOOLS.md), and
[forecast evaluation and limits](initiatives/chart-forecasts/STATUS.md).

### Watchlists, briefing, and rotation

Market includes watchlists, sector-relative rotation, accumulation signals, Treasury
curve context, SEC activity, and model-generated reads. Named scans control acquisition;
opening the workspace does not silently refresh the entire market.

Model reads retain the inputs behind their assessment and conditions that would make
it wrong. The forward Ledger records supported calls for later evaluation. Its original
call history keeps its scoring rules; chart forecasts have their own cohort and results.

The optional economic calendar uses Trading Economics. It needs a configured API key;
without one it displays a setup state. [Calendar configuration →](INTEGRATIONS.md#economic-calendar)

### Formula symbols and comparisons

Open expressions such as `VOO/GLD`, `(VOO + GLD) / 2`, or `0.6 * VOO + 0.4 * TLT`
from Market search. Formula charts evaluate split-adjusted closes on shared timestamps.
They do not fabricate OHLC candles or inherit issuer-only evidence.

An asset's indexed comparison can include up to five additional symbols or formulas.
Series rebase to zero at the selected range's first usable observation, and the URL
retains the comparison for reloads and sharing.

### Scans and technical alerts

Define asset baskets, linked watchlists, exclusions, data sources, and schedules.
Preview scope and expected source work before a manual scan. Focused scans keep their
own results without replacing the broad-market briefing.

Alerts reuse the indicator registry's calculations on completed daily, weekly or monthly
US-equity candles. The indicator bell carries its settings into the alert editor.
Rules support one-shot or repeating events, with recorded crossings in Pulse. Optional
Telegram delivery has explicit per-rule consent and delivery receipts.

![Technical alert editor — synthetic demonstration data](imgs/market-alert-editor.png)

Build the frontend before starting background alerts: its build also creates the
headless Node evaluator. Telegram uses `COPNET_TELEGRAM_BOT_TOKEN` and configured
Messaging destinations. An optional `COPNET_PUBLIC_URL` supplies a private,
device-reachable origin for ticker links; credentials do not belong in those URLs.

### Quotes and portfolio context

An open ticker can subscribe to Yahoo's price stream, with vendor time and availability
shown in the asset bar. Quotes may be delayed. Leaving the ticker or hiding the tab
closes the subscription. Live quotes do not rewrite historical candles or trigger
completed-candle alerts.

The optional Webull integration reads account information; it does not place, modify,
or cancel orders. Portfolio context for supported model reads is opt-in and uses a
separate sanitized projection. [Read-only broker setup →](INTEGRATIONS.md#webull-portfolio-sync-read-only)

### On your phone

Chart and companion switch between full-width views. The composer keeps model, detail,
and annotation controls compact, with additional settings in a popover. The Market
workstation uses stacked sections while keeping desktop layout preferences separate.
Private access from another device is available through Tailscale.

<img src="imgs/market-chart-agent-mobile.png" width="390" alt="Mobile chart-agent conversation with compact controls and context inspection" />

*Synthetic chart conversation.* [Private mobile setup →](STARTUP.md#6-recommended-production-ish-baseline)

## Agent workspace

### Persistent sessions and tools

General sessions live in **Agents**, with streaming conversations, attached tools,
artifacts, archive/restore, and Markdown export. After first send, provider, profile,
persona and workspace remain bound to the session. You can explicitly change the model
within that provider or adjust Access; each run records what it used.

Profiles describe behavior. Access controls authority. Tool availability and execution
still depend on the provider and model, so a successful chat is not proof that every
tool is supported. See [session semantics](SESSION-CONTINUITY.md).

### Fleet rooms

Fleet supports durable rooms with independent OpenAI and Claude lanes. An `@everyone`
message gives both lanes the same room snapshot and holds peer responses until both
attempts finish. Follow up with a specific provider to question an answer. Responses
and tool receipts retain attribution.

![Fleet room with independently attributed answers](imgs/fleet/fleet-room.png)

### Observability

Inspect the evidence behind a run: provider/model identity, tool arguments and retained
results, final output, and lifecycle trace. Debug capture adds model-input and detailed
tool snapshots for subsequent runs. Information the provider did not expose stays
unavailable; a provider reasoning summary is not presented as a complete internal trace.

![Run inspector — synthetic demonstration](imgs/copenet-observability-run-inspector.jpg)

See [tracing](TRACING.md) and [debugging](DEBUGGING.md).

### Personalization and experiments

Personas use editable Markdown identity files. Memory and profile context support
continuity, and local knowledge sources can be configured without requiring the
creator's personal library. Media/web ingestion and labs provide additional places to
experiment; these have differing levels of maturity.

Home is a workspace overview. Workflows and Data & Tools remain direction-setting
sections. They should not be read as finished workflow automation or integration
products. The strongest current entry points are Market, Agents, and Observability.

## Extending the platform

Business logic and run lifecycle live in `src/copenet/core/`. Provider adapters translate
runtime-specific APIs; the React workspace connects through the host. External apps can
use WebSocket RPC or the REST + SSE lane.

Start with the [architecture](ARCHITECTURE.md), [app API](APP-API.md), and
[contributor guide](../AGENTS.md). When adding Market data or actions, declare their
[chart-agent exposure](initiatives/chart-agent/CONTEXT_AND_TOOLS.md) explicitly.
