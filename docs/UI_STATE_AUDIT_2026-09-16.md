# UI state audit — 2026-09-16

## Scope and evidence standard

This audit maps the operator workflow from first arrival through market research, agent
work, evidence inspection, and supporting sections. Images live in the
[visual state catalog](imgs/INDEX.md). Every committed image must use synthetic data.

"Every state" has a practical boundary: it means every named product state and transition
that can be reached from the UI, not every possible value, timestamp, model answer, or
combination of user data. The state matrix below is the capture contract for the product.

## Current capture matrix

| Journey | Required states | Current evidence | Status |
| --- | --- | --- | --- |
| App shell | connected, connecting, disconnected, light/dark, expanded/collapsed nav, narrow nav | historical shell images only | missing current capture |
| Home | first-run setup, populated desk, empty market read, provider issue, quick-launch handoff | populated baseline only | partial |
| Market workstation | briefing, structure, signals, portfolio, evidence, ledger, backtest, screeners, scans; loading, empty, error | historical coverage plus fresh Screeners | partial |
| Ticker workspace | standard, loading, quote reconnect, chart controls, detail tabs, drawer, position opt-in, alert editor, agent, forecast, replay, comparison | historical coverage; fresh forecast frames | partial |
| Agents | draft, locked session, streaming, paused, completed, tool rows, tool inspector, approval, archived/restore, narrow layout | fresh streaming at 1440px/390px | partial |
| Observability | no runs, list selected, run inspector, trace loading/error, debug capture, usage empty/populated | historical inspector images only | missing current capture |
| Data & Tools | hub, source import, media URL, media audio, web import, persona, memory, messaging, permissions; empty/loading/error | historical hub/persona only | partial |
| Workflows | entry shell, Meme Lab empty/generating/result/Agents handoff | historical shell only | missing current capture |
| Experiments | no data, populated matrix, filters, detail handoff | historical populated matrix only | partial |
| Global overlays | command palette, account menu, mobile sheet, section error boundary, confirmation/approval | no dedicated evidence | missing |

## Findings

### P0 — Existing documentation screenshots expose operator-specific data

The visual baseline includes an operator name, a local workspace path, live session activity,
and market/account context. The current repository instructions prohibit that material in
documentation screenshots. These images must not be copied to a public surface or treated as
sanitized fixtures.

Impact: a documentation refresh could disclose private operator data. Replace each affected
image through an isolated synthetic fixture, then remove the unsafe image in an explicitly
authorized sanitization change. The catalog labels every historical baseline as unsafe until
that work is complete.

### P1 — Market visual regression suite is broken before it can verify key workflows

`verify_market_loading.py` and `verify_ticker_live_quote.py` import
`MARKET_QUOTE_METHODS` from `copenet.host.rpc_market_quote`, but that export no longer
exists. `verify_market_monitoring.py` imports the removed
`copenet.host.rpc_market_monitoring` module. This blocks current capture of Market loading,
live quote, scan, and alert states.

Impact: the project has images for these workflows, but they cannot currently serve as
fresh regression proof. Repair the fixture imports/handler contract, then recapture all
blocked Market frames with synthetic data.

### P1 — Chart agent and forecast fixture protocols have drifted from the UI RPC surface

The chart-agent verifier made unexpected calls to `market.position.get`,
`market.intraday.intervals`, `market.alerts.list`, and `market.forecast.list`; the mocked
chat flow then failed on a missing `timeframe` field and never presented its approval
action. The forecast verifier captured its frames but failed on the same unexpected
Market RPC methods.

Impact: the chart agent's approval state and the forecast flow have no passing end-to-end
evidence. Update the isolated WebSocket fixtures to model the current startup requests and
the current provider event payload, then make the screenshot assertion contingent on a
passing flow.

### P2 — The product direction is clear in the primary navigation but weak in first-run orientation

The primary nav says Home → Market → Agents → Observability → Data & Tools. This is a good
reflection of the current product, but Home still needs current first-run and empty-state
evidence to show an operator what to do when no market read, provider, session, or source
exists. The captured populated desk cannot answer that question.

Fix: make Home's first-run state explicitly sequence setup, choose a market research path
or agent task, and explain where results become inspectable. Capture it at desktop and
narrow widths.

### P2 — Secondary destinations need an explicit role in the journey

Workflows and Experiments are intentionally removed from persistent navigation. They are
reachable through Data & Tools and the command palette, but the available visual evidence
does not prove those handoffs are discoverable or coherent. This risks reading those areas
as abandoned screens rather than deliberately secondary utilities.

Fix: show their relationship in the Data & Tools hub with outcome-focused labels and
capture the handoff and return path.

### P2 — State evidence is concentrated in the Market detail surface, not the whole product

The screenshot directory has strong historical coverage of ticker charts and Market panels,
but no current captures for command palette, account/menu, mobile sheet, errors, or most
empty states. This makes visual review biased toward the most mature screen.

Fix: create a fixture-backed gallery test that visits the complete state matrix and writes
deterministic named images. Treat the catalog as a release gate.

## Workflow model to test next

1. Home answers: is the host ready, what needs setup, and what should the operator do now?
2. Market answers: what changed, what deserves investigation, and what evidence supports it?
3. Ticker workspace answers: can the operator inspect, annotate, alert, forecast, or ask an agent from one coherent asset context?
4. Agents answers: can the operator execute a general task and inspect exactly what the harness did?
5. Observability answers: can the operator audit any run and its resource use without returning to the conversation?
6. Data & Tools, Workflows, and Experiments answer: how does an imported input or experiment become an actionable agent or market workflow?

## Verification performed

- `uv run python scripts/verify_chat_streaming.py` passed for 1440px and 390px.
- `uv run python scripts/verify_market_screeners.py` passed for synthetic desktop and
  mobile states.
- `verify_market_loading.py`, `verify_ticker_live_quote.py`,
  `verify_market_monitoring.py`, `verify_chart_agent.py`, and
  `verify_chart_forecasts.py` exposed the failures described above.

No live operator workspace was captured. The unmodified historical frames remain baseline
evidence only until their verifier passes against the current application.
