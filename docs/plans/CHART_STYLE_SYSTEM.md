# Chart Style System

Status: audited 2026-09-18, not built. One settings popup for anything painted on the chart.

## The idea

A settings menu is not a drawing feature. Everything on the chart is built from the same few
parts, each born from the one before it, and a thing's menu is the parts it is made of plus
one compartment of its own:

| Part | What it styles | Who has it |
| --- | --- | --- |
| stroke | color, width, solid/dashed/dotted, opacity | every line: trendline, indicator output, revenue, comparison, alert level, cost line, candle wick |
| fill | color, opacity | zone, measurement, position boxes, indicator cloud, volume bars, candle body |
| text | label, size | note, callout, any labelled drawing |
| own | what only this thing has | fib ratios, MA length and source, AVWAP anchor, overlay metric and period |

Style is how a thing LOOKS. What it COMPUTES stays in `own`. The revenue line gets a color
and a width; it never gets a "length".

## What paints today

| Thing | Painted by | Style lives in | Saved in | Click target | Reaches the model as |
| --- | --- | --- | --- | --- | --- |
| Drawings (14 kinds) | `drawings/primitive.ts` | `ChartObject.color/lineWidth/lineStyle/fillOpacity` | backend chart document: per symbol, revisioned, undoable | custom `hitDrawing` | Drawings table, color as a word |
| Indicator outputs (27) | `indicators/render.ts` | registry default + `IndicatorInstance.styles[output]` | `localStorage mm-tw-indicators`, versioned, workspace-sticky | none | matrix columns; metadata also ships hex color, width and style per output |
| Indicator cloud, reference lines | `cloudPrimitive.ts`, `createPriceLine` | registry constants | not editable | none | reference values only |
| Candles | `CandleChart.tsx` | `MM.up` / `MM.down` constants | not editable (`candleStyle` and `mm-log-scale` only) | none | `settings.candleStyle` |
| Volume | `CandleChart.tsx` | two `rgba` literals | not editable | none | `v` column |
| Financial overlay (revenue, P/E) | `CandleChart.tsx` LineSeries | `#8fb8e8`, width 2 | not editable | none | `chart:financial` resource |
| Comparison lines | `chartComparisonSeries.ts` | `COLORS[index]`, width 2 | not editable | none | `comparison:*` resources |
| Alert levels | `chartPriceAlerts.ts` price lines | `MM.accent`, `#8fb8e8` | not editable | none | not sent |
| Position cost line, fills, shading | `position/usePositionOverlay.ts` | `#8fb8e8` dotted | `localStorage mm-position-display` (toggles only) | none | `account:position` when opted in |
| SEC markers, cluster boxes | series markers + HTML | constants | not editable | marker id / HTML | `chart:evidence` |
| Forecasts | `forecasts/primitive.ts` | constants | backend | custom | forecast tools |

## Findings

1. **The vocabulary already matches.** Drawings carry `color, lineWidth, lineStyle` and so does
   `IndicatorStyle`, per output. Two subsystems independently chose the same three fields. The
   abstraction is a rename and a shared home, not an invention.
2. **Indicators store width and style but only offer color.** `IndicatorSettings` renders one
   color input per output. `lineWidth`/`lineStyle` overrides are persisted and rendered with no
   control to set them.
3. **Three settings surfaces, one job.** `DrawingToolbar` (on-chart bar), `IndicatorSettings`
   (a `FloatingPopover` behind a gear), and the `ChartDrawingsPanel` side editor. The popover
   shell the shared popup needs already exists: `components/FloatingPopover`.
4. **Series click targets are free.** Lightweight Charts 5.2 hit-tests line, candle and histogram
   series itself and reports `hoveredSeries` on click (tolerance via the `hitTestTolerance` series
   option); price lines report their `id` as `hoveredObjectId`. One `Map<ISeriesApi, target>`
   gives every indicator, overlay and comparison line a click target with no custom geometry.
   Touch needs the tolerance raised on coarse pointers.
5. **Three persistence homes, and that is correct.** Drawings are per-symbol documents the agent
   can edit; indicator layout is workspace-sticky; chart-level style (candles, volume, overlays)
   is a preference. The popup must not move storage. Each source adapts itself and keeps its
   own store. The third home does not exist yet: everything in it is a hard-coded constant.
6. **The model gets style tokens it cannot use and lacks the one it needs.** Indicator metadata
   ships hex color, width and style per output every turn. The operator says "the blue line"; a
   hex does not resolve that. Drawings already send a color word. Do the same in
   `metadata.columns` and drop width/style.

## Design

`sections/market/chartStyle/`:

- `types.ts`: `StrokeStyle {color, width, style, opacity}`, `FillStyle {color, opacity}`,
  `TextStyle {text}`. The palette, widths and styles move here from `drawings/kinds.ts`.
- `StyleFields.tsx`: `StrokeFields`, `FillFields`, `TextFields`. The only place these controls
  are written.
- `Styleable`: what any painted thing hands the popup.

```ts
interface Styleable {
  id: string;                 // 'drawing:<id>' | 'indicator:<instanceId>' | 'series:candles' ...
  title: string;
  strokes: Array<{ key: string; label: string; value: StrokeStyle; onChange(next: Partial<StrokeStyle>): void }>;
  fills: Array<{ key: string; label: string; value: FillStyle; onChange(next: Partial<FillStyle>): void }>;
  text?: { value: string; onChange(next: string): void };
  own?: ReactNode;            // fib ratios, the indicator inputs form, overlay period
  actions: { hide?(): void; remove?(): void; lock?: { value: boolean; toggle(): void }; reset?(): void };
}
```

