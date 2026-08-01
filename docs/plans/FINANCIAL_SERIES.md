# Financial-series overlays

## Outcome

CopeNet now has one canonical financial-series path shared by chart overlays,
WebSocket RPC, and the `market.financials` agent tool. Revenue is the first metric.
It supports quarterly, annual, and TTM views; reported-only or canonical bases;
filing-date point-in-time queries; range filters; provenance; and explicit quality
warnings.

The normalization and storage engine lives in CopeTech-Edgar. CopeNet owns the
product boundary and visualization:

```text
SEC Company Facts
  -> metric-specific fact extraction
  -> accession-keyed SQLite facts
  -> point-in-time window resolution
  -> Q4 / TTM derivation
  -> CopeNet financial-series boundary
       -> market.financial.series.get
       -> market.financials
       -> ticker overlay
```

## Audit findings

The prior revenue overlay was not limited because SEC history was unavailable.
Company Facts contained the history, but the old path:

- selected one concept for an issuer's whole history instead of stitching
  concepts per economic period;
- truncated raw rows before deduplicating comparative repeats;
- grouped by formatted fiscal/calendar labels rather than economic windows;
- could select the smaller conflicting value and discarded filing/accession
  provenance;
- treated SEC calendar frames as issuer fiscal quarters;
- had no explicit amendment or point-in-time policy;
- omitted standalone Q4 and therefore held Q3 for roughly six months; and
- plotted at period end, which introduced lookahead.

For example, canonical residuals recover NVDA FY2025 Q4 as
`$130.497B - $91.166B = $39.331B`, NVDA FY2026 Q4 as `$68.127B`, and
GOOGL FY2025 Q4 as `$113.829B`.

## Data contract

Every observation carries:

- economic identity: metric, frequency, period start/end, unit, fiscal metadata;
- availability identity: filing date and `alignedAt`;
- value semantics: reported/derived, derivation text, confidence, quality flags;
- provenance: taxonomy, concept, form, filing date, accession, frame, SEC URL.

Raw normalized facts are persisted rather than only caching presentation rows.
That preserves enough evidence to re-run normalization rules without reacquiring
every filing. Company Facts snapshots refresh daily. A failed refresh may fall
back to persisted facts only with an explicit warning.

Resolution uses actual duration windows: roughly 70–110 days for quarters and
330–400 days for annual facts. Concepts are ranked by the metric registry but
resolved independently per window. Comparative repeats are deduplicated; later
amendments win; the earliest filing carrying the selected value remains its
availability date.

Canonical Q4 is derived only when one annual value and three compatible
standalone quarters exist. TTM is the sum of four contiguous canonical quarters.
All contributors remain attached as sources.

## Point-in-time semantics

Price overlays must use `alignment=availability`. A fact affects the chart on the
date the filing made it public, never on the fiscal period end. `asOf` excludes
facts filed after the requested date, including later amendments. Period-end
alignment remains available for accounting analysis and exports but is unsafe for
backtests unless the caller separately applies an availability lag.

The frontend keeps loading, unavailable, stale/error, and loaded states distinct.
It guards against symbol-switch races, caches complete request keys, and does not
reset chart zoom when the overlay or frequency changes. If one filing makes
several comparative observations available on the same day, the step plot uses
the newest economic period for that timestamp while the API retains every row.

## Source strategy

SEC Company Facts is the canonical open source for reported US issuer history: it
is free, auditable, and accession-backed, but it requires normalization and has no
analyst estimates. Filing-level XBRL is the next fallback for missing or
low-confidence Company Facts periods.

yfinance's valuation-measures endpoint can supply convenient historical P/E and
related vendor-normalized fields. Its history is comparatively short and its
transformation/provenance are opaque, so it is useful as an optional display lane
or cross-check—not as the sole denominator in a reproducible open series. Paid
vendors remain appropriate for estimates, broader international coverage,
restatement support, and service guarantees.

## Metric roadmap

The registry currently contains USD revenue duration facts. Next additions should
reuse the same observation and provenance contract:

1. gross profit, operating income, net income;
2. operating cash flow, capital expenditure, free cash flow;
3. diluted EPS and clearly distinguished diluted/basic/period-end share counts;
4. trailing valuation metrics using split-adjusted price and point-in-time TTM
   denominators; and
5. forward valuation metrics only after adding timestamped consensus estimates.

Historical trailing P/E is not market cap divided by revenue and does not require
revenue per share. It is either split-adjusted price divided by point-in-time TTM
diluted EPS, or market cap divided by TTM net income using a consistently dated
share count. Negative or near-zero earnings need an explicit unavailable policy.

## Current limitations

