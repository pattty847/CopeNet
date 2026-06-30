# Market Monitor — Build Blueprint (Frontend ⇄ Backend Contract)

**Status:** ready to break ground. Companion to `MARKET_MONITOR.md` (vision/decisions) and
`MARKET_MONITOR_DESIGN_PROMPT.md` (the design). This doc is the **alignment contract** so Claude
(frontend) and Codex (backend) build in parallel without stepping on each other.
**Owners:** Claude = frontend · Codex = backend · Patrick = director.
**Base:** branch off clean `main` (identity/PWA/docs already merged: 320b764 / fec567c / 392ad9a).

---

## 0. How we work in parallel (read first)

**Frontend is built mock-first.** Claude implements the entire UI against a single typed seam —
`useMarketMonitorData()` — backed by an illustrative sample module today. Codex builds the backend
to produce the *same typed shapes*. Neither side blocks the other.

**The only integration point is ONE file** — the hook swaps its sample import for real RPC calls,
panel-by-panel. Everything else (components, store, signal engine, edgar wrapper) is independent.

**Worktrees:** Codex works in a separate worktree off `main` (backend); Claude works on a branch
off `main` (frontend). Merge both via PR when each side is green. **File ownership below guarantees
the diffs don't overlap.**

**Source of truth = §2 (the typed contract).** If the UI needs a field, it's added here first, then
both sides implement it. Backend never invents a shape the contract doesn't list; frontend never
consumes one it doesn't list.

---

## 1. Surface & RPC boundary

The frontend talks to the backend through **three read RPCs + one action**. Method names and payload
shapes are frozen by this doc.

