// A stand-in for the Lightweight Charts API surface the indicator renderer actually touches.
//
// Enough to assert lifecycle — that panes and series are created, reused, reordered and
// destroyed correctly — without a DOM. The renderer never reads back from the chart except
// for `paneIndex()`, so this is a complete model of its dependencies rather than a partial
// mock that happens to pass.

export class FakePane {
  constructor(private readonly chart: FakeChart) {}

  paneIndex(): number {
    const index = this.chart.panes.indexOf(this);
    if (index < 0) throw new Error('pane has been removed');
    return index;
  }

  moveTo(target: number): void {
    const from = this.paneIndex();
    this.chart.panes.splice(from, 1);
    this.chart.panes.splice(target, 0, this);
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

export class FakeChart {
  panes: FakePane[] = [];
  series: FakeSeries[] = [];

  constructor() {
    this.panes.push(new FakePane(this)); // pane 0 is the price pane and is never removed
  }

  addPane(): FakePane {
    const pane = new FakePane(this);
    this.panes.push(pane);
    return pane;
  }

  removePane(index: number): void {
    if (index <= 0 || index >= this.panes.length) throw new Error(`cannot remove pane ${index}`);
    this.panes.splice(index, 1);
  }

  addSeries(definition: { toString(): string }, options: Record<string, unknown>, paneIndex = 0): FakeSeries {
    const name = seriesName(definition);
    const series = new FakeSeries(name, options, paneIndex);
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
