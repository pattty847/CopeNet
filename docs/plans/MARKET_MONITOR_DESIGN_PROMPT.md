# Market Monitor — Claude Design Prompt

Draft prompt to feed the Claude Design model for the CopeNet Market Monitor dashboard.
Companion to `MARKET_MONITOR.md` (the system blueprint). Tweak freely before sending.
**Tip:** attach `docs/imgs/copenet-agents-console.png` to Claude Design as a visual reference so it
matches the existing app aesthetic.

---

## PROMPT

**You are designing a dashboard screen for an existing product. Match and extend its visual
language — do not invent a new design system.**

### The product
CopeNet is a personal, local "continuity engine" — a calm, dark, premium **operator console**
(React + Vite + Tailwind). Its existing look: near-black background (`#000103`), a single warm
**amber accent** (`#FB9423` / `#c27a3a`), uppercase tiny section labels, quiet label/value rows,
generous breathing room, sans body type with monospace for technical/numeric detail, a thin left
icon-rail for nav, and a three-column workspace feel. Think "refined mission control," NOT a busy
Bloomberg terminal. (Reference screenshot attached.)

### What we're designing
A new **Market Monitor** workspace: a daily market-orientation dashboard for a long-term investor.
Its whole reason to exist is that the owner should *want* to open it every day — it must be
**intuitive, calm, and genuinely nice to look at**, while still being information-rich on demand.

### Who it's for (design for this person, specifically)
A long-term accumulator who **enjoys watching the market** (pattern-hunting, pullback zones, long
horizons) but doesn't day-trade. He glances daily, thinks in **weekly candles with daily
confirmation** (never intraday), wants to feel **informed enough to be "the person people ask about
the market,"** and wants to spot good opportunities without staring at 40 charts. He values honesty
over hype — evidence-based reads, never crystal-ball predictions.

### The job of this screen
At a glance: *"What is the market doing, what actually needs my attention today, where is money
rotating, and how is my book?"* — then let him drill into any name for depth.

### Information architecture (proposed — refine if you have a better idea)
1. **Daily Briefing hero (top):** a calm, plain-English summary (LLM-generated) of the market read,
   the current **regime** (risk-on / risk-off / chop / event-risk), and the 2–3 items that genuinely
   need attention today. Must read like a trusted human brief, with explicit caveats — never
   over-confident.
2. **Cockpit grid (middle):** a calm grid of panels (below). Curated, not crowded — depth on demand.
3. **Ticker detail (drill-down):** full-screen view for one asset — the chart + its signals,
   benchmark verdict, and evidence.

### Panels to design (cockpit grid)
- **Macro Board** — DXY (dollar), 10Y yield, VIX, gold, oil, BTC/ETH as risk gauges. Compact, glanceable, "what's the weather."
- **Sector Rotation Graph (RRG)** — *signature panel, make it beautiful.* A coordinate plane: X = relative strength vs benchmark, Y = relative-strength momentum. Four labeled quadrants (top-right **Leading**, bottom-right **Weakening**, bottom-left **Lagging**, top-left **Improving**). One dot per sector ETF (XLK/XLE/XLF/XLI/XLV/XLP/XLY/XLU/XLB/XLRE + SMH) vs the S&P, each with a **fading tail** showing its path over recent weeks (rotates clockwise). Hover for detail. This visualizes where money is flowing.
- **Accumulation Watch** — quality names sitting in pullback zones (good long-term "add" candidates), ranked by confluence. Each row: how far below key moving averages, drawdown depth, oversold state, and a clear "why this is interesting."
- **Trend-Change Watch** — names whose **weekly** trend just shifted, confirmed by daily.
- **Portfolio** — his holdings with **live P&L** (cost basis known), plus an "add zone?" nudge per name.
- **Speculative lane** — clearly separated, clearly labeled. Tracked speculative positions with P&L + a defined **exit/target/invalidation**. Must feel distinct from the disciplined core — honest labeling, not blurred into the rest.
- **Evidence & News Feed** — per-ticker catalysts: SEC insider cluster-buys, material 8-K filings, plus relevant web news (cited sources). The "why did this move" feed.
- **Contrarian / thesis-killer notes** — for any highlighted signal, "what would make this wrong?" Surfaced as a first-class element, not buried. This is the honesty feature.

### Ticker detail view
- A **TradingView Lightweight Charts** candlestick chart (weekly primary, toggle to daily).
  Capabilities to design around: candlesticks, overlay line series (moving averages, MAMA/FAMA),
  a histogram sub-pane (volume), **event markers** on the time axis (insider buy ▲, 8-K ◆), and
  price lines. (No built-in indicator UI — all overlays are pre-computed series. Small TradingView
  attribution logo must be visible.)
