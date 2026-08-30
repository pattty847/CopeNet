// The Lightweight Charts adapter.
//
// This is the ONLY module that knows both what an indicator is and what a chart series is.
// `CandleChart` calls one hook; the hook calls `sync` with computed indicators and this layer
// decides what to create, update and tear down. Nothing about the 27 definitions leaks into
// the chart component.
//
// PANE MODEL. Price overlays go on pane 0 with the candles and share the right price scale,
// so an EMA is measured in the same units as the bars it sits on. Every pane indicator gets
// its own pane below, in layout order. Panes are addressed by the live `IPaneApi` rather than
// by a stored index, because `removePane` renumbers everything after it — caching an index is
// how you end up writing RSI data into the MACD pane.
//
// HIDDEN MEANS GONE. Hiding a pane indicator destroys its pane rather than emptying it. An
// empty pane holding vertical space is the worse of the two behaviours: hiding is what an
// operator reaches for when they want the price back.

import {
  AreaSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  LineType,
  type IChartApi,
  type IPaneApi,
  type IPriceLine,
  type ISeriesApi,
  type SeriesType,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { ComputedIndicator, ComputedOutput } from './compute';
import { DEFAULT_PRICE_STRETCH } from './state';

type AnySeries = ISeriesApi<SeriesType, Time>;

interface RenderedEntry {
  /** null for price overlays, which live on pane 0 alongside the candles. */
  pane: IPaneApi<Time> | null;
  /** Set when the indicator declares a fixed range, e.g. RSI's 0-100. */
  bounded: boolean;
  /** Output keys and plot kinds. A change here means the series have to be rebuilt. */
  signature: string;
  series: Map<string, AnySeries>;
  priceLines: IPriceLine[];
  /** The series carrying this pane's reference lines and fixed scale, if any. */
  anchor: AnySeries | null;
}

const LINE_STYLES: Record<ComputedOutput['lineStyle'], LineStyle> = {
  solid: LineStyle.Solid,
  dashed: LineStyle.Dashed,
  dotted: LineStyle.Dotted,
};

function signatureOf(indicator: ComputedIndicator): string {
  return `${indicator.placement}:${indicator.outputs.map((output) => `${output.key}/${output.plot}`).join(',')}`;
}

export class IndicatorChartLayer {
  private entries = new Map<string, RenderedEntry>();

  constructor(private readonly chart: IChartApi) {}

  /** Bring the chart in line with `indicators`. Safe to call on every render: unchanged
   *  entries are updated in place rather than rebuilt, so zoom, pan and scale all survive. */
  sync(indicators: ComputedIndicator[], priceStretch = DEFAULT_PRICE_STRETCH): void {
    const active = indicators.filter((indicator) => indicator.visible);
    const wanted = new Map(active.map((indicator) => [indicator.instanceId, indicator]));

    for (const [instanceId, entry] of [...this.entries]) {
      const indicator = wanted.get(instanceId);
      if (!indicator || signatureOf(indicator) !== entry.signature) this.teardown(instanceId, entry);
    }

    for (const indicator of active) {
      const existing = this.entries.get(indicator.instanceId);
      if (existing) this.update(existing, indicator);
      else this.create(indicator);
    }

    this.reorderPanes(active);
    this.applyPaneSizing(active, priceStretch);
    this.enforceBoundedScales();
  }

  /** Remove every series and pane this layer owns. The caller still owns the chart. */
  destroy(): void {
    for (const [instanceId, entry] of [...this.entries]) this.teardown(instanceId, entry);
  }

  /** Keep a declared pane range actually in force.
   *
   *  `autoscaleInfoProvider` only applies while the scale is on AUTO, and dragging a price
   *  axis silently turns auto off — after which RSI's declared 0-100 stops applying and the
   *  scale drifts to whatever the drag left behind, flattening the series into a line. The
   *  axis and the pane separator are a few pixels apart, so this is easy to trigger by
   *  accident while resizing and gives no clue what happened.
   *
   *  A range the definition declares is not a preference, so it is re-asserted rather than
   *  restored on request: for a bounded oscillator the scale IS the indicator. Unbounded
   *  panes are left completely alone and still drag, zoom and double-click-reset normally. */
  enforceBoundedScales(): void {
    for (const entry of this.entries.values()) {
      if (!entry.pane || !entry.bounded) continue;
      try {
        const scale = this.chart.priceScale('right', entry.pane.paneIndex());
        if (!scale.options().autoScale) scale.applyOptions({ autoScale: true });
      } catch {
        /* pane removed or mid-layout */
      }
    }
  }

  /** How the operator has divided the panes, as stretch factors. Relative by nature, so it
   *  restores proportionally on a different screen where pixel heights would not. */
  readPaneStretch(): { priceStretch: number; byInstance: Record<string, number> } {
    const byInstance: Record<string, number> = {};
    let priceStretch = DEFAULT_PRICE_STRETCH;
    try {
      priceStretch = this.chart.panes()[0]?.getStretchFactor() ?? DEFAULT_PRICE_STRETCH;
    } catch {
      /* mid-layout */
    }
    for (const [instanceId, entry] of this.entries) {
      if (!entry.pane) continue;
      try {
        byInstance[instanceId] = entry.pane.getStretchFactor();
      } catch {
        /* pane removed this frame */
      }
    }
    return { priceStretch, byInstance };
  }

  /** Pane indices currently in use, price pane excluded. Exposed so the chart can clamp
   *  pane-0-relative decorations against the space it actually has left. */
  paneCount(): number {
    return [...this.entries.values()].filter((entry) => entry.pane != null).length;
  }

  /** The live DOM element behind each indicator pane.
   *
   *  `IPaneApi.getHTMLElement()` is a first-class accessor, so anchoring controls to a pane
   *  needs no knowledge of Lightweight Charts' internal markup and no arithmetic over summed
   *  pane heights. It returns null before the pane has been laid out, which is why callers
   *  measure on a ResizeObserver rather than once. */
  paneElements(): { instanceId: string; element: HTMLElement }[] {
    const found: { instanceId: string; element: HTMLElement }[] = [];
    for (const [instanceId, entry] of this.entries) {
      if (!entry.pane) continue;
      let element: HTMLElement | null = null;
      try {
        element = entry.pane.getHTMLElement();
      } catch {
        element = null; // pane removed underneath us this frame
      }
      if (element) found.push({ instanceId, element });
    }
    return found;
  }

  private create(indicator: ComputedIndicator): void {
    const pane = indicator.placement === 'pane' ? this.chart.addPane(true) : null;
    const entry: RenderedEntry = {
      pane,
      bounded: indicator.paneRange != null,
      signature: signatureOf(indicator),
      series: new Map(),
      priceLines: [],
      anchor: null,
    };
    const paneIndex = pane ? pane.paneIndex() : 0;

    // A bounded oscillator uses nearly its whole pane. Lightweight Charts' default margins
    // reserve 30% of the height, which turns RSI's 0-100 into roughly -16..129 of usable
    // scale and squashes the line into the middle.
    if (pane && indicator.paneRange) {
      try {
        this.chart.priceScale('right', paneIndex).applyOptions({
          autoScale: true,
          scaleMargins: { top: 0.08, bottom: 0.08 },
        });
      } catch {
        /* the pane is mid-layout; enforceBoundedScales settles it */
      }
    }

    for (const output of indicator.outputs) {
      const series = this.chart.addSeries(
        output.plot === 'histogram' ? HistogramSeries : output.plot === 'area' ? AreaSeries : LineSeries,
        this.optionsFor(output, indicator, entry.anchor == null),
        paneIndex,
      );
      entry.series.set(output.key, series);
      if (!entry.anchor) entry.anchor = series;
    }

    this.entries.set(indicator.instanceId, entry);
    this.update(entry, indicator);
  }

  private update(entry: RenderedEntry, indicator: ComputedIndicator): void {
    let isAnchor = true;
    for (const output of indicator.outputs) {
      const series = entry.series.get(output.key);
      if (!series) continue;
      series.applyOptions(this.optionsFor(output, indicator, isAnchor));
      series.setData(
        output.points.map((point) => ({
          time: point.t as UTCTimestamp,
          value: point.value,
          ...(point.color ? { color: point.color } : {}),
        })),
      );
      isAnchor = false;
    }
    this.applyReferences(entry, indicator);
  }

  /** Reference lines are recreated rather than diffed. There are at most three of them, they
   *  carry no state, and a diff would have to key them by a value that is itself the thing
   *  being changed. */
  private applyReferences(entry: RenderedEntry, indicator: ComputedIndicator): void {
    const anchor = entry.anchor;
    if (!anchor) return;
    for (const line of entry.priceLines) {
      try {
        anchor.removePriceLine(line);
      } catch {
        /* the series is already gone; nothing to detach from */
      }
    }
    entry.priceLines = [];
    for (const reference of indicator.references ?? []) {
      entry.priceLines.push(
        anchor.createPriceLine({
          price: reference.value,
          color: reference.color ?? 'rgba(254,252,244,.2)',
          lineWidth: 1,
          lineStyle: LINE_STYLES[reference.lineStyle ?? 'dashed'],
          axisLabelVisible: false,
          title: reference.label ?? '',
        }),
      );
    }
  }

  private optionsFor(output: ComputedOutput, indicator: ComputedIndicator, isAnchor: boolean) {
    const range = indicator.paneRange;
    return {
      color: output.color,
      lineWidth: output.lineWidth as 1 | 2 | 3 | 4,
      lineStyle: LINE_STYLES[output.lineStyle],
      lineType: output.plot === 'stepline' ? LineType.WithSteps : LineType.Simple,
      priceScaleId: 'right',
      priceLineVisible: false,
      // The last-value badge is useful on exactly one series per pane; on all of them it
      // becomes a stack of overlapping labels on the axis.
      lastValueVisible: isAnchor && indicator.placement === 'pane',
      crosshairMarkerVisible: true,
      // A bounded oscillator keeps the scale it declares. Without this RSI autoscales to
      // whatever range it happened to visit, so 45-55 fills the pane and reads as violent.
      ...(isAnchor && range
        ? {
            autoscaleInfoProvider: () => ({
              priceRange: { minValue: range.min ?? 0, maxValue: range.max ?? 100 },
            }),
          }
        : {}),
    };
  }

  /** Keep pane order matching layout order. `moveTo` is index-based and pane 0 is always the
   *  price pane, so a pane indicator's target is its ordinal among pane indicators, plus one. */
  private reorderPanes(active: ComputedIndicator[]): void {
    let target = 1;
    for (const indicator of active) {
      const entry = this.entries.get(indicator.instanceId);
      if (!entry?.pane) continue;
      try {
        if (entry.pane.paneIndex() !== target) entry.pane.moveTo(target);
      } catch {
        /* a pane removed underneath us this frame — the next sync settles it */
      }
      target += 1;
    }
  }

  /** Give the price pane the space it deserves.
   *
   *  Lightweight Charts hands every new pane the same stretch factor, which splits the chart
   *  2:1 with one indicator and would leave price on 40% of the canvas with three. Price is
   *  what the other panes are read AGAINST, so it keeps a fixed larger share: one indicator
   *  takes 20%, four take 12.5% each and price still holds half. */
  private applyPaneSizing(active: ComputedIndicator[], priceStretch: number): void {
    const panes = active.filter((indicator) => this.entries.get(indicator.instanceId)?.pane).length;
    if (!panes) return;
    try {
      this.chart.panes()[0]?.setStretchFactor(priceStretch);
    } catch {
      /* the chart is mid-layout; the next sync settles it */
    }
    for (const indicator of active) {
      const entry = this.entries.get(indicator.instanceId);
      if (!entry?.pane) continue;
      try {
        // A height the operator dragged, when there is one; otherwise the default weighting.
        entry.pane.setStretchFactor(indicator.instance.paneStretch ?? 1);
      } catch {
        /* same */
      }
    }
  }

  /** Remove an indicator and everything it owns.
   *
   *  The explicit `removePane(paneIndex())` is safe precisely BECAUSE panes are created with
   *  `preserveEmptyPane`: Lightweight Charts will not collect the pane as its last series is
   *  removed, so the index is still valid when we get there. Were that flag ever dropped, the
   *  pane could self-collect first and the captured index would then address the NEXT pane —
   *  removing a different indicator's. Verified in a real browser: removing the first of
   *  three pane indicators leaves the other two intact and reclaims the space. */
  private teardown(instanceId: string, entry: RenderedEntry): void {
    for (const line of entry.priceLines) {
      try {
        entry.anchor?.removePriceLine(line);
      } catch {
        /* already detached */
      }
    }

    for (const series of entry.series.values()) {
      try {
        this.chart.removeSeries(series);
      } catch { /* already removed */ }
    }
    if (entry.pane) {
      try {
        this.chart.removePane(entry.pane.paneIndex());
      } catch { /* pane already gone */ }
    }
    this.entries.delete(instanceId);
  }
}
