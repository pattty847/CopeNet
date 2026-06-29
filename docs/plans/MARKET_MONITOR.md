# CopeNet Market Monitor — Vision & Build Plan

**Status:** Direction agreed, not started. This doc exists to align Patrick + Claude + Codex
before any code lands.
**Owners:** Patrick (director) · Codex (backend/plumbing) · Claude (frontend + spec/direction)
**Last updated:** 2026-06-27

---

## 1. What we're building (one paragraph, grounded)

A **slow-timeframe market orientation tool** for a long-term accumulator who *enjoys* watching
the market. It pulls end-of-day/weekly data over a universe of quality names, computes a small
set of **explainable** signals (trend state, pullback zones, relative strength vs ETFs, drawdown,
MAMA/FAMA regime), enriches with **SEC insider + filing intelligence**, and has an LLM produce a
**caveated** weekly/daily briefing. It surfaces as a **dashboard + Pulse inbox items**, and later
**Telegram alerts**. It is explicitly **not** a day-trading bot, not an indicator-spam alert feed,
and not a predictor — it's a "so I don't have to watch every chart, and I don't miss the rare thing
that matters" radar.

## 2. Who it's for (this anchors every decision)

Patrick, specifically:
- **Doesn't day-trade anymore.** Holds positions, buys more when he can (accumulator).
- **Enjoys the watching** — pullback-zone hunting, pattern-finding, long-term horizons. The screen
  time is a feature, not a cost. So "make the watching richer/wider" is itself a valid goal even
  when it doesn't change a trade.
- **Glances daily**, but the market moves slow → **weekly candles are primary, daily confirms.**
  No low-timeframe anything.
- Wants to be **"the coworker people can ask about the market"** — i.e. wants a recitable,
  honest read on what the market is doing.
- Wants to **change his mind quantitatively**: tell him *why* a name is worse than just buying
  **VOO / XLK**, not just "here's a signal."
- Has a **small speculative appetite**: honestly-good names down ~30%, promising for a stretch →
  "yeet $100, look for profit and a defined exit." Self-aware about the gambling; the tool should
  **sharpen** it, not enable it.
- **PDT rule removal confirmed by Patrick** (recent change) → swing-trade frequency is no longer
  constrained by the old $25k / 4-trades-a-week rule. Loosens the speculative lane's cadence.

## 3. What it IS / what it ISN'T

| It IS | It is NOT |
|---|---|
| Weekly-primary, daily-confirm orientation | Intraday / low-TF anything |
| Rare-event, high-signal alerts | Indicator-wiggle spam (RSI crossed 30, etc.) |
| LLM as **caveated summarizer of verified facts** | LLM as predictor / hype narrator |
| Two honest lanes: **Core accumulation** + **Speculative swing** | One blurred "opportunities" feed |
| Benchmark-aware ("worse than VOO/XLK?") | Standalone buy/sell calls |
| Grounded, explainable confluence | Mystical black-box scoring |

## 4. Core design principles (DECIDED)

1. **Weekly primary, daily confirmation.** Regime/trend read off weekly candles; daily only used
   to confirm weekly trend changes. Lower noise, slower cadence, fewer/better alerts.
2. **Universe, not a watchlist** (eventually). Goal is 100+ quality names so the system can *find*
   better investments, not just monitor a hand-picked few. **Start small to prove value, expand
   once it earns it.**
3. **Benchmark everything against the ETF.** Every name gets an explicit "is this actually better
   than just buying VOO / XLK / its sector ETF?" read. Opportunity-cost framing is first-class.
4. **Two separated lanes, never blurred:**
   - **Core / accumulation** — quality names in pullback zones, with the SEC/filing backdrop.
   - **Speculative / swing** — down-~30% names with a defined small size + exit. Clearly labeled.
5. **LLM = caveated summarizer, never predictor.** It describes verified facts and must state
   *what would make the read wrong* (the "contrarian / thesis-killer" panel is load-bearing).
6. **Rare-event alerts only.** Tuned to fire on meaningful, infrequent events. The boy-who-cried-wolf
   failure is the primary thing to avoid.
7. **Stay grounded and honest.** Honest empty states, no phantom precision, surface uncertainty.

## 5. Reuse map (what's free vs what we build)