- Alongside the chart: the name's **benchmark verdict** ("beats / loses to VOO + sector ETF on a
  risk-adjusted basis"), its signal readout, and its evidence/news.

### Aesthetic & brand constraints
- Extend CopeNet's existing look: dark `#000103` canvas, amber `#FB9423` as the *single* accent,
  uppercase micro-labels, quiet label/value rows, calm spacing.
- Use color with restraint and meaning: amber for emphasis/accent; green/red ONLY for genuine
  up/down P&L and signal direction; everything else muted grayscale. No rainbow dashboards.
- Numeric/technical detail in monospace. Generous whitespace. Premium and calm.
- **Honest empty/loading states** — when there's no signal, say so cleanly. Never fake precision or
  populate phantom data.

### Hard anti-goals
- NOT a day-trading terminal; no intraday/low-timeframe framing.
- NOT noisy — no wall of blinking tickers, no information overload. Calm-curated, depth on demand.
- NO crystal-ball / predictive language anywhere; reads are evidence-based with caveats.
- Don't bury the contrarian view or the "what's my book doing" answer.

### Responsive
Design for **two surfaces**: a desktop operator workspace AND an **installed iPhone PWA** (the owner
moves between Mac and phone daily). On mobile it should stack to a single, thumb-friendly column —
Briefing hero first, then the most important panels — without losing the calm aesthetic. Show how
the RRG and the chart adapt to a narrow screen.

### What to deliver
1. A **layout blueprint** for desktop (the briefing hero + cockpit grid + how drill-down works).
2. **Annotated mockups** of: (a) the main dashboard, (b) the ticker-detail view with the chart,
   (c) the mobile/PWA stacked layout.
3. A focused treatment of the **RRG panel** (it's the signature piece).
4. A short **component inventory** + visual-hierarchy notes (type scale, spacing, color usage)
   consistent with the CopeNet tokens above.
5. Brief rationale for any IA choices you'd change.

---

## APPENDIX — Design tokens (paste this when Claude Design asks for Tailwind/CSS)

**Stack:** React + Vite + **Tailwind v4 (CSS-first** — tokens defined via `@theme` in
`index.css`, no `tailwind.config.js`). Design primarily for **dark mode** (that's the product's
signature look). Tokens are exposed as Tailwind colors like `bg-shell-panel`, `text-operator-text`,
`text-operator-accent`, `border-operator-border`, etc.

**Fonts:** Inter (`--font-sans`, body/UI) · Cormorant Garamond (`--font-display`, elegant serif for
big headers) · JetBrains Mono (`--font-mono`, all numbers/technical detail).

**Dark-mode color tokens (the real values):**
```
bg / canvas        #000103 / #010204     (near-black)
panel              #080809               (cards)
panel-strong       #111216               (raised/nested)
text               #fefcf4               (warm off-white — NOT pure white)
muted              #a29b90               (warm taupe-gray)
accent             #fb9423               (the single amber accent)
accent-soft/glow   rgba(251,148,35,.12) / .20
border             rgba(254,252,244,.06) (hairline)
border-strong      rgba(251,148,35,.16)  (amber-tinted)
success            #69c589   error #d96d5f   (use ONLY for real up/down P&L + signal direction)
```
Shadows are soft and deep: `--shadow-shell`, `-hover`, `-xl` (e.g. `0 8px 20px rgba(0,0,0,.18), 0 28px 56px rgba(0,0,0,.24)`).

**Type scale & spacing idioms (very small, tight, warm):**
- Section header: `text-[10px] font-semibold uppercase tracking-wider text-operator-muted` (or `tracking-[0.14em]` at `text-[9.5px]`)
- Value / row label: `text-[11px] font-medium text-operator-text`
- Pill / status badge: `rounded-full border border-operator-border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-operator-accent`
- Honest empty state: `text-[11px] text-operator-muted/85 italic`
- Radii: `rounded-lg` / `rounded-md` for cards & controls, `rounded-full` for pills, `rounded-2xl` for large surfaces.
- Padding stays tight: `px-2 py-1` typical; chrome type lives in the **9–12px** range.

**Representative component pattern (mirrors `InspectorOverview.tsx`):**
```tsx
<section className="rounded-lg border border-operator-border bg-shell-panel p-3">
  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">Runtime</h3>
  <div className="mt-2 space-y-1.5">
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-operator-muted">Provider</span>
      <span className="text-[11px] font-medium text-operator-text">OpenAI Codex</span>
    </div>
    <div className="flex items-center justify-between">
      <span className="text-[11px] text-operator-muted">Status</span>
      <span className="rounded-full border border-operator-success/25 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-operator-success">Connected</span>
    </div>
  </div>
</section>
```
This is the canonical look: a bordered near-black card, a tiny uppercase amber/muted header, quiet
`label —— value` rows in 11px, amber for emphasis, green/red only for true status.