| RPC | Request | Response | Notes |
|---|---|---|---|
| `market.dashboard.get` | `{}` | `DashboardPayload` (§2) | the whole dashboard; each panel carries its own `status` so we can go live panel-by-panel |
| `market.ticker.get` | `{ symbol: string }` | `TickerDetailPayload` (§2) | drill-down view |
| `market.universe.get` | `{}` | `UniverseAsset[]` (§2) | ⌘K palette list (Patrick's watchlist w/ roles) |
| `market.refresh` | `{ scope?: 'all' \| 'macro' \| 'signals' \| 'edgar' }` | `{ startedAt, runId }` | manual "run today's briefing" trigger (v1); scheduler is later |

Each panel's data is wrapped so we can ship honestly while the backend fills in:
```ts
type PanelStatus = 'live' | 'preview' | 'stale' | 'error';
interface Panel<T> { status: PanelStatus; data: T; asOf?: string; note?: string; }
```
`preview` ⇒ the UI shows the "Preview · illustrative" badge. When Codex lands a panel, he flips its
`status` to `live` and the badge disappears — no frontend change needed.

---

## 2. The typed data contract (source of truth)

Derived directly from the approved Claude Design dashboard. TypeScript is canonical; backend emits
matching JSON (camelCase).

```ts
// ---------- shared ----------
type Tone = 'up' | 'down' | 'flat';            // drives green / red / muted ONLY
type Direction = 'up' | 'down';
type AssetRole = 'index' | 'holding' | 'watch' | 'trend' | 'spec' | 'sector' | 'macro';

interface UniverseAsset { symbol: string; name: string; role: AssetRole; }

// ---------- dashboard ----------
interface DashboardPayload {
  asOf: string;                                 // "as of Fri 4:00pm ET close"
  briefing: Panel<Briefing>;
  regime:   Panel<Regime>;
  macro:    Panel<MacroItem[]>;
  rrg:      Panel<RrgSector[]>;
  accumulation: Panel<AccumulationRow[]>;
  trend:    Panel<TrendRow[]>;
  portfolio: Panel<Portfolio>;
  speculative: Panel<SpecPosition[]>;
  evidence: Panel<EvidenceItem[]>;
  contrarian: Panel<ContrarianNote[]>;
}

interface Briefing {
  headline: string;            // hero line; may wrap one emphasized clause (see emphasis)
  emphasis?: string;           // substring of headline to amber-highlight
  summary: string;             // 1-2 sentence plain-English read
  changed: { text: string; tone: Tone }[];      // "chop → risk-on", etc.
  attention: AttentionItem[];  // the 2-3 things that need eyes today
  vix: number;
  breadthPct: number;          // 0-100
}
interface AttentionItem { kind: string; label: string; glyph: string; symbol: string; }

interface Regime {
  current: 'risk-off' | 'chop' | 'risk-on' | 'event-risk';
  scale: { name: string; active: boolean; note?: string }[];   // note e.g. "CPI Thu"
}

interface MacroItem {
  label: string;               // DXY, US 10Y, VIX, Gold, WTI Oil, BTC, ETH
  value: string;               // pre-formatted ("$3,340", "4.21%")
  change: string;              // "+0.31%", "−3 bps"
  tone: Tone;
  spark: number[];             // ~22 points, 5-day
}

interface RrgSector {          // one sector ETF vs benchmark, with tail
  symbol: string; name: string;
  tail: { x: number; y: number }[];   // x = RS-Ratio (~ -6..6), y = RS-Momentum; last = current
  quadrant: 'leading' | 'weakening' | 'lagging' | 'improving';
}

interface AccumulationRow {
  symbol: string; name: string;
  belowMa: string;             // "−8.4%" vs 50W
  drawdown: string;            // "−41%"
  rsi: string;                 // "33"
  confluence: number;          // 0..4 (dot count)
  why: string;
}

interface TrendRow {
  symbol: string; direction: Direction; note: string; when: string; confirmed: boolean;
}

interface Portfolio {
  total: string;               // "$248,310"
  pnl: string;                 // "+$41,920 · +20.3%"
  pnlTone: Tone;
  positions: PortfolioPosition[];
}
interface PortfolioPosition {
  symbol: string; shares: number; avgCost: number;
  last: string; pnlPct: string; tone: Tone; nudge?: string;   // nudge = "add zone" hint
}

interface SpecPosition {
  symbol: string; pnlPct: string; tone: Tone; thesis: string;
  entry: string; target: string; invalidation: string;
}

interface EvidenceItem {
  type: 'Insider' | '8-K' | 'News'; symbol: string;
  headline: string; source: string; tone: Tone; url?: string;
}

interface ContrarianNote { signal: string; kill: string; }   // kill = "what makes this wrong"

// ---------- ticker detail ----------
interface TickerDetailPayload {
  symbol: string; name: string; last: string; change: string; tone: Tone;
  series: { weekly: Ohlcv[]; daily: Ohlcv[] };
  verdict: VerdictRow[];
  signals: SignalRow[];
  evidence: EvidenceItem[];
  events: ChartEvent[];        // markers: insider buys, 8-Ks
  kill: string;                // "what would make this wrong"
}
interface Ohlcv { t: number; o: number; h: number; l: number; c: number; v: number; }
interface VerdictRow { bench: string; label: 'Beats' | 'Lags' | 'In line'; pct: string; tone: Tone; }
interface SignalRow { key: string; value: string; tone: Tone; }
interface ChartEvent { t: number; kind: 'insider' | '8-K'; glyph: string; }
```

---

## 3. Backend expectations (Codex)

**Home:** `src/copenet/core/market/` (all new — zero conflict with existing code).
```
core/market/
  data_sources.py   # yfinance OHLCV (weekly+daily) + macro proxies. Symbol map per below.
  signals.py        # pure pandas/pandas-ta: trend vs MAs, ATR move, vol vs avg, drawdown,
                    #   relative strength, MAMA/FAMA regime, RRG (RS-Ratio × RS-Momentum)
  edgar.py          # thin wrapper over copetech_sec.SECDataFetcher → EvidenceItem[]
  benchmark.py      # beta + excess-return vs VOO + sector ETF → VerdictRow[]
  synthesis.py      # LLM briefing + contrarian notes (provider-agnostic, Meme Lab pattern)
  store.py          # durable: bars + computed signals + latest briefing (operator-level, NOT
                    #   session artifacts). JSONL or sqlite — Codex's call.
  runtime.py        # orchestrate: refresh → compute → persist → assemble DashboardPayload
  models.py         # Python DTOs mirroring §2 (snake_case internally, camelCase on the wire)
```
**RPC:** `host/rpc_market.py` (new) implementing the four methods in §1; register in
`rpc_catalog.py` + `rpc_dispatch.py` (the ONLY shared-file touches — see §5).

**Sourcing map:**
| Contract field | Source |
|---|---|
| `macro`, `portfolio.last`, `ticker.series`, `accumulation`, `trend`, `rrg` | yfinance OHLCV → `signals.py` (pandas-ta) |
| `portfolio` P&L | yfinance last + Patrick's cost basis (config) |
| `verdict` | `benchmark.py` (beta + excess return vs VOO + sector ETF) |
| `evidence`, ticker `events` | `copetech_sec.SECDataFetcher` (`get_insider_signal_payload`, 8-K) |
| `briefing`, `contrarian` | `synthesis.py` LLM over the computed facts — facts-only, must emit thesis-killers, no forecasts |

**Symbol resolution (yfinance):** `DXY→DX-Y.NYB`, `VIX→^VIX`, `SOX→^SOX`, `BTCUSD→BTC-USD`,
`ETHUSD→ETH-USD`; verify `SPCX`; handle thin-history names (`CRWV`,`SHLD`,`SPCX`) gracefully.
SEC user-agent: `"Patrick McDermott (CopeNet) pattty847@gmail.com"`. (Full watchlist: `MARKET_MONITOR.md` §11.)

**Go-live ladder** (flip each panel's `status` to `live` as it lands — order = least lift → most):
1. `macro` → 2. `portfolio` → 3. `accumulation` + `trend` + `rrg` (the pandas-ta core) →
4. `evidence` (edgar) → 5. `briefing` + `contrarian` (LLM, needs the rest as input) →
6. `ticker.series` real OHLCV (frontend then swaps SVG → Lightweight Charts).

**Constraints:** weekly-primary / daily-confirm. Risk-adjusted benchmark logic (D3). Evidence-based,
no crystal ball. Honest empty states (`status:'preview'`/`'error'` not fake data).

---

## 4. Frontend expectations (Claude)

**Home:** `src/copenet/host/frontend/src/sections/market/` (all new).
```
sections/market/
  MarketMonitor.tsx        # page shell (briefing → cockpit grid → drill-down)
  useMarketMonitorData.ts  # THE SEAM. returns DashboardPayload | TickerDetailPayload | universe.
                           #   today: imports ./sampleData. later: calls market.* RPCs. (one-file swap)
  sampleData.ts            # illustrative data seeded with Patrick's real watchlist + roles
  panels/                  # one file per panel (BriefingHero, MacroBoard, Rrg, AccumulationWatch,
                           #   TrendWatch, Portfolio, Speculative, Evidence, Contrarian)
  Rrg.tsx                  # SVG rotation graph (port from design — quadrants, tails, scrubber)
  TickerDetail.tsx         # chart (SVG now → Lightweight Charts later) + verdict/signals/evidence
  CommandPalette.tsx       # ⌘K ticker jump (port from design, scoped to this section)
  types.ts                 # the §2 contract (canonical TS)
```
**Nav:** new top-level section "Market" (Patrick signed off — new nav item). Minimal `AppShell.tsx`
nav-entry addition + route in the store (frontend-owned, see §5).

**Behavior:** drop the design's mock rail/topbar (CopeNet provides them); keep the ⌘K palette. Honor
the `Panel.status` badge. Match the pinned tokens (`MARKET_MONITOR_DESIGN_PROMPT.md` appendix).

---

## 5. File ownership (so the diffs never collide)

| Area | Owner | Files |
|---|---|---|
| Market backend | **Codex** | `core/market/**` (new), `host/rpc_market.py` (new) |
| Market frontend | **Claude** | `frontend/src/sections/market/**` (new), nav entry in `AppShell.tsx`, market route in `useAppStore.ts` |
| RPC registration | **Codex** | `rpc_catalog.py`, `rpc_dispatch.py` (server-side method registration only) |
| Client RPC wiring | **Claude** | `wsClient.ts` / a new `wsMarketRpc.ts` (client-side) — only when swapping the seam to live |

**No overlap:** backend = server + new core; frontend = new section + nav + client. The few shared
files (`AppShell`, `useAppStore`, `rpc_catalog`, `rpc_dispatch`) are split by side (nav/route =
frontend; method registration = backend) so even those don't collide. During the parallel phase the
frontend doesn't touch client RPC at all (it's on the mock seam), so collision surface is ~zero.

---

## 6. v1 Definition of Done

- Frontend: full dashboard + ticker detail + ⌘K live as a "Market" nav section, mock-seam, honest
  Preview badges, tokens matched, `npx tsc --noEmit` EXIT:0.
- Backend: `market.*` RPCs return contract-valid payloads; macro + portfolio + signals + edgar
  panels `live`; briefing synthesized; store persists; `py_compile` + tests green.
- Integration: hook swapped to real RPCs panel-by-panel; badges clear as panels go `live`.
- Out of scope for v1 (later phases): scheduler/auto-run, Telegram delivery, FRED macro calendar,
  tvscreener breadth, 100+ universe scale, Portfolio Copilot advisory.
```
