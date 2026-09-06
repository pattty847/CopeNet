# Optional integrations

[Back to CopeNet](../README.md) · [Startup guide](STARTUP.md)

These integrations are optional. Neither is required to start a chart-agent conversation.

## Economic calendar

The Market morning brief includes a compact **Next 7d** calendar for medium- and high-impact
United States releases. It uses Trading Economics' documented calendar API, converts timestamps
to the operator's local time in the browser, caches successful responses for 15 minutes, and keeps
the last successful snapshot visible if the provider is temporarily unavailable.

Add the server-side credential to the root `.env` and restart CopeNet:

```bash
TRADING_ECONOMICS_API_KEY=your-key
```

The credential never reaches the browser. Without it, the widget shows an explicit setup-ready
state rather than sample events. Calendar rows link to the official release source when the
provider supplies one; the Trading Economics calendar remains available as the source receipt.

## Webull Portfolio Sync (read-only)

CopeNet can read your actual Webull positions/balances and (optionally) hand a sanitized portfolio
context pack to the model reads. **The integration is read-only: it does not place, modify, or cancel orders.**
Model context uses a separate sanitized projection; credentials are not part of that projection.

Setup:
1. Apply for Webull OpenAPI individual access (developer.webull.com → OpenAPI Management) and create
   an App Key + App Secret. Individual developers don't need IP whitelisting.
2. Add to `.env` (gitignored): `WEBULL_KEY=…`, `WEBULL_SECRET=…` (optional `WEBULL_ENV=sandbox`).
3. `uv run copenet webull auth` — then **approve the request in the Webull app on your phone**
   (the SDK polls up to ~5 minutes). Tokens persist under `~/.copenet/data/market/webull/`.
4. `uv run copenet webull accounts` → `uv run copenet webull select --account-id <id>`.
5. `uv run copenet webull sync` — pulls balances + positions (prices enriched via yfinance;
   Webull market data is a separate paid subscription and is not required).
6. Dry-run the AI pack: `uv run copenet webull context` — prints the sanitized context pack only
   and verifies no credentials are present. Nothing is sent anywhere.
7. Opt in to model visibility: `INCLUDE_WEBULL_PORTFOLIO_CONTEXT=true` in `.env` (default **false**).
   When enabled, market/ticker model reads include the sanitized pack (masked account id only).

In the UI, the Market → Portfolio card shows its data source and a `↻ Webull` re-sync button.
`uv run copenet webull status` shows auth/token state, the selected account, and last sync.
