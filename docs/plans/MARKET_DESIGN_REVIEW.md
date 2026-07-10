# Market Monitor — First-Principles Design Review

**Date:** 2026-07-10
**Author:** Claude (product-architect pass, requested by Patrick)
**Status:** Accepted direction pending Patrick's sign-off on the forks in §8
**Inputs:** Codex "morning decision engine" roadmap, Gemini "market cockpit" roadmap, the live
product as of `7f98d32`, and the standing product philosophy (weekly/monthly investor, thesis
driven, regime over prediction, evidence-traceable synthesis).

The brief was explicitly *not* "more ideas." It was: maximize one metric —

> *"I should instinctively open this every morning because it consistently tells me something I
> didn't know that materially changes how I understand markets."*

---

## 1. The verdict

CopeNet Markets should not become a cockpit. It should become a **briefing officer with
receipts** — and, over years, the only market tool that knows *you*.

Codex designed a Bloomberg for a professional making twenty decisions a day. Our user makes
maybe three real decisions a month. Bloomberg's job is latency reduction for experts who already
know what to look for; CopeNet's job is **synthesis for one person with fifteen minutes**. The
metric is not data coverage — it is decision quality per month, and trust in the synthesis,
compounding over time.

The clone test for every surface, present and proposed:

> Does it show **numbers for the user to interpret** (terminal clone), or **claims the system
> already interpreted, with receipts** (intelligence system)?

Panels of numbers are clone drift. Sentences with evidence chips are the product.

## 2. Assumptions we're making that are wrong

**A1. "The user is a morning analyst at a desk."** Patrick is a shift supervisor finishing
school. The 9:45 sweep gets ~60 seconds on a phone; real engagement happens at night and on
weekends. The actual usage cycle is **morning orientation (60s, phone) → evening research
(30+ min, desktop) → weekly decision session**. We have been designing one page for what is
actually three distinct moments. The "Wall Street at 6:30am" framing in both roadmaps is
borrowed from a different user's life.

**A2. "More model inputs improve the reads."** Unmeasured. We wired fundamentals, live news,
insider evidence, and multi-year structure into the reads — each verified as *present in the
prompt and used in the prose* — but zero evidence yet that any of it improves **calibration**.
The Forward Ledger exists precisely to answer this and its first claims resolve ~Aug 5.
Feature-adding is currently outrunning the feedback loop. Until the ledger has resolved data,
every new model input is faith, not engineering.

**A3. "The dashboard is the surface."** CopeNet's thesis is a continuity engine. The market
monitor is drifting toward a standalone terminal when its endgame is being one voice in
"I'm back." The brief, Pulse, and eventually Telegram are the real delivery surfaces; the
Monitor page is the drill-down, not the product.

**A4. "Coverage gaps are the bottleneck."** Everything we display is **realized** data — prices
that already printed, filings already filed. We hold no *expectations* data: no estimates, no
implied moves, no positioning. "What is the market pricing that I'm probably not?" is
unanswerable today with any amount of yfinance OHLCV. This is the single largest genuine
information gap (§6).

**A5. "The system knows the user's theses."** It doesn't. "Thesis driven" is in the philosophy,
"thesis-killers" are in every model read — but no thesis is stored anywhere. The theses live in
Patrick's head, so the system structurally cannot answer "what thesis got stronger this week?"
This is the cheapest wrong assumption to fix and the most differentiating (§6).

## 3. Questions, not data — the canonical set

Every surface must claim at least one of these or it is entropy:

| # | Standing question | Cadence |
|---|---|---|
| Q1 | What changed while I wasn't looking? | every look |
| Q2 | What actually matters today — for *my* names? | morning |
| Q3 | Why does my watchlist look the way it does? (macro → sector → name transmission) | morning |
| Q4 | What thesis of mine just got stronger or weaker? | morning/weekly |
| Q5 | What could move my names in the next 7 days, and what result would surprise? | morning |
| Q6 | What is the market pricing that I'm probably not? | weekly |
| Q7 | What deserves research tonight? | morning → evening |
| Q8 | Am I (and is the model) becoming overconfident? Where are we miscalibrated? | weekly |
| Q9 | If I had to act this week, what exactly and what kills it? | weekly |

