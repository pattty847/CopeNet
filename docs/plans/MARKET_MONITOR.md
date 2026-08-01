# Market Monitor

Market Monitor is CopeNet's slow-timeframe market radar. The public repository contains only
account-neutral market architecture and synthetic examples. Personal holdings, cost basis,
watchlists, fills, account balances, and portfolio preferences are local operator data.

## Public architecture

- `core/market/universe.py` contains broad market, macro, and sector references only.
- `WatchlistStore` persists user-curated lists beneath the operator's local CopeNet data root.
- `core/market/webull/` reads credentials from ignored environment files and persists sanitized
  broker snapshots beneath the local CopeNet data root.
- Portfolio panels and ticker-position joins are populated only from the local broker snapshot.
  There is no source-controlled cost-basis fallback.
- Price bars remain split-adjusted, and financial overlays align to filing availability dates.

## Privacy boundary

Never commit or publish:

- broker keys, secrets, access tokens, account identifiers, or SDK token files;
- holdings, quantities, average costs, balances, fills, realized/unrealized P&L, or account-derived
  watchlists;
- screenshots, traces, fixtures, or audit prose copied from a live account;
- a person's name, email, local filesystem username, or other personal profile data.

Tests and screenshots must use clearly synthetic values. Live probes may validate behavior, but
their raw output belongs under the ignored local data root or `docs/private/`, never in tracked
documentation.

## Product behavior

The dashboard combines public market references with local watchlist and broker data at runtime.
Read-only market tools expose the same sanitized runtime shapes. Broker trade execution remains out
of scope; the Webull lane is read-only.

Detailed operator-specific planning notes live in the ignored
`docs/private/MARKET_MONITOR.private.md` file when present.
