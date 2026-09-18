// The selection bar sits top-centre until the operator drags it somewhere better; after that
// it stays where they put it, on every chart. Stored as a FRACTION of the chart so a spot
// chosen on a monitor is still on screen on a phone.
import { useCallback, useLayoutEffect, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';

interface BarPosition { x: number; y: number }
const STORAGE_KEY = 'mm-drawbar-position';

export function clampBarPosition(position: BarPosition, bar: { width: number; height: number }, chart: { width: number; height: number }): BarPosition {
  const maxX = Math.max(0, chart.width - bar.width);
  const maxY = Math.max(0, chart.height - bar.height);
  return { x: Math.min(Math.max(position.x, 0), maxX), y: Math.min(Math.max(position.y, 0), maxY) };
}

function load(): BarPosition | null {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as BarPosition | null;
    return stored && Number.isFinite(stored.x) && Number.isFinite(stored.y) ? { x: Math.min(1, Math.max(0, stored.x)), y: Math.min(1, Math.max(0, stored.y)) } : null;
  } catch { return null; }
}
let saved: BarPosition | null | undefined;

export function useBarPosition(barRef: RefObject<HTMLElement | null>): { style: CSSProperties | undefined; lowerHalf: boolean; onGripPointerDown: (event: ReactPointerEvent<HTMLElement>) => void; reset: () => void } {
  const [fraction, setFraction] = useState<BarPosition | null>(() => saved === undefined ? (saved = load()) : saved);
  const [pixels, setPixels] = useState<BarPosition | null>(null);

  // Fractions become pixels against the chart the bar is actually in, clamped so a bar can
  // never be restored off the edge of a smaller screen.
  useLayoutEffect(() => {
    const bar = barRef.current;
    const chart = bar?.offsetParent as HTMLElement | null;
    if (!fraction || !bar || !chart) { setPixels(null); return; }
    setPixels(clampBarPosition({ x: fraction.x * chart.clientWidth, y: fraction.y * chart.clientHeight },
      { width: bar.offsetWidth, height: bar.offsetHeight }, { width: chart.clientWidth, height: chart.clientHeight }));
  }, [fraction, barRef]);

  const onGripPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const bar = barRef.current;
    const chart = bar?.offsetParent as HTMLElement | null;
    if (!bar || !chart || event.button !== 0) return;
    event.preventDefault();
    const grip = event.currentTarget;
    grip.setPointerCapture(event.pointerId);
    const barBounds = bar.getBoundingClientRect();
    const chartBounds = chart.getBoundingClientRect();
    const offset = { x: event.clientX - barBounds.left, y: event.clientY - barBounds.top };
    let latest: BarPosition | null = null;
    const move = (next: PointerEvent) => {
      latest = clampBarPosition({ x: next.clientX - chartBounds.left - offset.x, y: next.clientY - chartBounds.top - offset.y },
        { width: barBounds.width, height: barBounds.height }, { width: chartBounds.width, height: chartBounds.height });
      setPixels(latest);
    };
    const up = () => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', up);
      if (!latest) return;
      saved = { x: latest.x / chartBounds.width, y: latest.y / chartBounds.height };
      setFraction(saved);
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); } catch { /* the spot just does not persist */ }
    };
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', up);
  }, [barRef]);

  const reset = useCallback(() => {
    saved = null; setFraction(null); setPixels(null);
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* nothing stored */ }
  }, []);

  // In the lower half of the chart the bar's menus have to open upward to stay on it.
  const chartHeight = (barRef.current?.offsetParent as HTMLElement | null)?.clientHeight ?? 0;
  return { lowerHalf: pixels != null && chartHeight > 0 && pixels.y > chartHeight / 2, style: pixels ? { left: pixels.x, top: pixels.y, transform: 'none' } : undefined, onGripPointerDown, reset };
}