## 4. The question test applied — what survives, what dies

### Survives (answers a standing question)

| Surface | Question | Disposition |
|---|---|---|
| Morning Brief + Sentinel | Q1 | **Becomes the entire first viewport** (§5) |
| Global tape / overnight transmission (planned) | Q1, Q3 | Build — feeds the brief, not a new panel |
| Catalyst calendar, scoped to watchlist + CPI/FOMC | Q5 | Build — one strip in the brief |
| Ticker detail page (chart, SEC activity, reads) | Q7, Q9 | Keep — the research surface |
| RRG | Q3 | Keep — drill-down; the "improving→leading transitions" line surfaces in the brief |
| Forward Ledger | Q8 | Keep + expand — the moat |
| Portfolio panel | Q2, Q9 | Keep — drill-down |
| Regime read | Q1, Q3 | Keep — first line of the brief |

### Dies as a persistent panel (absorbed or demoted)

| Surface | Problem | Disposition |
|---|---|---|
| BacktestLab at top of Monitor | Lab tool holding the most valuable real estate, answers no morning question | On-demand from ticker/portfolio context |
| Macro board (grid of sparklines) | Numbers-to-interpret; Q3 wants the *transmission sentence* | Collapses into a thin tape ribbon + brief prose |
| Contrarian panel | No standing question; model read already carries thesis-killers | Absorbed into brief/read |
| Speculative lane panel | Its useful part is the model's lane comment | One brief line when something changes |
| Soft-bottoming watch strip | Rare-event signal displayed permanently | A brief line *when it fires* (rare-event alerts, per original philosophy) |
| Accumulation/Trend full lists, always visible | Reference material, not news | Behind one click; brief mentions only *changes* |

### Rejected from the roadmaps

| Proposal | Why |
|---|---|
| Opportunity funnel + trade construction desk (Codex 7/8) | Answers a day-trader's question. Wrong user. Q9 is served by ticker reads + thesis registry instead |
| Pre-market anomaly scanner (Gemini 3) | Same, plus weak pre-market data |
| Whole-market MRI, full version (Codex 2) | The honest fix (stop calling watchlist breadth "breadth") costs 5% of this. Use S&P-constituent or equal-weight/cap-weight proxies; revisit only if a decision ever hinged on finer breadth |
| Volatility "weather station" (Codex 5) | One brief line ("front-window fear is event-driven: CPI Thursday") from three index ratios. A station is clone drift |
| Modular drag-grid layout (Gemini 10) | Layout churn, zero information gain, against the subtraction rule |
| Glassmorphism/neon reskin (Gemini) | No |

## 5. The 60-second screen

The first viewport **is the brief**, structured as answers, ~12 lines, phone-first, never
scrolls. Everything currently on the Monitor tab moves below it or behind a click.

```
REGIME    Disinflationary chop, 12th day. No change since yesterday.        [why →]
OVERNIGHT Asia soft (Nikkei -1.2%), copper -2.1% → your industrials
          opened heavy; yields eased, growth futures firm.                  [tape →]
MATTERS   1. SOFI reports in 6 days — first print since revenue went
             negative YoY. Implied move n/a (no options data yet).
          2. ASX insiders: 6th consecutive sell week, -$352M/90d.           [filing →]
          3. XLF crossed improving→leading on the RRG with breadth
             confirming.                                                    [rrg →]
THESES    ⬆ "SOFI monetization inflection" — ARK added $1M            [evidence →]
          ⬇ "Semis lead this cycle" — SMH 3rd week weakening quadrant
NEXT 7D   CPI Thu · FOMC minutes Wed · SOFI earnings Jul 16
LEDGER    Model: 6 claims pending, first scores Aug 5. You: no action
          taken on last 3 flagged items.
          [research tonight: 2 queued]
```

Every line carries receipt chips (filing links, chart links, evidence items) — traceability is
already our rule; this makes it the UI.

