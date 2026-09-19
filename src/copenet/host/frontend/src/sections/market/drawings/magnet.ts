// Magnet: while placing or dragging an anchor, the price sticks to the open, high, low or
// close of the candle under the cursor. `weak` sticks only when the cursor is already near
// one; `strong` always takes the nearest. The snapped anchor records WHICH field it took
// (`evidenceField`), the same declaration an agent drawing makes, so a magnet-placed level
// is a checkable claim about a candle rather than a number that happens to match one.
import type { ChartAnchor } from '../chartAgent/types';
import type { Ohlcv } from '../types';

export type MagnetMode = 'off' | 'weak' | 'strong';
export const MAGNET_MODES: MagnetMode[] = ['off', 'weak', 'strong'];
export const MAGNET_LABELS: Record<MagnetMode, string> = { off: 'Magnet off', weak: 'Magnet: snaps when near a candle price', strong: 'Magnet: always snaps to the nearest candle price' };
export const MAGNET_REACH_PX = { mouse: 14, touch: 28 };
const STORAGE_KEY = 'mm-drawing-magnet';

const FIELDS = ['o', 'h', 'l', 'c'] as const;

export function magnetSnap(bar: Ohlcv, y: number, toY: (price: number) => number | null, mode: MagnetMode, reachPx: number): { value: number; y: number; field: NonNullable<ChartAnchor['evidenceField']> } | null {
  if (mode === 'off') return null;
  let best: { value: number; y: number; field: typeof FIELDS[number]; distance: number } | null = null;
  for (const field of FIELDS) {
    const candidateY = toY(bar[field]);
    if (candidateY == null || !Number.isFinite(candidateY)) continue;
    const distance = Math.abs(candidateY - y);
    if (!best || distance < best.distance) best = { value: bar[field], y: candidateY, field, distance };
  }
  if (!best || (mode === 'weak' && best.distance > reachPx)) return null;
  return { value: best.value, y: best.y, field: best.field };
}

export function loadMagnet(): MagnetMode {
  try { const stored = localStorage.getItem(STORAGE_KEY); return MAGNET_MODES.includes(stored as MagnetMode) ? stored as MagnetMode : 'off'; } catch { return 'off'; }
}
export function saveMagnet(mode: MagnetMode): void {
  try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* the preference just does not persist */ }
}
