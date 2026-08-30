# Chart indicators

An extensible technical-indicator engine for the ticker workspace. 27 indicators
ship; adding a 28th means adding one entry to one file.

Branch: `codex/market-indicator-engine`, from `5015572`.

## The contract

Everything about an indicator is declared once, in a registry entry under
`src/copenet/host/frontend/src/sections/market/indicators/registry/`. That one
entry populates the picker, the settings form, the legend, the persisted layout
and the chart renderer. Nothing about an indicator lives in a component.

```ts
interface IndicatorDefinition {
  id: string;                    // stable — it is the persistence key
  name: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume' | 'ehlers';
  description?: string;          // only where the name does not carry it
  placement: 'price' | 'pane';   // overlay the candles, or take a pane below
  requires: IndicatorField[];    // 'volume' here gates the whole indicator
  inputs: IndicatorInput[];      // number | source | enum | boolean, with bounds
  outputs: IndicatorOutput[];    // series, in DRAW order, with default styles
  references?: IndicatorReference[];   // RSI 70/30, MACD zero, CCI ±100
  paneRange?: { min?: number; max?: number };  // fixed scale for a bounded pane
  warmup: (config) => number;
  compute: (bars, config, context) => IndicatorResult;   // PURE
  short: (config) => string;     // legend label, e.g. "EMA 20"
  format?: (value, config) => string;
}
```

### Layers

```
types.ts        the contract above
math.ts         sma/ema/rma/wma/stdev/atr/... — null-safe, causal primitives
config.ts       reading, defaulting and REPAIRING a config
calc/           pure calculations, grouped by family
registry/       the 27 definitions
state.ts        instances, transitions, versioned persistence
compute.ts      full-history computation, range slicing, memoisation
render.ts       the only module that knows both indicators and chart series
useChartIndicators.ts   the single hook CandleChart calls
Indicator{Picker,Rows,Settings}.tsx   the Plots-menu UI, generated from the registry
```

Two invariants hold everywhere below `calc/`:

1. **`null` is the only way to say "no value".** A zero denominator, a warm-up
   gap or missing volume all return `null` — never `NaN`, never `Infinity`. No
   consumer has to guess whether a number is real.
2. **Every function is causal.** Index `i` depends on indices `<= i` and nothing
   else. This is what makes "compute over full history, then slice" identical to
   "compute over the range" for every shared bar, and it is asserted across the
   whole registry rather than per indicator.

## Adding one indicator

1. Write the calculation in the right `calc/` file as a pure function over
   `IndicatorBar[]`. Return `null` wherever the value is not computable. Cite the
   formula's origin in a comment.
2. Add a definition to the matching `registry/` file.
3. That is the entire change. The picker, settings, legend, persistence and
   renderer pick it up.

The registry-wide test sweep covers the new indicator automatically: alignment,
finiteness, causality, determinism, warm-up honesty, flat-series and zero-volume
behaviour, and bar-index semantics. Add family fixtures for the actual values —
the sweep proves an indicator is well-behaved, never that it is correct.

