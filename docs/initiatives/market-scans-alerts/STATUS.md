# Status

## Authorized and implemented in the initial safety pass

- Default morning time is 09:45 operator-local; valid explicit environment overrides remain.
- Startup waits for a strictly future scheduled slot, regardless of missing/stale briefs.
- A slot missed by more than 60 seconds of event-loop delay (e.g. machine sleep) is skipped.
  A failed full sweep waits for the next scheduled slot instead of retrying the whole job.
- Dashboard and briefing mount/reload paths only read stored state. No automatic full
  refresh on empty/error dashboard or missing/stale brief. Manual controls remain available.
- Existing price-alert evaluation rejects forming candles using US-equity close availability
  AND cache-fetch time, and does not evaluate a close that predates alert creation.
- Extracted dashboard/brief hooks before changing the oversized aggregate hook file;
  shared the conservative daily-close availability rule with ledger reporting.

## Implemented after build approval

- Named scans persist explicit universes/watchlists/direct symbols/exclusions, independent
  source choices, multiple times, weekdays, timezone, enabled state and revisions. Environment
  time is migrated once; persisted configuration owns future edits.
- Scans & alerts is a Market destination with Scans, Alerts and Activity views, read-only
  next-run chrome, scope/cache preview, temporary editors, and mobile single-scroll sheets.
- Per-root cross-process acquisition lease, same-slot queued work/cache reuse, bounded
  pacing, scoped run snapshots, compact history and lazy full results. SEC-only jobs never
  acquire Yahoo prices. Missing linked lists block rather than widen scope.
- Full dashboard acquisition was extracted from projection. Partial price failures preserve
  the prior coherent dashboard with stale status, rather than publishing a fresh false brief.
- Canonical AlertRule replaces price-only persistence with one-time migration. Chart-created
  price rules are projections of the same store. Price/SMA/EMA/RSI/MACD support D/W/M
  US-equity exchange sessions, holiday/early close/DST boundaries, baseline establishment,
  gaps/splits/revisions, repeat/one-shot behavior, immutable events and revision/candle dedupe.
- A generated Node evaluator imports the chart registry; no second formula implementation.
  It shares the chart’s daily history window and full weekly/monthly history. The wheel
  includes its generated bundle. Missing Node/bundle is an actionable unavailable state.
- Telegram has a real adapter, explicit per-rule consent, existing destination/blocklist
  policy, durable outbox, receipts, approval, retry and uncertain-send acknowledgement.
  No test sends or live scans were used in verification.

## Verification — completed build

- 344 Market backend, notification RPC and host integration tests pass, including scheduler, source isolation,
  close/calendar gating, indicator parity, revisions, partial results and outbox regressions.
- Frontend typecheck/build and all 492 frontend tests passed.
- `uv run python scripts/verify_market_passive_load.py`: isolated browser regression for
  empty, stale, and offline initial loads, navigation, reload, and opening scan controls.
  All network is intercepted; no operator data, Yahoo requests, or Telegram messages.
- `uv run python scripts/verify_market_monitoring.py`: UI → real RPC → isolated stores:
  named SEC scan creation, exact preview, one scoped synthetic acquisition, weekly alert
  creation/pause/re-arm, lazy run detail, persistence/reload, Escape/focus restoration,
  1440/1100/390 viewport geometry and one-scroll mobile editor.
- Screenshot frames are synthetic and checked for operator data. Wheel inspection confirms
  the generated evaluator is packaged. Python compile smoke passes.
- Build before backend tests, not concurrently: Vite replaces the distribution directory,
  including the generated evaluator, during a production build.

## Boundaries / operator verification

- Existing ticker/watchlist/calendar/rates data-on-demand behavior remains. This initiative
  prevents hidden **full sweeps**, not every external request made elsewhere in Market.
- Scan source-work estimates are not promises of exact HTTP request counts. Initial history,
  SEC adapters and upstream throttling can require multiple requests per asset/source.
- Linked watchlists use canonical names today; rename/delete blocks affected scans until
  explicitly repaired. Run snapshots retain the exact old inclusion reasons and assets.
- Alerts currently support US-listed equity/ETF sessions only, D/W/M, and the first four
  chart indicators. Intraday, crypto sessions and arbitrary compound rule expressions wait.
- Source results currently expose structured evidence in a lazy inspector. A richer research
  presentation for every provider can follow without changing acquisition or persistence.
- Actual Telegram delivery requires operator verification with the explicit Test action;
  credentials and recipients were not inspected. Ambiguous sends can duplicate only after
  the operator explicitly acknowledges that risk and retries.
- Genuine chart level placement/pan behavior needs visible operator testing. Automated checks
  validate DOM, wiring, persistence and calculations, not hidden-pane repaint behavior.
- Existing unrelated compatibility shim found: MarketStore dashboard rehydration monkey-patches
  a serializer instead of filling all DTO panels. This initiative does not extend that shim.
