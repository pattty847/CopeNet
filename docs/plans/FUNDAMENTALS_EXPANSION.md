# Fundamentals Expansion — Audit & Implementation Proposal

Date: 2026-08-02
Status: Phase 1 implemented (see status section at the end)
Companion to: `FINANCIAL_SERIES.md` (existing revenue/P-E pipeline design)

## 1. Assessment of the current system

The pipeline is: SEC Company Facts → `METRIC_REGISTRY` concept chains
(`CopeTech-Edgar/src/copetech_sec/financial_metrics.py`) → append-only SQLite
fact ledger with content-hashing and normalization versioning → window
resolution keyed on actual `(period_start, period_end, unit)` durations rather
than SEC `fy`/`fp` labels → derived Q4 and TTM → CopeNet boundary
(`core/market/financials.py`) → WS RPC `market.financial.series.get` →
Lightweight Charts overlay. Point-in-time semantics (`availableAt` = earliest
filing carrying the selected value, `as_of` filtering on `filed`), amendment
handling, concept-priority stitching, and provenance are solid. Extend, don't
replace.

Load-bearing structural facts for the expansion:

- **Adding a flow metric is ~5 registry lines.** Store schema, RPC payload,
  TS types, and chart overlay are metric-agnostic. `aggregation="sum"` metrics
  inherit quarterly/annual/derived-Q4/TTM for free.
- **Balance-sheet (instant) facts are currently impossible.**
  `_normalize_raw_fact` (`financial_series.py:164-172`) drops any fact without
  a `start`; the resolver only accepts 70–110 / 330–400-day durations;
  `MetricDefinition.fact_type` is never read. Net debt, equity, working
  capital, shares-outstanding-at-date all need an instant-fact branch.
- **YTD cash-flow facts are dropped.** Verified empirically against cached
  AAPL Company Facts: income-statement concepts (OperatingIncomeLoss,
  ResearchAndDevelopmentExpense, GrossProfit) have discrete-quarter windows
  for all four fiscal quarters, but cash-flow-statement concepts (OCF, capex,
  SBC, D&A) are discrete only for fiscal Q1 — Q2/Q3 exist only as 6M/9M YTD
  windows. Quarterly/TTM OCF-family metrics require a YTD-differencing
  derivation (Qn = YTDn − YTDn−1). Annual values work today.
- **No cross-metric arithmetic layer exists.** Every composite (FCF, margins,
  ratios) needs a derived-series module. The TTM aggregator's pattern
  (availableAt = max, confidence = min, flags = union) is the right template.
- **Prices/market cap live entirely in CopeNet** (split-adjusted-only
  `PriceCache`, yfinance). The valuation engine takes caller-supplied prices.
  Correct division of labor — keep it.

Weaknesses NOT to copy into new series:

1. Summary-card P/E divides a TOTAL_RETURN price by split-only EPS
   (`runtime.py:783-789`) — the basis bug already fixed in the overlay path.
2. `diluted_eps` has one concept; `EarningsPerShareBasicAndDiluted` filers get
   no P/E. New chains get fallbacks from day one.
3. Agent tool enum (`market_financials.py:75`) hardcoded to `["revenue"]`;
   UI metric buttons hardcoded to two. Both must become registry-driven.
4. Overlay payload discrimination by `'epsMetric' in data` key-sniffing — add
   a real `kind` tag before there are four payload shapes.
5. `useFinancialSeries` module cache never invalidates; SQLite ledger path is
   CWD-relative (`sec_api.py:74`); `_trim_leading_unpriced` falsy-index bug.
6. IFRS concepts listed but `valid_units=("USD",)` guarantees zero facts for
   non-USD filers — don't repeat the contradiction.

## 2. Feasibility matrix

