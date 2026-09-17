# CopeNet visual state catalog

Only the entries marked **Fresh** below are current synthetic visual evidence. Several
historical baseline images contain operator-specific data and are unsafe to publish. Do not
add another screenshot from a live operator workspace, portfolio, destination list, or
transcript. Replace or remove unsafe baselines only as an explicit sanitization task.

The catalog distinguishes fresh evidence from a historical baseline. A baseline image is
useful for product orientation but is not proof that the current UI still renders the same.
Run the named verifier before promoting a baseline image to fresh evidence.

## Fresh on 2026-09-16

| Surface | State | Viewport | Image | Evidence |
| --- | --- | ---: | --- | --- |
| Agents | streaming, follow/pause/reopen | 1440px | [agents-streaming-1440.png](agents-streaming-1440.png) | `uv run python scripts/verify_chat_streaming.py` passed |
| Agents | streaming, follow/pause/reopen | 390px | [agents-streaming-390.png](agents-streaming-390.png) | `uv run python scripts/verify_chat_streaming.py` passed |
| Market screeners | results, empty, error, reload, handoff, overflow | desktop + 390px | [market-screeners.png](market-screeners.png) | `uv run python scripts/verify_market_screeners.py` passed |
| Chart forecasts | published forecast and overlay | desktop | [market-chart-forecasts.png](market-chart-forecasts.png) | Visual frame captured; verifier has fixture-contract failures |
| Chart forecasts | forecast layout | 390px | [market-chart-forecasts-mobile.png](market-chart-forecasts-mobile.png) | Visual frame captured; verifier has fixture-contract failures |
| Chart forecasts | scored outcome | desktop | [market-forecast-outcome.png](market-forecast-outcome.png) | Visual frame captured; verifier has fixture-contract failures |
| Chart forecasts | ledger/evidence | desktop | [market-chart-forecasts-ledger.png](market-chart-forecasts-ledger.png) | Visual frame captured; verifier has fixture-contract failures |

## Historical baseline: operator shell — unsafe until sanitized

| Surface | Primary state | Image |
| --- | --- | --- |
| Home | populated operator desk | [copenet-home-dashboard.png](copenet-home-dashboard.png) |
| Agents | console | [copenet-agents-console.png](copenet-agents-console.png) |
| Agents | tool attachments | [agent-tool-attachments.png](agent-tool-attachments.png) |
| Agents | access permissions | [copenet-access-permissions.png](copenet-access-permissions.png) |
| Data & Tools | hub | [copenet-data-tools.png](copenet-data-tools.png) |
| Data & Tools | persona home | [copenet-persona-home.png](copenet-persona-home.png) |
| Workflows | shell | [copenet-workflows.png](copenet-workflows.png) |
| Experiments | matrix | [copenet-experiments-matrix.png](copenet-experiments-matrix.png) |
| Observability | run explorer | [copenet-observability.png](copenet-observability.png) |
| Observability | run inspector | [copenet-observability-run-inspector.jpg](copenet-observability-run-inspector.jpg) |
| Fleet | room | [fleet/fleet-room.png](fleet/fleet-room.png) |

## Historical baseline: Market workstation — unsafe until sanitized

| Surface | State | Image |
| --- | --- | --- |
| Market | briefing landing | [market-briefing.png](market-briefing.png) |
| Market | ticker workspace | [market-ticker-workspace.png](market-ticker-workspace.png) |
| Market | live quote, wide/medium/narrow | [ticker-live-quote-1440.png](ticker-live-quote-1440.png), [ticker-live-quote-1100.png](ticker-live-quote-1100.png), [ticker-live-quote-390.png](ticker-live-quote-390.png) |
| Market | loading workstation/ticker | [market-workspace-loading.png](market-workspace-loading.png), [ticker-workspace-loading.png](ticker-workspace-loading.png) |
| Market | scans and alert editor | [market-scans-alerts.png](market-scans-alerts.png), [market-scans-editor.png](market-scans-editor.png), [market-alert-editor.png](market-alert-editor.png) |
| Market | scan compact/mobile | [market-scans-compact.png](market-scans-compact.png), [market-scans-mobile.png](market-scans-mobile.png) |
| Market | chart agent and mobile controls | [market-chart-agent.png](market-chart-agent.png), [market-chart-agent-mobile.png](market-chart-agent-mobile.png), [market-chart-mobile-zoom.png](market-chart-mobile-zoom.png) |
| Market | evidence/signals mobile | [market-mobile-evidence.png](market-mobile-evidence.png), [market-mobile-signals.png](market-mobile-signals.png) |
| Market | position | [market-position.png](market-position.png) |

## Historical baseline: ticker detail panels — unsafe until sanitized

- [Asset workspace](market-panel/copenet-asset-workspace.png)
- [Watchlist and macro](market-panel/copenet-market-watchlist-macro.png)
- [Financial overlays](market-panel/copenet-financial-overlays.png)
- [Price alert](market-panel/copenet-price-alert.png)
- [Asset comparison](market-panel/copenet-asset-comparison.png)
- [Formula symbol](market-panel/copenet-formula-symbol.png)
- [Financial-series overlay](market-panel/copenet-financial-series-overlay.png)
- [Ledger evidence](market-panel/copenet-market-ledger-evidence.png)
- [Treasury curve](market-panel/copenet-treasury-curve.png)
- [Rotation / accumulation](market-panel/copenet-market-rotation-accumulation.png)
- [Why this read](market-panel/copenet-market-why-this-read.png)
- [Mobile chart toolbar](market-panel/copenet-mobile-chart-toolbar.png)

## Capture gaps and blockers

See [UI state audit](../UI_STATE_AUDIT_2026-09-16.md) for the full state matrix, audit
findings, and the capture commands that currently fail. Do not use a stale baseline image
to close one of those gaps.
