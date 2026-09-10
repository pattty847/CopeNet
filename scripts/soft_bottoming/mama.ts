/** Reuse the exact chart calculation and defaults; do not port Ehlers to Python. */
import fs from 'node:fs';
import { mesaAdaptiveMovingAverage } from '../../src/copenet/host/frontend/src/sections/market/indicators/calc/ehlers';
import type { IndicatorBar } from '../../src/copenet/host/frontend/src/sections/market/indicators/types';
const input: Record<string, IndicatorBar[]> = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output: Record<string, unknown> = {};
for (const [key, bars] of Object.entries(input)) {
  if (!Array.isArray(bars) || bars.some(b => !['t','o','h','l','c','v'].every(k => Number.isFinite(b[k as keyof IndicatorBar])))) {
    throw new Error('Invalid indicator bars: ' + key);
  }
  output[key] = mesaAdaptiveMovingAverage(bars, 0.5, 0.05, 32, 'close');
}
fs.writeFileSync(process.argv[3], JSON.stringify(output));
