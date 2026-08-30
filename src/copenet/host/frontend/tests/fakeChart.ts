// A stand-in for the Lightweight Charts API surface the indicator renderer actually touches.
//
// Enough to assert lifecycle — that panes and series are created, reused, reordered and
// destroyed correctly — without a DOM. The renderer never reads back from the chart except
// for `paneIndex()`, so this is a complete model of its dependencies rather than a partial
// mock that happens to pass.

export class FakePane {
  /** Lightweight Charts' default. The renderer overrides it so the price pane keeps its
   *  share; asserting the value here is what stops that override from being silently
   *  swallowed by the try/catch that guards a mid-layout chart. */
  stretchFactor = 1;

  constructor(private readonly chart: FakeChart) {}

  setStretchFactor(value: number): void {
    this.stretchFactor = value;
  }

  getStretchFactor(): number {
    return this.stretchFactor;
  }

  /** Stands in for the pane's DOM node. Null models the real API's documented behaviour
   *  before the pane has been laid out, which is why the renderer must tolerate it. */
  element: unknown = { pane: true };

  getHTMLElement(): unknown {
    return this.element;
  }

  /** Panes are created preserved, which is what keeps a captured pane index valid through
   *  teardown. The renderer depends on this staying true; the flag is modelled so a future
   *  change that clears it shows up here rather than as a wrongly-removed pane. */
  preserve = true;

  paneIndex(): number {
    const index = this.chart.paneList.indexOf(this);
    if (index < 0) throw new Error('pane has been removed');
    return index;
  }

  moveTo(target: number): void {
    const from = this.paneIndex();
    this.chart.paneList.splice(from, 1);
    this.chart.paneList.splice(target, 0, this);
  }
}

export interface FakePriceLine {
  price: number;
  color: string;
  title: string;
}

export class FakeSeries {
  data: { time: number; value: number; color?: string }[] = [];
  options: Record<string, unknown>;
  priceLines: FakePriceLine[] = [];

  constructor(
    public readonly definitionName: string,
    options: Record<string, unknown>,
    public readonly createdInPane: number,
    /** The pane this series lives in, by reference — indices move when a pane is removed. */
    public readonly pane: FakePane | null = null,
  ) {
    this.options = { ...options };
  }

  applyOptions(options: Record<string, unknown>): void {
    Object.assign(this.options, options);
  }

  setData(data: { time: number; value: number; color?: string }[]): void {
    this.data = data;
  }

  createPriceLine(options: FakePriceLine): FakePriceLine {
    const line = { ...options };
    this.priceLines.push(line);
    return line;
  }

  removePriceLine(line: FakePriceLine): void {
    const index = this.priceLines.indexOf(line);
    // Throwing on an unknown line is the point: it is how a double-remove or a leak shows up
    // as a failing test rather than as silently duplicated furniture on the chart.
    if (index < 0) throw new Error('price line is not attached to this series');
    this.priceLines.splice(index, 1);
  }
}

/** A price scale, modelled because `autoscaleInfoProvider` only applies while autoScale is
 *  on — so "did the renderer put it back after a drag turned it off" is a real assertion. */
export class FakePriceScale {
  autoScale = true;
  scaleMargins: { top: number; bottom: number } = { top: 0.2, bottom: 0.1 };
  applyCount = 0;

  applyOptions(options: { autoScale?: boolean; scaleMargins?: { top: number; bottom: number } }): void {
    this.applyCount += 1;
    if (options.autoScale != null) this.autoScale = options.autoScale;
    if (options.scaleMargins) this.scaleMargins = options.scaleMargins;
  }

  options(): { autoScale: boolean; scaleMargins: { top: number; bottom: number } } {
    return { autoScale: this.autoScale, scaleMargins: this.scaleMargins };
  }
}

export class FakeChart {
  /** The backing array. `panes()` is the method the real API exposes; the array is kept
   *  separately so assertions can read it without going through the accessor. */
  paneList: FakePane[] = [];
  series: FakeSeries[] = [];

  constructor() {
    this.paneList.push(new FakePane(this)); // pane 0 is the price pane and is never removed
  }

  panes(): FakePane[] {
    return this.paneList;
  }

  /** Price scales are per pane in v5, keyed by id within that pane. */
  private scales = new Map<string, FakePriceScale>();

  priceScale(id: string, paneIndex = 0): FakePriceScale {
    if (paneIndex >= this.paneList.length) throw new Error(`no pane ${paneIndex}`);
    const key = `${paneIndex}:${id}`;
    let scale = this.scales.get(key);
    if (!scale) {
      scale = new FakePriceScale();
      this.scales.set(key, scale);
    }
    return scale;
  }

  addPane(): FakePane {
    const pane = new FakePane(this);
    this.paneList.push(pane);
    return pane;
  }

  removePane(index: number): void {
    if (index <= 0 || index >= this.paneList.length) throw new Error(`cannot remove pane ${index}`);
    this.paneList.splice(index, 1);
  }

  addSeries(definition: { toString(): string }, options: Record<string, unknown>, paneIndex = 0): FakeSeries {
    const name = seriesName(definition);
    const series = new FakeSeries(name, options, paneIndex, this.paneList[paneIndex] ?? null);
    this.series.push(series);
    return series;
  }

  removeSeries(series: FakeSeries): void {
    const index = this.series.indexOf(series);
    if (index < 0) throw new Error('series is not on this chart');
    this.series.splice(index, 1);
  }
}

/** Lightweight Charts' series definitions carry a `type` field. */
function seriesName(definition: unknown): string {
  const typed = definition as { type?: string };
  return typed?.type ?? 'Unknown';
}