`warmup` means **the bar by which every output exists**. Outputs may arrive
earlier (MACD's line precedes its signal; +DI precedes ADX); none may arrive
later, or the UI promises a series the chart draws empty.

## State and persistence

The layout is **workspace-sticky, not per symbol**. An analyst configures their
instrument once and looks at every asset through it; the values recompute per
symbol, the layout does not move. This follows the split the workspace already
draws (`tickerWorkspaceState.ts`): interval, range, log axis and the pane set are
sticky, while comparisons and financial overlays are symbol-scoped and reset on
switch.

One versioned blob under `mm-tw-indicators`:

```json
{ "version": 1, "instances": [ { "instanceId", "indicatorId", "config", "visible", "styles"? } ] }
```

`parseIndicatorLayout` is total: it never throws and drops anything it cannot
vouch for rather than repairing it into something the operator did not ask for.

- A version that does not match **exactly** is discarded, in either direction. A
  build that understands v1 must not half-read a v2 layout written by a newer
  build the operator has since rolled back from. **Bumping `LAYOUT_VERSION`
  therefore means writing a migration in the same commit, or accepting that every
  operator loses their layout once.**
- A retired `indicatorId` drops that row and keeps the rest.
- Configs are clamped to the registry's current bounds on load, so a
  hand-edited or older-build value can never reach a compute loop.
- Layouts are capped at `MAX_INDICATORS` (12).

Instance ids are `${indicatorId}#${n}` using the smallest free ordinal — readable,
and reproducible in tests without a clock or randomness.

Every transition (`addIndicator`, `configureIndicator`, `moveIndicator`, …) is a
pure function over the instance array. Nothing in `state.ts` touches the chart.

## Computation

Indicators compute over **every bar the payload carries**, then slice to the
visible range. Computing over the visible bars would restart every warm-up, so
switching 5Y to 6M would silently redraw the same EMA at different values.

Memoisation keys on `(bar-series identity, indicator id, config, barsPerYear)` —
not on the instance. So opening a popover recomputes nothing, two
identically-configured instances compute once between them, and a new or revised
last bar still invalidates. The cache is pruned to the live key set on every pass;
without that it grows by one entry per bar update per instance, forever.

`barsPerYear` is derived from the chart interval (252 / 52 / 12) so Historical
Volatility annualises against the bars it is actually looking at.

## Rendering and panes

`render.ts` is the only module that knows both what an indicator is and what a
chart series is. `CandleChart` gained one prop and one hook call.

- **Price overlays** go on pane 0 with the candles and share the right price
  scale, so an EMA is measured in the same units as the bars under it.
- **Pane indicators** each get their own pane below, ordered to match the layout.
- Panes are addressed by the live `IPaneApi`, never a stored index — `removePane`
  renumbers everything after it, and a cached index writes one indicator's data
  into another's pane.
- **Hidden means gone.** Hiding a pane indicator destroys its pane rather than
  emptying it; an empty pane still holding vertical space is the worse behaviour
  when hiding is what you reach for to get the price back.
- Bounded oscillators pin their own scale via `autoscaleInfoProvider`, so RSI at
  45–55 does not fill its pane and read as violent.
- The price pane holds a stretch factor of 4 against 1 per indicator pane.
  Lightweight Charts gives every new pane the same stretch, which would leave
  price on 40% of the canvas with three indicators.
- Indicator points are stamped with **candle timestamps**, never their own. The
  time axis is index-based: any series contributing a timestamp the candles lack
  injects a new equal-width slot. See `FINANCIAL_SERIES.md` §2 for the shipped
  bug this avoids.

### The cluster-box fix

`TICKER_WORKSPACE_REDESIGN.md` recorded panes as blocked because the SEC cluster
boxes are absolutely-positioned HTML at `priceToCoordinate` pixels and "would need
to become pane-aware". They did not. Their bottom clamp was `height - 24` — a
guess at the chart height less its time axis, fine while the price pane was the
only pane, and free to overhang into an indicator pane once one exists. It is now
pane 0's measured height. Pane 0 is always first and always starts at y=0, so its
coordinates still equal wrapper coordinates and nothing else in that positioning
code changed. Pane height also joined the transform identity, so adding a pane
forces a recompute even when it happens to preserve both price probes.

## Catalogue

27 indicators. Formula provenance is in a comment at each calculation.

| Trend (price pane) | Momentum (own pane) | Volatility | Volume | Ehlers |
|---|---|---|---|---|
| Simple Moving Average | RSI | Average True Range | On-Balance Volume | Super Smoother *(price)* |
| Exponential Moving Average | Stochastic | Average Range % | Chaikin Money Flow | MAMA / FAMA *(price)* |
| Weighted Moving Average | Stochastic RSI | Historical Volatility | | Instantaneous Trendline *(price)* |
| Hull Moving Average | MACD | | | Fisher Transform *(pane)* |
| Bollinger Bands | Rate of Change | | | |
| Keltner Channels | Commodity Channel Index | | | |
| Donchian Channels | Williams %R | | | |
| Rolling VWAP | ADX / DMI | | | |
| Supertrend | Money Flow Index | | | |

### Judgement calls

Each is commented at its definition; recorded here because they are choices, not
transcriptions.

- **Rolling VWAP, not VWAP.** A true VWAP is anchored to a *session* and
  accumulates intraday. The finest bar here is daily, where a session VWAP is
  identical to the bar's own typical price and measures nothing. What is
  meaningful is a rolling volume-weighted average, and the label always carries
  its bar count. Returns `null` where the window has no volume rather than
  falling back to an unweighted average that has quietly stopped being weighted.
- **Average Range %, not ADR.** This chart serves weekly and monthly bars too,
  where reading the number as a *daily* range is wrong. Measures mean
  `high/low - 1`, deliberately not true-range-based: including gaps would be
  measuring a different thing.
- **Historical Volatility annualises by the chart interval** by default.
  Hardcoding 252 overstates a monthly chart by ~4.6×. Can be pinned explicitly.
- **RSI and MFI report 50 on a dead-flat series.** `100 - 100/(1 + 0/0)` is
  undefined; the common library answer of 100 renders no movement at all as
  maximally overbought, which is the least defensible option available.
- **A zero range means "no information", not "extreme".** Stochastic, Williams %R
  and CCI return `null` when their window has no range, rather than 0 or 100.
- **Volume indicators go all-null without volume.** `market.ticker` returns
  `v: 0` for instruments with no reported volume, so this is live, not
  theoretical. An OBV drawn from zeros is a flat line that looks like a
  measurement.
- **Bounded oscillators are clamped** to the range they declare. The bound is a
  property of the formula; `100.00000000000001` only defeats the pane's scale.
- **`sma` sums its window directly** rather than sliding. The sliding form is
  O(n) but carries accumulated rounding forward for the whole series, which is
  enough to push a bounded oscillator outside its own range. Windows are tens of
  bars; the direct form costs nothing measurable.
- **Bollinger uses population deviation**, per Bollinger. The n-1 sample
  deviation widens every band slightly and is a common silent divergence.
- **Keltner is the ATR formulation** (Raschke's revision), which is what the name
  means in current usage — not Keltner's 1960 typical-price/range original.
- **Donchian includes the current bar**, the standard definition. The
  breakout-system variant that excludes it is a different indicator.
- **CCI uses mean absolute deviation**, not standard deviation. Substituting
  stdev is frequent and silently changes the scale.
- **Ehlers works in degrees.** `Math.atan` returns radians, so MAMA converts
  explicitly. This is not cosmetic: alpha is `fastLimit / deltaPhase`, and 5° is
  0.087 rad — feeding radians makes alpha ~57× too large, pins it to `fastLimit`
  on nearly every bar, and turns the adaptive average into a plain fast EMA that
  still looks entirely plausible on a chart.

## Controls: where they live

**The chart is where you tune what you can see; Plots is where you manage the set.**

Settings and remove sit on the chart itself — on a price overlay's legend row and
at the top-right of each indicator pane, anchored with
`IPaneApi.getHTMLElement()`. The gear opens the same `IndicatorSettings` form the
Plots menu uses: one settings surface, three doors onto it, never two copies.

Two things have no chart affordance and so live only in Plots:

- **Unhiding.** Hiding a pane indicator destroys its pane, so a hidden indicator
  has no chart presence at all — the Plots row is the only way back.
- **Pane order.**

Pane geometry is measured with a `ResizeObserver` on the pane elements rather
than sampled on an animation frame. Dragging a separator publishes no event, but
it does resize the panes either side of it, and a pane above resizing moves every
pane below it — whose own observers then fire. That covers separator drags, chart
resizes and pane add/remove with no polling.

Two details that are easy to get wrong, both of which shipped broken once:

- **Anchor to the plot area, not the pane element.** `getHTMLElement()` returns
  the pane ROW, which spans the full chart width including its price scale.
  Right-aligning controls to it puts them on top of the axis labels — present in
  the DOM, unreadable on screen. The plot area is found as the widest canvas
  inside the pane, which is robust to how the library orders its layers and stays
  correct when a left-hand axis appears for a financial overlay.
- **An element with `pointer-events: none` never matches `:hover`.** The pane-head
  strip must not receive pointer events, or it swallows the crosshair and the
  separator drag across the top of every pane — so `.tw-panehead:hover` matched
  only when the pointer was already on the (invisible) buttons. Controls reveal on
  `.tw-stage:hover` instead, and stay lit while their own popover is open.

Double-click-to-open-settings was considered and rejected: an invisible affordance
where a visible gear is already one click away in three places.

## Plots-menu integration

Plots is the home for chart layers, in the order an operator reaches for them:
volume, indicators, financial series. Rows are 24px; settings expand **in place**
below their row rather than opening a second surface, because the popover exists
to answer "what is on my chart" and a nested dialog puts the answer behind another
click. Discovery lives in the picker; the row list carries no descriptions.

Compare stays a separate tool. It rebases the price pane to indexed percent, which
is a mode change rather than another layer, and every price-anchored plot is
genuinely inapplicable while it is on. Indicators are suppressed from the chart
during comparison with the **layout untouched**, so leaving Compare restores
exactly what was there. Listing compared assets inside Plots would imply they
compose, and they do not.

Visual grammar follows `marketTokens.css`: 4px radius on controls, seams rather
than outlines, and **orange strictly reserved for an armed tool** — a row that is
merely selected or expanded is a lifted surface. Indicator series draw from their
own hue set with no orange in it; green and red appear only where they already
carry meaning (Supertrend direction, MACD histogram sign).

## Testing

`npm test` — 455 tests, of which ~250 are this subsystem.

| File | Covers |
|---|---|
| `indicatorMath.test.ts` | primitives, and a registry-wide sweep |
| `indicatorCalc.test.ts` | per-family numeric fixtures |
| `indicatorEhlers.test.ts` | Ehlers reference behaviour |
| `indicatorCompute.test.ts` | warm-up, slicing, memoisation, legend order |
| `indicatorState.test.ts` | transitions and the persistence contract |
| `indicatorRender.test.ts` | chart lifecycle against `fakeChart.ts` |

The registry-wide sweep is the load-bearing half: per-indicator fixtures catch a
wrong formula, but only a universal sweep catches the indicator added six months
from now that emits NaN on a flat series or reads a future bar.

**Do not read chart DOM from a background tab.** Lightweight Charts materialises a
pane's DOM row on a paint, and a background tab does not paint — so the DOM shows
the state from before your last change while the chart's own model is already
correct. This produced a confident false diagnosis during development ("an empty
pane is leaking 72px"); the row heights were simply stale. Query the model
(`panes()`, `paneIndex()`, `paneSize()`) for structure, and force a paint with a
screenshot before trusting any measured geometry.

**The Ehlers tests avoid snapshots deliberately.** These filters are recursive and
self-referential, so a snapshot of their own output proves only that they have not
changed — a transposed coefficient would be captured as "correct" on the first
run. Every assertion is derivable from outside the implementation: analytic fixed
points (coefficients summing to one make a constant a fixed point), the published
coefficients recomputed independently in the test, and — for MAMA — the
measurement it exists to make. Feeding a sine of known period, the Hilbert
discriminator recovers it to within 0.1 bars across 10–40. That is what makes the
degree/radian phase arithmetic trustworthy.

The renderer suite runs against a complete fake of the chart surface the layer
touches, and is built around failures that are invisible until the tenth toggle:
a series outliving its remove, a pane outliving its indicator, reference lines
re-created every render until the pane is striped with them. It ends by adding and
removing all 27 indicators and asserting the chart returns to exactly its price
pane each time.

One lesson from building it: an incomplete fake hides bugs behind the renderer's
own `try`/`catch`. `FakeChart` was missing `panes()`, so the stretch-factor call
was throwing into a catch and the price pane silently kept the wrong share.
**When adding a guarded call to `render.ts`, add the method to `fakeChart.ts` in
the same commit.**

## Performance

Pure calculations, memoised on stable configuration identities. No worker, and no
measurement suggests one is needed: a few thousand bars across ~20 indicators is
well inside a frame, and an unrelated re-render recomputes nothing at all.
Measure before adding one.

## Known limitations

- ~~**No per-pane legends.**~~ **Fixed.** The earlier claim that no API existed for
  anchoring DOM to a pane was wrong: `IPaneApi.getHTMLElement()` is a first-class
  accessor. A pane indicator now carries its own legend and controls inside its
  pane, measured against that element with a `ResizeObserver` — no knowledge of
  Lightweight Charts' internal markup and no arithmetic over summed pane heights.
  The top-left stack now carries price overlays only.
- **Bands are two lines and a dashed midline, with no shaded fill.** A fill needs
  a custom series primitive (v5 supports `attachPrimitive` /
  `ICustomSeriesPaneView`) per band family.
- **Interior gaps connect.** Warm-up nulls simply start the series later, but a
  null *inside* a series (a flat Stochastic window) is dropped and the line draws
  through it. Honest gaps need one series per segment, as
  `splitFinancialOverlaySegments` does for the financial overlay. Rare enough to
  defer; not free.
- **Pane heights are not persisted.** Separators drag fine and the controls track
  the new geometry, but the resulting sizes are not read back into the layout, so
  they reset on reload. The initial split follows the fixed 4:1 stretch.
- **`insufficientHistory` is reported but not explained.** The row and legend read
  "needs history" without saying how many bars are missing, though `warmup` has
  the number.
- **The automated browser pane cannot verify painting.** It runs with
  `visibilityState: "hidden"`, so `requestAnimationFrame` never fires and
  Lightweight Charts never paints — pane creation was confirmed through the
  chart's own model (`panes()`, `paneIndex()`, `paneSize()`), not the DOM, which
  shows no pane row there. Same constraint recorded in `AGENTS.md`. Visual
  confirmation of the painted panes and of interactive pane resizing is an
  operator step.
- **No ticker formula language.** Deliberately out of scope for this branch.

## Follow-up

- Band fills via a series primitive.
- Segment-split series so interior gaps read honestly.
- Persisting dragged pane heights into the layout.
- A "needs N more bars" reading on `insufficientHistory`.
- Indicators computed on a comparison series, which would make Compare a plot
  rather than a mode — the end state `TICKER_WORKSPACE_REDESIGN.md` already
  records as the better one.
