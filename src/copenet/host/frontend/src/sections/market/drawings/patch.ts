import type { ChartObject, DrawingPatch } from '../chartAgent/types';

const PATCH_KEYS = ['kind', 'anchors', 'label', 'color', 'lineWidth', 'lineStyle', 'fillOpacity', 'locked', 'timeframes', 'showStats', 'params'] as const;

/** Only what actually changed is sent, so an untouched field can never be overwritten. */
export function drawingPatch(original: ChartObject, draft: ChartObject): DrawingPatch {
  const patch: Record<string, unknown> = {};
  for (const key of PATCH_KEYS) if (JSON.stringify(original[key]) !== JSON.stringify(draft[key]) && draft[key] !== undefined) patch[key] = draft[key];
  return patch as DrawingPatch;
}
