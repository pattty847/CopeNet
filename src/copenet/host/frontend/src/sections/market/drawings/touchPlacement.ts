// Touch placement is relative. The first tap drops a cursor, a drag ANYWHERE on the chart
// moves that cursor by the finger's delta, and a plain tap commits it as the anchor. The
// finger therefore never has to cover the candle being aimed at.

export interface ChartPoint { x: number; y: number }
export interface TouchGesture { down: ChartPoint; origin: ChartPoint; fresh: boolean; moved: boolean }

export const TOUCH_SLOP_PX = 6;

export function beginTouch(cursor: ChartPoint | null, point: ChartPoint): TouchGesture {
  return { down: point, origin: cursor ?? point, fresh: !cursor, moved: false };
}

/** The cursor after this move, or null while the finger is still inside the tap slop. */
export function dragTouch(gesture: TouchGesture, point: ChartPoint, pane: { width: number; height: number }): ChartPoint | null {
  const dx = point.x - gesture.down.x;
  const dy = point.y - gesture.down.y;
  if (!gesture.moved && Math.hypot(dx, dy) < TOUCH_SLOP_PX) return null;
  gesture.moved = true;
  return {
    x: Math.min(Math.max(gesture.origin.x + dx, 0), pane.width),
    y: Math.min(Math.max(gesture.origin.y + dy, 0), pane.height),
  };
}

/** Only a plain tap on an existing cursor commits; the first tap and any drag position it. */
export function touchCommits(gesture: TouchGesture): boolean {
  return !gesture.fresh && !gesture.moved;
}