**Real-estate law:** persistent = tape ribbon (one thin row) + the brief. Everything else —
RRG, portfolio, lists, lab, ledger detail — is drill-down. Nothing new gets added *to* the
first viewport; new capabilities get added *to the brief's vocabulary*.

## 6. Missing information that would actually change decisions

1. **A thesis registry.** First-class stored objects: name, statement, linked symbols,
   invalidation conditions, created date. The sweep scores new evidence against them; the brief
   reports deltas (Q4); ticker reads get the user's actual thesis in the packet instead of
   guessing; the ledger can eventually score *theses*, not just model leans. Both outside
   roadmaps proposed data features; neither proposed capturing the user's beliefs as data.
   This is the intelligence-system move, and it's cheap — a store, two RPCs, a brief section,
   a packet section.
2. **Expectations data.** Analyst estimates (yfinance exposes them), consensus revenue/EPS
   ahead of watchlist earnings, and options-implied earnings moves for the few names that
   matter. Without this Q6 is unanswerable. Scope: watchlist-only, on-demand — not a
   market-wide vol surface.
3. **Self-calibration.** Ledger phase 2: feed resolved outcomes back as brief lines ("your
   bullish leans are 4/6; the model's chop calls are 9/11") and log *user actions* (acted /
   passed) alongside model claims, so Q8 covers both parties.

## 7. Why indispensable after two years

Because of the assets that **compound**: the ledger (measured track record of the model *and*
of Patrick's own leans and actions), the thesis registry history (what he believed, when, what
killed it), and the evidence archive tied to both. In two years CopeNet can say: *"The last
nine times you wanted to add on a dip like this, seven worked — but your speculative-lane
entries are 2 for 11, and you're most miscalibrated when insider sells coincide with a
narrative you like."* No terminal on earth can say that, because no terminal knows the user.
That is the continuity-engine thesis applied to markets. Charts and tapes are commodities;
the memory is the moat.

## 8. The workflow (designed for the actual life)

- **09:40** — sentinel sweeps (exists). Brief generated (exists), now question-structured.
- **09:45** — push to phone: the brief's first four lines via Telegram (messaging config
  exists; send function is the missing piece). Reading it is 60 seconds.
- **Any tap** → ticker page. Anything worth more than two minutes → **"research tonight"**
  action: queues an Agents-chat prompt with the fact packet attached (Q7 — the bridge from
  orientation to research, using the market.* tools that already exist).
- **Evening** — open CopeNet, the research queue is waiting; deep reads, backtests, thesis
  updates.
- **Sunday** — the weekly session is the *real decision point* for a weekly/monthly investor:
  ledger resolutions, thesis review (Q4/Q8/Q9), watchlist grooming. Deserves its own brief
  flavor eventually (weekly retrospective rather than overnight delta).

Forks needing Patrick's call: (a) adopt the brief-first viewport and panel demotions in §4–5;
(b) thesis registry as a build priority; (c) Telegram push before or after the global tape.

## 9. Revised build order

This review changes my own earlier recommendation (which was feature-sequenced): the brief
redesign moves to #1 because every other item feeds it.

1. **The 60-second brief** — restructure `brief.py` output + `MorningBrief.tsx` into the §5
   layout; demote BacktestLab/macro grid/always-on lists; add receipt chips. No new data.
2. **Global tape** — overnight cross-asset snapshot + ATR-normalized surprise + transmission
   sentence, feeding brief line 2 and the model packet. (Feasibility verified: yfinance 1.5.1.)
3. **Thesis registry v1** — store, RPCs, brief deltas, packet section.
4. **Catalyst strip** — watchlist earnings dates + CPI/FOMC/payrolls into "NEXT 7D".
5. **Telegram push** of the brief — closes the phone loop.
6. **Ledger phase 2** — self-audit lines + user-action logging (after Aug 5 resolutions).
7. Then, by evidence not enthusiasm: expectations data, vol one-liner, breadth-proxy honesty
   fix, RRG universe expansion, real historical scenario replay.

Everything else from both roadmaps is parked until a standing question claims it.
