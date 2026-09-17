# CopeNet Feature Glossary

This glossary is the detailed product tour for CopeNet. The main README stays focused on the product, installation, and the six canonical product images.

## Operator workspace

### Access

Each session has an explicit permission level: **Read-only**, **Ask**, or **Full Access**. Read-only permits repository reads and a safe shell allowlist. Ask pauses commands that need approval. Full Access permits writes and unrestricted user-level shell commands for trusted providers. The selected model and Access can change between turns without hiding which runtime handled each run.

### Agents Console

Agents combines persistent conversations with visible runtime state. The console shows the provider, model, profile, persona, workspace, Access, connection state, and recent tool activity. Operators can attach tools to one turn, copy or export conversations with tool evidence, archive sessions, and create a separate debug session.

Runs continue while the browser is closed if the host remains active. Reopening the session restores the partial answer and resumes the stream. Desktop and mobile views preserve manual scroll position until the operator returns to the latest output.

### Artifacts and tool evidence

Tool calls appear as one grouped block per turn. Each action has a compact result preview and an inspector with arguments, policy decisions, evidence roles, and the retained full output when an artifact exists. This keeps the conversation readable without hiding what the agent did.

### Data & Tools

Data & Tools is the home for imported assets, source material, tool surfaces, and structured inputs that can support later runs. The section is still a direction-setting shell rather than a complete operator workflow.

### Experiments

Experiments compares behavior across provider and model combinations. It is useful for evaluating response quality, latency, tool behavior, and prompt-following drift.

### Fleet Rooms

Fleet is a durable multi-model room inside Agents. An `@everyone` message sends the same room snapshot to ChatGPT and Claude, holds both answers behind an independent-first reveal barrier, and then commits attributed answers and tool receipts. Direct `@chatgpt` and `@claude` follow-ups let one lane challenge the other without merging their identities.

See [Fleet Rooms](plans/FLEET_ROOMS.md).

### Home

Home is the operator launchpad. It summarizes active sessions, provider health, tools, recent activity, system health, quick actions, market context, and NASA's Picture of the Day.

### Observability

The run inspector reconstructs one model turn from durable records. It exposes the effective model input, provider and model metadata, reasoning provenance, tool arguments and results, the final response, and the raw trace. The Usage view aggregates provider-reported token data without inventing missing values or subscription costs.

See [Observability](plans/OBSERVABILITY.md) and [Tracing](TRACING.md).

### Personas and profiles

Personas give each runtime an explicit, editable identity backed by plain Markdown files such as `SOUL.md`, `IDENTITY.md`, and `USER.md`. Profiles provide the base behavior prompt. Access remains a separate permission axis, so a personality choice does not silently grant more authority.

### Sessions

Sessions persist transcripts and runtime history. The first send locks the provider, profile, persona, and workspace. The operator can change the model within the same provider and can change Access for a later turn. Every run records the provider and model that produced it.

See [Session Continuity](SESSION-CONTINUITY.md).

### Workflows

Workflows is the home for focused operator surfaces that deserve more structure than a conversation pane. It is currently a direction-setting shell.

## Market workspace

### Alerts

Technical alerts reuse the chart indicator implementation for completed daily, weekly, and monthly US-equity candles. Rules can observe a crossing, a first interaction with a forming candle, and the later close result. Each rule has explicit delivery consent, durable receipts, and optional cached-position context.

Chart-created price alerts let the operator place a level directly on the candlestick chart and arm a daily-close crossing rule. Linked scans acquire the data and evaluate the rule; opening a browser quote does not trigger it.

See [Market Sentinel Alerts](plans/MARKET_SENTINEL_ALERTS.md).

### Asset comparison and formula symbols

The ticker workspace accepts ordinary symbols and safe formulas such as `VOO/GLD` or `0.6 * VOO + 0.4 * TLT`. Formula charts align split-adjusted closes on shared timestamps. Comparison mode can rebase as many as five symbols or formulas to zero at the first usable observation in the selected range.

### Chart agent