- Revenue is USD-only and Company Facts-only.
- No filing-level XBRL fallback or estimate source is implemented yet.
- Conflict flags identify disagreement but do not yet include a materiality score.
- Filing timestamps are day-granular; same-day market-session timing is not yet
  modeled.
- The legacy fundamentals response remains for compatibility. New clients should
  use the canonical RPC/tool.

Validation covers concept stitching, comparative-repeat deduplication, amendments
under `asOf`, Q4/TTM derivation, persisted fallback, RPC/tool shape parity, and
live GOOGL/NVDA history. Browser verification covers NVDA quarterly/TTM/annual
switching, provenance/status display, the filing-date step line, and a clean
console.

## Review findings, 2026-07-31

Independent review of the shipped overlays. The accounting core verified clean
against real filings — AAPL FY2025 `$7.46`, NVDA FY2025 `$2.94`, and GOOG FY2021
`$5.61` (the reported `$112.20` across a real 20:1 split) all match as-filed, and
`availableAt` correctly resolves to the first filing that carried a value rather
than the latest restatement. The defects are around it, not in it.

Open, ranked:

1. **Historical P/E divides total-return prices by split-only EPS.** The valuation
   path fetches `auto_adjust=True`, which is splits *and* dividends, then labels it
   `price_basis="split_adjusted"` — a guard satisfied by a string, not by the actual
   basis. Measured understatement at the 10-year edge: XOM 35%, KO 27%, AAPL 8%,
   NVDA 2%, decaying to zero at the right edge, so it renders as a de-rating that
   never happened. Fixed by the split-only basis in `docs/plans/PRICE_CACHE.md`.
2. **Overlay time domains are unbounded.** P/E is hardcoded to 10y weekly and
   revenue to full SEC history regardless of the selected D/W/M candle window.
   Lightweight Charts' axis is index-based, so every unique timestamp across all
   series takes one equal-width slot: pre-candle quarterly revenue compresses into
   the width of ~45 weekly bars, and overlay points landing on filing dates rather
   than candle dates *inject* new slots, corrupting the `barSpacing` the SEC cluster
   boxes use for their width. Fix is candle-master: max-history candles plus
   forward-snapping every overlay point onto a candle timestamp.
3. **Cluster boxes never recompute on price-axis changes.** Recompute is wired to
   the visible *logical time* range, the ResizeObserver, and data effects. Nothing
   fires on a vertical rescale — price-axis drag, vertical pan, autoscale shift, or
   the log/linear toggle, which applies the mode without recomputing. The boxes are
   absolutely-positioned HTML at `priceToCoordinate` pixels, so candles move and
   boxes do not. Lightweight Charts v5 exposes no price-scale subscription; a rAF
   sampler over a reference coordinate is the available fix.
4. **`buildBuckets` bounds evidence above but not below.** Anything older than the
   first candle snaps onto it. Latent while the evidence window (180 days) stays
   shorter than every candle window; live the moment `daysBack` is raised.
5. **Diluted-share coverage gates interim TTM EPS.** GOOG has 34 quarterly EPS
   observations but only 10 quarterly diluted-share observations, all from Oct 2024.
   TTM reconstruction needs share counts on all three bridge windows, so before 2025
   only annual 10-K EPS survives — 14 usable points in 10 years. The 180-day
   staleness rule then blanks the rest, producing the ~6-months-on/6-months-off P/E
   gaps. Widen the concept list the way `diluted_shares` already accepts
   `WeightedAverageNumberOfShareOutstandingBasicAndDiluted`; note `diluted_eps` has
   no matching `EarningsPerShareBasicAndDiluted` entry, which is an asymmetry rather
   than a basic-EPS fallback and silently excludes issuers using the combined tag.
6. **`GOOGL` resolves to nothing while `GOOG` works.** Ticker-to-CIK resolution
   drops one of Alphabet's two tickers.
7. **No flag for one-off earnings.** GOOG Q2 2026 diluted EPS was `$9.11` against
   `$2.31` a year earlier and AMZN `$5.75` against `$1.68`, both as-filed. TTM EPS
   roughly doubles and the P/E collapses — correct arithmetic that reads to a human
   as the stock getting cheap when the denominator spiked. A discontinuity flag on
   TTM EPS moving more than ~40% in one quarter would mark these for review.
8. **Two live financial paths.** `market.ticker.fundamentals.get` still exists in
   the backend with a client function in `wsMarketRpc.ts`, though no market component
   calls it. Orphaned frontend code over a live backend path.

Revenue values spot-checked correct (AMZN Q2'26 `$200.61B`, GOOG Q2'26 `$119.80B`,
NVDA Q1 FY27 `$81.61B`). The revenue concept registry has no bank/fintech
total-revenue concept, so issuers reporting under a custom total-revenue tag will
understate.
