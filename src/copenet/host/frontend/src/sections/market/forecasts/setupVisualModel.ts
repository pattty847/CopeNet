import type { ForecastChart, ForecastSetup } from './types';

export function setupVisualModel(setup: ForecastSetup, chart: ForecastChart, width = 600) {
  const entry = setup.entry.price;
  const risk = Math.abs(entry - setup.stop);
  const direction = setup.direction === 'long' ? 1 : -1;
  const levels = [
    { kind: 'entry', label: 'Entry', price: entry, fraction: null },
    { kind: 'stop', label: 'Stop', price: setup.stop, fraction: null },
    ...setup.targets.map((target, index) => ({ kind: 'target', label: `T${index + 1}`, ...target })),
  ].sort((a, b) => b.price - a.price);
  const points = [...chart.history, ...chart.outcome];
  const maximum = Math.max(...levels.map((level) => level.price), ...points.map((point) => point.close));
  const minimum = Math.min(...levels.map((level) => level.price), ...points.map((point) => point.close));
  const start = chart.history[0]?.t ?? chart.publishedAt - 30 * 86400;
  const right = width - 80;
  const x = (time: number) => 8 + (time - start) / (chart.deadlineAt - start) * (right - 8);
  const y = (price: number) => 22 + (maximum - price) / (maximum - minimum) * 188;
  const path = (rows: typeof points) => rows.map((point, index) => `${index ? 'L' : 'M'}${x(point.t)},${y(point.close)}`).join(' ');
  let previousLabel = 6;
  return { width, right, start, x, y, entryY: y(entry), stopY: y(setup.stop), targetY: y(setup.targets[setup.targets.length - 1].price),
    publicationX: x(chart.publishedAt), historyPath: path(chart.history),
    outcomePath: chart.outcome.length ? path([...chart.history.slice(-1), ...chart.outcome]) : '', points,
    levels: levels.map((level) => {
      const labelY = Math.max(y(level.price), previousLabel + 14); previousLabel = labelY;
      return { ...level, y: y(level.price), labelY, percent: direction * (level.price - entry) / entry * 100,
        riskMultiple: direction * (level.price - entry) / risk };
    }) };
}
