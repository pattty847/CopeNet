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

The current schedule is still daily, operator-local, and environment-configured. A visible
timezone-aware scan editor, source budgets, durable per-scan runs, D/W/M indicator alerts,
and outbound Telegram delivery are **shaped, not built**. See VISION.md.

## Verification

- 246 Market backend unit tests passed, including scheduler, brief, price-alert, and
  ledger-baseline regressions.
- Frontend typecheck/build and all 484 frontend tests passed.
- `uv run python scripts/verify_market_passive_load.py`: isolated browser regression for
  empty, stale, and offline initial loads, navigation, reload, and explicit scan actions.
  All network is intercepted; no operator data, Yahoo requests, or Telegram messages.

Remaining known scope: ordinary ticker/watchlist/calendar/rates data-on-demand behavior
still exists. This safety pass stops **implicit full sweeps**, not every external request.
The conservative daily-close boundary waits until 16:00 New York on early-close days;
the full alert initiative needs supported-market calendars and per-candle provenance.
