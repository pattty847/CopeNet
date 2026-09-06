import type { ForecastSetup } from './types';

export function setupVisualModel(setup: ForecastSetup) {
  const entry = setup.entry.price;
  const risk = Math.abs(entry - setup.stop);
  const direction = setup.direction === 'long' ? 1 : -1;
  const levels = [
    { kind: 'entry', label: `${setup.entry.kind === 'limit' ? 'Limit' : 'Stop'} entry`, price: entry, fraction: null },
    { kind: 'stop', label: 'Stop loss', price: setup.stop, fraction: null },
    ...setup.targets.map((target, index) => ({ kind: 'target', label: `Target ${index + 1}`, ...target })),
  ].sort((a, b) => b.price - a.price);
  const maximum = levels[0].price;
  const minimum = levels[levels.length - 1].price;
  const height = levels.length * 56;
  const y = (price: number) => 28 + (maximum - price) / (maximum - minimum) * (height - 56);
  return { height, entryY: y(entry), stopY: y(setup.stop), targetY: y(setup.targets[setup.targets.length - 1].price),
    levels: levels.map((level, index) => ({ ...level, y: y(level.price), labelY: 28 + index * 56,
      percent: direction * (level.price - entry) / entry * 100,
      riskMultiple: direction * (level.price - entry) / risk })) };
}