The chart agent receives a frozen observation of the candles, indicators, quote, research panels, and selected context that were visible when the operator sent the message. It can create evidence-linked levels, zones, trendlines, and labels. Operators can inspect the exact context, edit or hide drawings, and exclude account data by default.

### Economic calendar

The morning brief can show the next seven days of medium- and high-impact United States releases. The host reads Trading Economics with `TRADING_ECONOMICS_API_KEY`, caches successful responses for 15 minutes, and keeps the last good snapshot during temporary failures. The credential never reaches the browser.

### Financial-series overlays

Ticker charts can layer quarterly, trailing-twelve-month, or annual revenue over split-adjusted price. Historical P/E uses the diluted EPS that was public on each date and leaves genuine gaps when earnings are non-positive, stale, or unsupported.

See [Financial Series](plans/FINANCIAL_SERIES.md).

### Live quotes

A visible ticker workspace can subscribe to Yahoo's price stream. The asset bar shows the last price, vendor time, market session, and reported day volume. The subscription closes when the operator leaves the ticker or hides the browser tab. Live quotes never rewrite canonical candles or trigger completed-candle scans.

### Market briefing

The Market landing page is a sectioned workstation built around a short daily read. It combines watchlists, SEC evidence, sector rotation, accumulation signals, macro context, and explicit falsification conditions. Model calls enter a forward ledger so later outcomes can score the original claims.

See [Market Monitor](plans/MARKET_MONITOR.md) and [Market Design Philosophy](plans/MARKET_DESIGN_PHILOSOPHY.md).

### Position context

A held equity can show an average-cost line, snapshot profit or loss, and optional fill markers. Price scenarios use current shares and average cost without pretending to reconstruct historical account value. Account context is opt-in and hidden during replay and comparison views.

### Scans

Scans own broad market-data acquisition. Each saved definition has an asset scope, exclusions, source plan, schedules, and immutable run history. Manual runs preview the exact scope and require confirmation. Missed schedules do not catch up during application startup.

### Screeners

Screeners discover candidates through bounded TradingView observations. The built-in setups cover compression, leader pullbacks, oversold large caps, breakdown watches, and volume expansion. Results are delayed research filters, not probabilities or canonical candle data.

See [Market Screeners](plans/MARKET_SCREENERS.md).

### Ticker workspace

Each symbol opens a reloadable `/market/{symbol}` workspace with the price chart in command. It combines identity, quote provenance, interval and range controls, split-adjusted history, SEC events, financial overlays, alerts, position context, and a research dock. The benchmark view separates raw return, benchmark return, beta, and beta-adjusted residual.

### Treasury curve

The macro workspace charts official United States Treasury Constant Maturity rates for 3-month, 2-year, 5-year, 10-year, and 30-year maturities. It also shows curve movement and the 10Y–2Y and 10Y–3M spreads from one aligned observation date.

### Webull portfolio sync

The Webull integration is read-only. It can sync balances, positions, and filled-order aggregates, then prepare an optional sanitized context pack for market model reads. Credentials and tokens stay outside model inputs and logs. No order placement, modification, or cancellation exists.

See [Webull API Surface](plans/WEBULL_API_SURFACE.md).

## Inputs and integrations

### Knowledge bases

CopeNet can index curated local Markdown sources for creative and research workflows. Public configuration uses `config/knowledge-sources.example.toml`; local paths belong in the ignored `config/knowledge-sources.local.toml` file.

See [Knowledge Bases](KNOWLEDGE-BASES.md).

### Media imports

Media workflows support URL and audio ingestion, transcription, and session-scoped asset storage. Remote use remains compatible with private Tailscale access.

### Telegram delivery

Market alerts can send one chart image and caption through configured Messaging destinations. Delivery requires explicit per-rule consent and preserves uncertain receipts instead of silently sending a duplicate.

## The Custodian

The Custodian is CopeNet's append-only night-shift mascot. His badge says `ACCESS EVERYWHERE`; his patch says `DON'T WRITE. DELETE.` He carries the keys, a rubber duck, and an unreasonable amount of responsibility for clean worktrees.