| Series | Source | Cadence | Needs price? | Effort | Reliability | Verdict |
|---|---|---|---|---|---|---|
| FCF (OCF − capex) | Strong | Annual now; Q/TTM need YTD-differencing | No | Medium | High | Phase 1 (annual) / 2 (Q+TTM) |
| FCF margin | FCF ÷ revenue | Same as FCF | No | +Composite layer | High | Phase 1/2 |
| FCF yield | FCF fine; market cap external | TTM only | Yes (+ shares instant) | High | Medium | Phase 3 |
| Gross margin | `GrossProfit` absent for ~⅓ of filers; derivable; meaningless for banks | Q/A/TTM work today | No | Low + composite | Med-High | Phase 1 |
| Operating margin | `OperatingIncomeLoss` near-universal | All work today | No | Low + composite | High | Phase 1 |
| Diluted share count | Already in registry | Weighted-avg; no TTM sum (correct) | No | UI-only | High | Phase 1 |
| Per-share fundamentals | Composite ÷ diluted_shares | Follows numerator | No | Composite | High | Phase 1 |
| SBC burden | `ShareBasedCompensation` standard | Annual now; Q/TTM need YTD-diff | No | Medium | High | Phase 2 |
| ROIC | NOPAT fine; invested capital needs instants + averaging + definitional choices | Annual/TTM only | No | High | Medium | Phase 4 |
| Net debt | Debt tags fragmented across 6+ concepts | Point-in-time (instant) | No | Instant support + summation chains | Medium | Phase 3 |
| Interest coverage | `InterestExpense` inconsistently tagged | Annual/TTM | No | Medium | Low-Medium | Phase 4 |
| Working capital | `AssetsCurrent` etc. very standard | Instant; turnover needs flow÷instant | No | Instant support | High raw / Medium turnover | Phase 3 |
| Capex intensity | capex ÷ revenue | Same as FCF | No | Medium | High | Phase 2 |
| R&D intensity | Income-statement, discrete quarters exist | All work today | No | Low + composite | High | Phase 1 |
| P/S | TTM revenue exists today | TTM | Yes (+ shares) | Valuation engine reuse | High | Phase 1–2 |
| P/FCF | Once TTM FCF exists | TTM | Yes | Valuation reuse | High | Phase 2/3 |
| P/B | `StockholdersEquity` | Point-in-time | Yes | Instant + valuation | High | Phase 3 |
| EV/EBITDA, EV/S | EBITDA needs D&A (YTD issue); EV needs net debt + mkt cap | TTM | Yes | Everything combined | Medium | Phase 4 |
| Sector KPIs (ARPU etc.) | Not in Company Facts (untagged/dimensional/extension) | — | — | Needs inline-XBRL parser (absent) | Low | Excluded |

## 3. Formulas and source fields

New `METRIC_REGISTRY` entries (priority order):

