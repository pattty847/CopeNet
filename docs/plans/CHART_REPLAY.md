# Chart replay

Walk the ticker chart forward one bar at a time — candles, indicators, filing markers and
the financial overlay all stopping at the same instant — so a setup can be read the way it
was actually seen, without the rest of the chart already answering the question.

Toolbar: the ⏪ button in the period group, or `r`. That **arms** the picker — a vertical
cut follows the pointer with everything to its right dimmed, and the click commits that bar
as the start. `Esc` backs out. Once running: `space` play/pause, `←`/`→` step, and the
scrubber for anything further away than a few bars.

## The one rule

**Replay is a truncation, and it happens once**, in `useTickerViewModel`. Every series the
chart draws is derived there from `bars`; cutting `bars` at the cursor cuts all of them.

That is the whole design. The alternative — each consumer filtering its own data against a
replay timestamp — is how a replay leaks: one overlooked derivation draws next quarter's
8-K on a chart the operator believes stops at last Tuesday, and nothing on screen says so.
If you add a chart series, derive it from `bars` and it is replay-correct for free. If it
genuinely cannot be (it is fetched per-request, say), it must be *hidden* during replay, not
left live.

Three derivations need the cursor explicitly, because they are filtered by predicate rather
than sliced from `bars`:

- SEC evidence and chart events (`replayTime` upper bound). Undated evidence is **dropped**
  during replay — it cannot be shown to be in the past.
- The indicator history. See below.
- The agent capture. See below.

## The cursor is a time, not an index

`replay/chartReplay.ts` stores the cursor as a bar timestamp. An index would be silently
wrong the moment the operator switched interval or range underneath it — 260 weekly bars
and 1250 daily bars do not share position 140, so the replay would land on a different date
and the chart would look perfectly normal. A timestamp resolves through
`replayCursorIndex()` to the last bar at or before it, whatever the bars now are.

A cursor that predates the first bar (what shortening the range produces) resolves to bar 0
rather than to "no bars": a recoverable state instead of one that reads as a broken chart.

## Indicators are recomputed, not filtered

`compute(history, visibleCount, …)` aligns its outputs by assuming the visible window is a
**suffix** of the history it was given. Replay's window is a prefix of the visible range, so
the history itself is cut (`indicatorHistory`) rather than the outputs being filtered after
the fact.

Because every calculation in the registry is causal — asserted registry-wide, see
`CHART_INDICATORS.md` — the retained values are identical to the untruncated ones. The cut
costs one recompute per step (a few ms over full history) and buys an indicator that
genuinely never saw the future, including the memoised path: the computer keys on bar-array
identity, so each step is a real recompute rather than a stale hit.

## Off → arming → active

Arming is its own phase, not a flag on `active`, because **nothing is hidden yet** while the
operator is choosing. The chart still holds the whole range; the future is dimmed, not
removed, so the choice is made against history that is still visible. Committing is what
cuts. That also means a capture taken while arming needs no special handling — there is
nothing to disclose.

## Fit once, then only slide

Off replay, every data write refits, which is right when the payload changes underneath you.
Under replay it is exactly wrong twice over: refitting on every step re-zooms the chart as
bars arrive, and it throws away whatever pan or zoom the operator set.

So replay **fits once**, on the step that opens it (`replayEntryRange`), and after that only
**slides**: the visible logical range moves by the number of bars revealed. That holds the
newest candle still and pulls history left underneath it, and because the slide is relative,
the operator's own framing rides along untouched.

Two details that will bite:

- The prior range is read **before** `setData`, never after, so the slide is computed from
  the range the chart actually had rather than from whatever the write left behind.
- The comparison/volume effect also called `fitContent`, and its dependency
  `comparisonLines` is rebuilt from the truncated bars — so it fires on *every* replay step
  and would have undone the slide a frame later. It is guarded on the same flag.

## What the agent sees

A capture taken mid-replay is truncated too. Everything derived from `bars` stops at the
cursor already; the D/W/M candle resources are read straight off the payload and are cut
explicitly in `viewState/capture.ts`, with `metadata.replay.{truncatedAt,hiddenBars}` saying
so. `settings.replay` carries the cursor, the transport state and one honest caveat: the
research panels and the displayed quote below the chart are **still live**. Replay is a
chart mode, not a time machine for the whole workspace.

## Files

| File | Role |
|---|---|
| `replay/chartReplay.ts` | Pure model: speeds, cursor resolution, stepping, hidden bars |
| `replay/useChartReplay.ts` | Transport state and the playback clock |
| `replay/ReplayBar.tsx` | The strip under the chart |
| `useTickerViewModel.ts` | The truncation |
| `CandleChart.tsx` | `trailingTimes` whitespace |
| `viewState/capture.ts` | Truncated capture + `settings.replay` |

Tests: `tests/chartReplay.test.ts`, `tests/replayBar.render.test.tsx`, and the replay case
in `tests/chartCapture.test.ts`.

## Not built

- **Replaying the research panels.** Fundamentals, evidence and the quote stay live, and the
  capture says so rather than pretending otherwise.
- **Bar-by-bar paper trading.** Replay renders history; it records no decisions against it.