| Piece | Source | Decision |
|---|---|---|
| Daily/weekly adjusted OHLCV | **Build our own `yfinance` integration inside CopeNet** | Build (thin) — do NOT shell out to Sentinel's script; own it in CN |
| Insider / 8-K / 13F + `llm_digest` | **CopeTech-Edgar** (`from copetech_sec import SECDataFetcher`, no API key, just user-agent) | **Reuse as-is** — easily implemented, highest-ROI piece |
| Signal math (MA distance, ATR move, RS, drawdown, **MAMA/FAMA**) | **`pandas-ta`** + pandas | Build (thin) |
| Screener breadth | Sentinel `tvscreener` scripts | **Later** — only if/when it proves useful |
| Macro backdrop (VIX, 10Y, dollar, gold, oil) | `yfinance` proxies (`^VIX`, `^TNX`, `DX-Y.NYB`, `GLD`, `USO`) — no key | Build (thin), v1-optional |
| FRED economic calendar (CPI/FOMC/jobs) | FRED API (needs free key + credential store CN lacks) | **Defer** |
| Briefing surface | CopeNet **Pulse** inbox + **Artifacts** (both durable, exist) | Reuse as-is |
| Daily/weekly auto-run | No scheduler in CopeNet today | Build (small) |
| Telegram alerts | Config + routing built; **send function missing** | Build (one function) |
| Dashboard | Nothing | Build (Claude's lane) |

## 6. Architecture shape

Follow the **Meme Lab precedent**: a standalone runtime module + typed models + REST endpoint +
a Workflows-section UI. Provider-agnostic synthesis (same `Provider` streaming interface).

Proposed new backend home: `src/copenet/core/market/`
- `data_sources.py` — yfinance OHLCV fetch (daily + weekly) + macro proxies
- `signals.py` — pandas-ta signal/regime computation, pure functions on a price frame
- `edgar.py` — thin wrapper over `copetech_sec.SECDataFetcher` (insider digest, 8-K)
- `market_monitor_runtime.py` — orchestrate fetch → signals → enrich → LLM synthesis
- `models.py` — typed DTOs (Asset, Bar, SignalSet, TickerBrief, MarketBriefing, Alert)
- `store.py` — **NEW durable store** for bars + computed signals + briefings (recurring,
  operator-level data — NOT session-scoped artifacts). Likely JSON/JSONL or sqlite.

Surfaces:
- **Dashboard** in Workflows section ("Market Monitor" playbook): Market Regime · Accumulation
  Watch · Trend-Change Watch · Macro Board · Evidence Feed (SEC) · Contrarian Notes · Speculative
  lane (with live P&L) · **Sector Rotation Graph (RRG)** — see §12.
- **Pulse item** per run ("Weekly briefing ready — 2 accumulation candidates, 1 trend-change").
- **Artifacts** for the briefing markdown + signal JSON (auditability).
- **Telegram** delivery (Phase 2).

## 7. Division of labor

- **Codex — backend / plumbing:** data ingestion, signal engine, edgar wrapper, the new market
  store, scheduler lane, Telegram send function, RPC/endpoints.
- **Claude — frontend + spec/direction:** the dashboard and all UI, writing the build specs Codex
  works from, pulling insights/options, keeping us on-page, reviewing backend contracts at the boundary.
- **Patrick — director:** seeds the watchlist, sets thresholds/taste, makes the calls below.

## 8. Phasing

- **Phase 1 — Thin vertical slice (headless):** small watchlist → yfinance (weekly+daily) → signals
  → SEC insider digests → LLM briefing → artifact + Pulse item. Prove the briefing is *genuinely
  useful* via CLI/probe before any dashboard.
- **Phase 2 — Dashboard:** the Workflows surface reads Phase-1 output.
- **Phase 3 — Scale the universe:** expand to 100+ names; add tvscreener breadth if useful.
- **Phase 4 — Automation:** daily/weekly scheduler + Telegram alert delivery.

---

## 9. OPEN DECISIONS TO PIN DOWN

Each has a **recommended default** — react with yes / no / tweak so we converge fast.

### D1 — Starter watchlist (names + size) — ✅ RESOLVED
Patrick supplied the full list (~40 names), grouped by role. See **§11 Watchlist v1**. This IS the
Phase-1 universe (bigger than the original 15–25 guess, still trivially cheap for yfinance). 100+
expansion stays Phase 3. The role groupings drive the data model — each asset carries a `role`.

### D2 — Run cadence & primary timeframe mechanics
*How do weekly-primary / daily-confirm translate to jobs?*
**Recommend:** a **weekly deep pass** (weekend/Friday close) that does the full regime read +
briefing, and a lighter **daily pass** that only updates daily candles and checks for
daily-confirming a pending weekly trend change. Phase 1 = manual "Run briefing" trigger; scheduler
is Phase 4.
→ **Confirm:** weekly-deep + daily-confirm split? Manual trigger for v1?

### D3 — "Worse than VOO/XLK" benchmark logic — ✅ RESOLVED (risk-adjusted framing)
**Patrick's call:** it's about **beta + correlation vs excess return.** A name has to *earn* its
extra volatility. If it's more volatile than the ETF but doesn't deliver more return, **the ETF
wins.** So:
- Compute, per name vs benchmark (VOO broad + the name's sector ETF): **correlation**, **beta**,
  and **excess return** over rolling windows (3/6/12-month).
- Verdict logic: a name "beats the ETF" only if **excess return > 0 after accounting for its beta**
  (i.e. risk-adjusted outperformance — Sharpe-style, not raw return). High beta + no excess return
  = "just buy the ETF."
- LLM phrases the verdict in plain language, citing the numbers.
This same risk-adjusted measure feeds **correlation pruning** (§11): among correlated names, keep
the one with better risk-adjusted return / lower volatility.

### D4 — Signal set v1 (the exact list + MA periods)
*Pin the v1 indicators so Codex builds a fixed contract.*
**Recommend (weekly unless noted):**
- Trend state vs **10/30/40-week** MAs (≈ 50/150/200-day)
- Daily **50/200-DMA** for confirmation only
- **MAMA/FAMA** regime label (pandas-ta) — one input, not a standalone trigger
- ATR(14) + current move vs ATR (stretch)
- Volume vs 20-period average
- Drawdown from 52-week high (pullback-zone depth)
- Relative strength vs benchmark (D3)
- Pullback-zone score = confluence of (below key MA + oversold + deep-ish drawdown + structure)
→ **Confirm:** this list + the MA periods.

### D5 — Alert thresholds (what's worthy of a Pulse/Telegram ping) — ⏸ DEFERRED (decide once running)
**Patrick's call:** tune this after the system is live and we can see real signal volume. Don't
guess thresholds in the abstract.
**Mechanism (decided):** alert rules live in a **YAML config** (human-editable, version-able). Bonus
path: an operator can describe what they want in plain text → an LLM generates/edits the YAML. So
build the alert layer to read a declarative YAML rule set, not hard-coded thresholds.
**Starting trigger candidates** (to tune later): weekly trend change confirmed by daily; insider
**cluster buy**; material 8-K; quality name **entering a pullback zone**; ≥30% drawdown in a quality
name; **index-inclusion / forced-buying events** (see SPCX). Plus a ping budget (cap N/week).

### D6 — Speculative lane: surface-only or track positions? — ✅ RESOLVED (track positions)
**Patrick's call:** **track real positions.** He owns two speculative names — **SOFI** and **SLI** —
and will supply **avg entry price + share count**. So the spec lane shows live P&L + watches for a
defined exit, not just candidates.
**Data-model impact:** `held`/speculative assets carry **`{avg_cost, shares}`** (cost basis). This
also enables real portfolio P&L for the Portfolio group, which feeds D11 portfolio monitoring.
**Still surface** new candidates with entry-zone / target / invalidation framing.
→ **Needs from Patrick:** avg entry + amounts for his positions (SOFI, SLI at minimum; ideally the
full Portfolio group for accurate P&L).

### D7 — New market store shape (Codex's call, flag it)
*Recurring operator-level data (bars + signals + briefings) doesn't fit session-scoped artifacts.*
**Recommend:** dedicated `core/market/store.py` — JSONL for bars/signals (append-friendly,
greppable) + a briefings log. sqlite if volume demands. Codex decides the exact shape.
→ **Codex to propose** the store contract.

### D8 — Scheduler mechanism (Phase 4, decide early)
*CopeNet has no scheduler.*
**Recommend:** in-process asyncio/APScheduler background lane inside the host (keeps it
self-contained, no external cron/launchd dependency). Codex's architecture call.
→ **Codex to weigh in:** in-process vs external.

### D9 — SEC user-agent + any config/secrets — ✅ RESOLVED
`SEC_API_USER_AGENT = "Patrick McDermott (CopeNet) pattty847@gmail.com"`. Set via env/config; no
full credential store until FRED (deferred) forces it.

### D10 — Which provider/model synthesizes the briefing
**Recommend:** default to the strongest available (openai-codex / a capable Claude model);
operator-selectable like Meme Lab.
→ **Confirm:** a default, or leave operator-selectable.

### D11 — Macro board + portfolio monitoring — ✅ RESOLVED (macro in v1; portfolio advisory next)
**Patrick's call:** macro board **yes, in v1** (yfinance proxies, no key; FRED deferred).
**And the elevated next priority after macro: PORTFOLIO MONITORING / ADVISORY.** What he actually
wants the system to help with:
- when to buy **additional shares** (accumulation timing on names he holds),
- **what to worry about** in his current book,
- **where to hedge** if drawdowns look likely on the horizon.
**Hard constraint (Patrick, emphatic):** advice must be **evidence-based with historical proof** —
frontier model reasoning is trusted, but **no crystal-ball / pure prediction.** Every suggestion
cites the data/precedent it rests on, and explicitly carries the "past ≠ future" caveat. This is the
contrarian/thesis-killer principle (§4.5) applied to portfolio advice.
→ **Phasing:** macro board = v1. Portfolio-advisory = its own Phase (call it **Phase 2.5 — Portfolio
Copilot**), built on the cost-basis data from D6.

---

## 10. Honest risks (keep visible)

- **Noise / over-alerting** → trains Patrick to ignore it. Mitigated by D5 rare-event tuning + ping budget.
- **LLM horoscope** → false confidence dressed as analysis. Mitigated by facts-only + mandatory
  thesis-killer panel (principle 5).
- **Curve-fit signals** → feel predictive, aren't. Mitigated by keeping signals simple, explainable,
  benchmark-relative.
- **Speculative lane feeding the gambling impulse** → mitigated by hard separation + defined-risk
  framing + honest labeling (principle 4).

---

## 11. Watchlist v1 (D1 — resolved)

Patrick's monitored universe, grouped by **role**. The role drives system behavior — it tells the
engine whether an asset is a *position to manage*, a *regime/benchmark anchor*, a *candidate to
evaluate*, or a *macro/sector reference*. Store each asset with `{symbol, name, role, yf_symbol}`.

| Symbol | Name | Role | yfinance symbol |
|---|---|---|---|
| **Portfolio (held — core accumulation + manage)** ||||
| ASX | ASE Technology Holding (ADR) | held | `ASX` |
| GOOG | Alphabet Class C | held | `GOOG` |
| SOFI | SoFi Technologies | held | `SOFI` |
| VTI | Vanguard Total Stock Market ETF | held | `VTI` |
| XLK | Technology Select Sector SPDR | held | `XLK` |
| XLE | Energy Select Sector SPDR | held | `XLE` |
| SLI | Standard Lithium | held (spec-ish) | `SLI` |
| **Major Markets (regime + macro anchors, RS benchmarks)** ||||
| VOO | Vanguard S&P 500 ETF | benchmark | `VOO` |
| QQQ | Invesco QQQ Trust | benchmark | `QQQ` |
| VOOG | Vanguard S&P 500 Growth ETF | benchmark | `VOOG` |
| XLRE | Real Estate Select Sector SPDR | sector | `XLRE` |
| DXY | U.S. Dollar Index | macro | ⚠ `DX-Y.NYB` (not `DXY`); fallback proxy `UUP` |
| VIX | Volatility S&P 500 Index | macro | ⚠ `^VIX` (needs caret) |
| BTCUSD | Bitcoin / USD | macro/risk | ⚠ `BTC-USD` |
| ETHUSD | Ethereum / USD | macro/risk | ⚠ `ETH-USD` |
| **Watch List (active candidates)** ||||
| CRWV | CoreWeave | candidate | `CRWV` (recent IPO — short history) |
| SHLD | Global X Defense Tech ETF | candidate | `SHLD` (ticker reused; verify resolves to Global X, not old Sears) |
| PLD | Prologis | candidate | `PLD` |
| **Future Bags (want-to-own — accumulation-zone watch)** ||||
| AMZN | Amazon | future-bag | `AMZN` |
| INTC | Intel | future-bag | `INTC` |
| IWM | iShares Russell 2000 ETF | future-bag | `IWM` |
| NVDA | NVIDIA | future-bag | `NVDA` |
| TSLA | Tesla | future-bag | `TSLA` |
| SPCX | SpaceX (newly public ~Jun 2026) | future-bag / event-watch | ⚠ **Confirm the actual common-stock ticker resolves on yfinance** (Patrick: SpaceX went public ~last week; **pending SPY inclusion ~Jul 6 2026** → index funds forced to buy = demand catalyst worth watching). Brand-new issue → near-zero history; treat as event-driven, not trend-driven |
| **Extra ETF / Sector (sector RS benchmarks + breadth)** ||||
| VONE | Vanguard Russell 1000 ETF | benchmark | `VONE` |
| VTHR | Vanguard Russell 3000 ETF | benchmark | `VTHR` |
| EFA | iShares MSCI EAFE ETF | benchmark (intl) | `EFA` |
| VWO | Vanguard FTSE Emerging Markets ETF | benchmark (EM) | `VWO` |
| USO | United States Oil Fund | macro/commodity | `USO` |
| SOX | Philadelphia Semiconductor Index | sector | ⚠ `^SOX` (index, needs caret); or use `SMH` as tradeable proxy |
| SMH | VanEck Semiconductor ETF | sector | `SMH` |
| XLI | Industrial Select Sector SPDR | sector | `XLI` |
| XLF | Financial Select Sector SPDR | sector | `XLF` |
| XLP | Consumer Staples Select Sector SPDR | sector | `XLP` |
| XLY | Consumer Discretionary Select Sector SPDR | sector | `XLY` |
| XLU | Utilities Select Sector SPDR | sector | `XLU` |
| XLB | Materials Select Sector SPDR | sector | `XLB` |
| XLV | Health Care Select Sector SPDR | sector | `XLV` |

### Symbol-resolution notes (yfinance grounding for Codex)
Most resolve as typed. The ones that DON'T: `DXY → DX-Y.NYB`, `VIX → ^VIX`, `SOX → ^SOX`,
`BTCUSD → BTC-USD`, `ETHUSD → ETH-USD`. **`SPCX` must be verified** (SpaceX is private; the ticker
may be dead). `CRWV` and `SHLD` resolve but have short/odd histories — handle thin-history names
gracefully (weekly trend math needs enough bars).

---

## 12. Sector Rotation Graph (RRG) — requested feature

Patrick wants a **coordinate-plane plot of momentum (Y, +/-) vs relative growth (X,
increasing/decreasing)**, plotting each sector over time with **traced lines (tails)** between
points to see how sectors rotate and where money is flowing. **This is the Relative Rotation Graph
(RRG)** — a known methodology (JdK), perfect for the XL sector series.

**Math (Codex):** for each asset vs a benchmark (VOO/SPY):
- **X = RS-Ratio:** normalized relative strength (asset ÷ benchmark, then normalized ~100 center).
- **Y = RS-Momentum:** normalized rate-of-change of the RS-Ratio (~100 center).
- Compute weekly; keep the last ~6–10 points per asset to draw the **tail** (trajectory; tends to
  rotate clockwise).

**Four quadrants:**
| Quadrant | Meaning |
|---|---|
| Top-right — **Leading** | strong RS, rising momentum (current leaders) |
| Bottom-right — **Weakening** | strong RS, falling momentum (leaders losing steam) |
| Bottom-left — **Lagging** | weak RS, falling momentum (laggards) |
| Top-left — **Improving** | weak RS but rising momentum (early rotation in) |

**Primary use:** the **XL sector series** (XLK/XLE/XLF/XLI/XLV/XLP/XLY/XLU/XLB/XLRE) + SMH vs VOO —
shows sector rotation at a glance: what's leading, what's rotating in/out. Could later overlay
individual holdings.

**Frontend (Claude):** SVG/canvas scatter with 4 labeled quadrants, a dot per asset, fading
poly-line tails showing the recent path, hover for detail, weekly cadence. This is a signature,
high-delight panel — built to look great.

### Correlation pruning (Patrick's note: "remove super-correlated, keep the best one")
Heavy overlap clusters exist: broad US equity (VOO/VTI/VONE/VTHR/VOOG/QQQ), semis (SOX/SMH/NVDA),
tech (XLK/QQQ). **Important distinction:** correlation among the **benchmark/sector ETFs is fine and
intentional** — they're reference anchors, not competing investments. Pruning only matters when
**ranking candidate investments against each other** (so the "best name" list doesn't show five
near-identical S&P wrappers). **Pruning rule (Patrick):** among highly-correlated candidates, keep
the one with the **better risk-adjusted return / lower volatility** (ties directly to D3's beta +
excess-return measure). Apply dedup at the *ranking/recommendation* layer, not the data layer.
Defer the actual pruning logic to when the ranked list exists (Phase 3-ish).