| Metric | Concept chain (us-gaap unless noted) | Notes |
|---|---|---|
| `operating_cash_flow` | `NetCashProvidedByUsedInOperatingActivities` → `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` | YTD-derivation needed for Q2/Q3 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment` → `PaymentsToAcquireProductiveAssets` → `PaymentsForCapitalImprovements` | ditto |
| `gross_profit` | `GrossProfit`; derived fallback: revenue − (`CostOfGoodsAndServicesSold` → `CostOfRevenue` → `CostOfGoodsSold`) | AAPL tags `CostOfGoodsAndServicesSold` |
| `operating_income` | `OperatingIncomeLoss` | discrete quarters exist |
| `rnd_expense` | `ResearchAndDevelopmentExpense` → `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` | absence is signal |
| `sbc` | `ShareBasedCompensation` | Phase 2 (YTD) |
| `dep_amort` | `DepreciationDepletionAndAmortization` → `DepreciationAndAmortization` → `Depreciation` + `AmortizationOfIntangibleAssets` | Phase 4 (EBITDA) |
| `interest_expense` | `InterestExpense` → `InterestExpenseNonoperating` → `InterestIncomeExpenseNet` | flag which concept won |
| `tax_expense` | `IncomeTaxExpenseBenefit` | for NOPAT |
| Instants (Phase 3) | `StockholdersEquity`; `CashAndCashEquivalentsAtCarryingValue` + `ShortTermInvestments`/`MarketableSecuritiesCurrent`; `LongTermDebtNoncurrent` + `LongTermDebtCurrent` + `DebtCurrent`; `AssetsCurrent`; `LiabilitiesCurrent`; `AccountsReceivableNetCurrent`; `InventoryNet`; `AccountsPayableCurrent`; `dei:EntityCommonStockSharesOutstanding` / `CommonStockSharesOutstanding` | debt/cash are summation chains, a new mapping semantic |

Composites (server-side, aligned on identical `(periodStart, periodEnd)`,
`availableAt = max(components)`, `confidence = min`, `qualityFlags = union`):

- FCF = operating_cash_flow − capex; FCF margin = FCF ÷ revenue;
  FCF/share = FCF ÷ diluted_shares
- Gross margin = gross_profit ÷ revenue; Operating margin = operating_income ÷ revenue
- SBC burden = sbc ÷ revenue; R&D intensity = rnd_expense ÷ revenue;
  Capex intensity = capex ÷ revenue
- Net debt = total debt − (cash + ST investments); Working capital = CA − CL
- Interest coverage = TTM operating_income ÷ TTM interest_expense
- ROIC = NOPAT ÷ avg invested capital; NOPAT = operating_income × (1 −
  tax_expense/pretax income); invested capital = debt + equity − cash,
  averaged over beginning/ending balances
- Market cap(t) = split-adjusted close(t) × latest point-in-time shares with
  availableAt ≤ t; FCF yield = TTM FCF ÷ market cap; P/S, P/FCF, P/B, EV/x
  follow the `valuation_series.py` per-price-bar pattern

## 4. Required schema / API changes

CopeTech-Edgar:
1. `MetricDefinition`: honor `fact_type` (duration|instant); add
   `ytd_cadence` flag; summation-chain semantic for debt/cash aggregates.
2. `financial_series.py`: instant-fact branch (synthesize
   `period_start = period_end`); accept 150–200 / 240–290-day windows as
   H1/9M for ytd_cadence metrics; `_derive_quarters_from_ytd` (flag
   `derived_from_ytd`); gate Q4/TTM on fact_type. TTM for YTD metrics can use
   annual + current-YTD − prior-YTD (EPS engine's proven pattern).
3. New `derived_series.py` composite module; expose via
   `client.financials.series(metric="fcf_margin", ...)`. No SQLite schema
   change; composites computed at read time, not persisted.
4. `EdgarAgentTools` metric enum generated from the registry.
5. Fix or drop the IFRS/`valid_units` contradiction.

CopeNet:
6. `core/market/financials.py`: dispatch table for valuation-type metrics
   instead of the `trailing_pe` string special-case; pass explicit cache_dir.
7. Add `kind: "financial" | "valuation"` to payloads; stop key-sniffing.
8. Frontend: metric list from a `market.financial.metrics.list` RPC;
   per-metric priceFormat (percent/currency/ratio); cache invalidation in
   `useFinancialSeries`.
9. `market.financials` agent tool enum from the same registry.

## 5. Phased plan

- **Phase 1 — income-statement metrics + composite layer**: gross
  profit/margin, operating income/margin, R&D + intensity, revenue-per-share,
  annual FCF + annual FCF margin. Carry-alongs: kind tag, agent-tool enums,
  registry-driven UI, summary-P/E basis fix.
- **Phase 2 — YTD-differencing cadence**: quarterly/TTM OCF, capex, SBC, D&A
  → full FCF family at all frequencies; P/S and P/FCF via valuation engine.
- **Phase 3 — instant-fact support**: shares outstanding, equity, cash, debt,
  current assets/liabilities → net debt, working capital, P/B, market-cap
  series, FCF yield, EV/S.
- **Phase 4 — hard composites**: EBITDA + EV/EBITDA, interest coverage, ROIC
  (documented invested-capital definition, balance averaging).
- **Excluded**: sector-specific operational KPIs (not in Company Facts;
  requires the inline-XBRL parser CopeTech-Edgar lacks) and forward multiples
  (no timestamped consensus source).

## 6. Risks and unresolved decisions

1. YTD cash-flow cadence is the linchpin risk; differencing compounds
   restatement noise — mitigate with conflict flags + confidence discounts.
2. Debt/interest tag fragmentation: summation chains risk double-counting
   (`LongTermDebt` vs current/noncurrent split) and omission (finance leases).
3. `GrossProfit` absence for a large minority of filers; gross margin
   meaningless for financials — need per-metric "not applicable" UI handling.
4. Non-GAAP divergence vs street FCF/EBITDA — annotate (show SBC alongside
   FCF) rather than silently diverge.
5. Multiple share classes (GOOGL/BRK): consolidated counts sometimes only
   dimensional; Company Facts excludes dimensional facts.
6. Market-cap dependence on yfinance grows with every price-based metric —
   acceptable now; worth an abstraction seam.
7. Open: composites computed in CopeTech-Edgar (chosen) vs CopeNet; ROIC
   invested-capital definition; persist derived observations (no — read-time);
   alignment story for instant metrics (reuse availableAt).

## 7. First batch (Phase 1 scope)

Gross margin, operating margin, R&D intensity, revenue-per-share, annual FCF +
FCF margin, and P/S. Pure income-statement series exercise only registry rows
plus the composite layer against the least fragile data; annual FCF rides
along free; P/S reuses the battle-tested valuation engine with TTM revenue.
Touches zero risky normalizer paths and forces the UI/tooling generalization
that makes every later metric a data-only change.

## 8. Phase 1 implementation status (2026-08-02)

Landed in CopeTech-Edgar:
- Registry: `gross_profit`, `cost_of_revenue`, `operating_income`,
  `rnd_expense`, `operating_cash_flow`, `capex` (`financial_metrics.py`).
- New `derived_series.py` composite layer: `fcf`, `fcf_margin`,
  `gross_margin` (with per-window cost-of-revenue fallback, flag
  `gross_profit_derived_from_cost_of_revenue`), `operating_margin`,
  `rnd_intensity`, `revenue_per_share`. Join on exact
  `(periodStart, periodEnd)`; availableAt = max over the components a value
  actually used; confidence = min; flags = union. TTM requests whose required
  components are weighted averages return empty with
  `ttm_unavailable_for_weighted_average_component`.
- `FinancialSeriesService.get_series` routes derived ids; one Company Facts
  fetch feeds all components. `supported_metrics()` lists base + derived.
- `edgar.financials.series` agent-tool enum generated from the registries.
- Tests: `tests/test_derived_series.py` (9 tests); full suite green.

Landed in CopeNet:
- `VALUATION_METRICS` dispatch replaces the `trailing_pe` string special-case;
  payloads carry `kind: "financial" | "valuation"`; SEC cache pinned to
  `<market root>/edgar` instead of the process CWD (first run after this
  change rebuilds the fact ledger there); `_trim_leading_unpriced` index check
  made explicit.
- New RPC `market.financial.metrics.list`; `supported_financial_metrics()`
  returns base + derived + the `trailing_pe` valuation pseudo-metric.
- `market.financials` agent tool enum generated from the same list.
- Summary-card P/E now divides a SPLIT_ADJUSTED close by TTM EPS
  (`MarketRuntime._last_split_adjusted_close`) — the TOTAL_RETURN basis bug is
  fixed in both paths.
- Frontend: overlay controls are registry-driven (flagship Revenue / P/E
  buttons + a dropdown for every other served metric), frequency selector
  shows for all financial metrics, `isValuationPayload()` replaces
  `'epsMetric' in data` sniffing, and the left axis formats by unit
  (ratio → percent, USD/shares → currency, shares → count, USD → $B).

Deliberately deferred from the first batch:
- **P/S**: a correct trailing P/S needs split-adjusted point-in-time TTM
  revenue-per-share — share-count reconstruction machinery equivalent to
  `eps_series.py`. Building it hastily would ship exactly the fragility this
  plan exists to avoid; it moves to Phase 2 alongside the YTD-differencing
  work.
- Quarterly/TTM FCF beyond fiscal Q1 (needs Phase 2 YTD differencing; annual
  FCF and sparse quarterly observations work today).
- `useFinancialSeries` cache invalidation / refresh button (unchanged
  behavior: cached for the page lifetime).