- `ChartObjectSettings.tsx`: one popup, renders any `Styleable`. Double-click opens it; on touch,
  tap selects and the bar's gear opens it.
- Adapters live with their subsystem and write to their own store: `drawings/styleable.ts`,
  `indicators/styleable.ts`, `chartStyle/seriesStyleable.ts`.
- One chart selection (`{kind, id}`) replaces `selectedObjectId`, so the top bar, Delete and
  Escape work for an indicator line exactly as they do for a trendline.
- New store `mm-chart-style` (versioned like the indicator layout) for candles, volume,
  financial overlay, comparison, alert and position line style.

## Delta: the TradingView dialogs, mapped (2026-09-18)

Reference: TradingView's Trendline, Anchored VWAP and SMA settings dialogs. Same shell for all
three; only the tabs differ. That is the design above with one correction: the compartments are
**tabs**, and there are five of them, not four.

| TV tab | Our compartment | Drawings today | Indicators today | Gap |
| --- | --- | --- | --- | --- |
| Inputs | `own` | none (fib ratios, AVWAP source are constants) | registry `inputs`, basic + advanced | AVWAP source and bands; fib ratios |
| Style | `strokes` + `fills` | color, width, style, fill opacity | color only in the UI; width/style stored | per-output show/hide, plot type, precision, price-scale label |
| Text | `text` | label string only | n/a | size, bold/italic, alignment |
| Coordinates | **new: `anchors`** | price editable in the side panel; date is not | n/a | date + price per anchor, as bar-exact fields |
| Visibility | **new: `visibility`** | a drawing shows only on the timeframe it was made on | one `visible` flag | per-timeframe checkboxes (D / W / M) |

`Styleable` gains `anchors?` and `visibility?` beside `strokes`, `fills`, `text`, `own`. A tab
appears only when the thing has that compartment, exactly as TV drops Text and Coordinates for
an SMA.

What the screenshots confirm or change:

- **Extend is a dropdown on one Trendline.** TV models trendline / ray / extended line as a
  single object with `Don't extend | Right | Left | Both`. Keep our separate toolbar tools (they
  are the fast path); each just presets the extent, and the Style tab can change it afterwards.
  This settles the "collapse" question: one object, several doors.
- **Stats are already computed.** TV's trendline "Stats" (price range, percent, bars, angle) are
  the numbers `drawings/reads.ts` derives for the model: `perBar`, `atLast`, `vsClosePct`, bars.
  A "Show stats" toggle paints those same values beside the line. One calculation feeds the
  canvas, the popup and the model.
- **Cancel / Ok means a draft.** Today every control applies instantly, and for drawings each
  click is its own revision and its own undo batch. The popup edits a local draft with live
  preview (the preview path the drag gesture already uses), and **Ok sends one `update` patch**:
  one revision, one undo step. Cancel discards. Indicators snapshot their instance on open and
  restore it on Cancel. The top bar stays instant, because it is the quick path.
- **Defaults / Template.** First version: `Reset to defaults` and `Save as default` per kind,
  stored in `mm-chart-style`. A new trendline is born with your saved trendline style; a new
  SMA with your SMA style. Named templates are a later addition to the same store.
- **AVWAP is an indicator wearing a drawing's anchor.** TV gives it Inputs (source, band mode,
  three multipliers) and Style, no Text or Coordinates. Ours has a fixed `hlc3` source and no
  bands. Its `own` tab: source, band mode (standard deviation | percent), up to three
  multipliers; each band becomes one more stroke in Style and one more column in the matrix.
- **Indicator Style rows are per output.** TV's SMA row is `[x] MA  color/line  plot type`, then
  precision, "labels on price scale", "values in status line". Ours maps directly: the checkbox
  is a per-output `visible` (we only have `hiddenByDefault`), plot type is `IndicatorPlot`,
  precision exists in the registry, the price-scale label is `lastValueVisible`, and the status
  line is our top-left legend.
- **Not adopting now:** line-end arrows, middle point, SMA smoothing/offset, and the indicator
  Timeframe input (multi-timeframe waits on `INTRADAY_BARS.md`).

## Build order

1. Extract `chartStyle/` from `DrawingToolbar`; add the tabbed popup with draft + Cancel/Ok;
   double-click a drawing opens it with Style (incl. opacity and extent), Text and Coordinates.
   Drawings only, no behavior lost.
1b. Visibility tab: drawings carry `timeframes` instead of one `timeframe` (a migration of saved
   documents, and the model's Drawings table filters on it).
2. Indicators: series-to-owner map, click to select, the same popup with one stroke compartment
   per output and the existing inputs form as `own`. Gives width and style their missing controls.
3. `mm-chart-style` + adapters for candles, volume, financial overlay, comparison lines; the
   same store holds per-kind defaults (`Save as default` / `Reset`).
3b. AVWAP `own` tab: source and bands. "Show stats" on segments, painted from `reads.ts`.
4. Remove the `ChartDrawingsPanel` editor form; the panel keeps the list, visibility and undo.
5. Model packet: color word per column, drop hex/width/style from indicator metadata.

## Circle back

- Financial series `own` compartment, the way TradingView would offer it: period (quarterly /
  annual / TTM), step vs line, show points, its own scale vs shared, growth-% mode.
- Fib ratio editing, position sizing fields, per-timeframe visibility for drawings.
- Trendline / ray / extended trendline as one segment with an extent, behind separate tools.
