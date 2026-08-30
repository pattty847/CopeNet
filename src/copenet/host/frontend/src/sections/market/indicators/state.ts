// Indicator workspace state and its persisted contract.
//
// SCOPE: the layout is WORKSPACE-STICKY, not per symbol. An analyst configures "EMA 20, EMA
// 50, RSI 14" once and expects to keep looking through that same instrument at every asset
// they open; the values recompute per symbol, the layout does not move. This matches the
// split the workspace already draws — interval, range, log axis and the pane set are sticky,
// while comparisons and per-metric financial overlays are symbol-scoped and reset on switch.
//
// PERSISTENCE: one versioned blob under a single key. A stored layout whose version does not
// match exactly is discarded rather than guessed at, in either direction — a build that only
// understands v1 must not half-read a v2 layout written by a newer build the operator has
// since rolled back from. Bumping LAYOUT_VERSION therefore means writing a migration in the
// same commit, or accepting that every operator loses their layout once.

import { configKey, defaultConfig, normalizeConfig } from './config';
import { indicatorById } from './registry';
import type { IndicatorConfig } from './types';

export interface IndicatorStyle {
  color?: string;
  lineWidth?: number;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
}

export interface IndicatorInstance {
  /** Unique within a layout. Multiple instances of one indicator is the normal case. */
  instanceId: string;
  indicatorId: string;
  config: IndicatorConfig;
  visible: boolean;
  /** Per-output overrides. Absent means "whatever the registry declares". */
  styles?: Record<string, IndicatorStyle>;
  /** Pane height, stored as a STRETCH FACTOR rather than pixels.
   *
   *  Dragging a pane separator updates Lightweight Charts' stretch factors, which are
   *  relative — so a layout saved on a laptop restores proportionally on a monitor, where a
   *  pixel height would restore a pane that is right in absolute terms and wrong on screen.
   *  Absent means "use the default weighting". */
  paneStretch?: number;
}

/** A whole persisted layout: the indicators, plus how the panes are divided. */
export interface IndicatorLayout {
  instances: IndicatorInstance[];
  /** Stretch factor of the PRICE pane, which no instance owns. */
  priceStretch: number;
}

/** Price against each indicator pane, before the operator drags anything. Four is the point
 *  where one indicator reads as a strip under the chart rather than a second chart competing
 *  with it. */
export const DEFAULT_PRICE_STRETCH = 4;

/** Bounds for a stored stretch factor. Wide enough for any deliberate layout, narrow enough
 *  that a corrupt value cannot collapse a pane to nothing or push the others off-screen. */
const MIN_STRETCH = 0.05;
const MAX_STRETCH = 50;

function normalizeStretch(value: unknown, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback;
  return Math.min(MAX_STRETCH, Math.max(MIN_STRETCH, value));
}

export const LAYOUT_VERSION = 1;
const STORAGE_KEY = 'mm-tw-indicators';

/** Guard against a layout that would make the chart unusable — and against a corrupt blob
 *  claiming thousands of instances. */
export const MAX_INDICATORS = 12;

interface StoredLayout {
  version: number;
  instances: unknown[];
  priceStretch?: unknown;
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode — an indicator layout is a convenience, never a requirement */
  }
}

/** Turn an arbitrary stored blob into instances this build can actually run.
 *
 *  Total by construction: it never throws, and anything it cannot vouch for is dropped rather
 *  than repaired into something the operator did not ask for. An indicator id that no longer
 *  exists is dropped silently — the alternative is a layout that fails to load entirely
 *  because one entry was retired. */
export function parseIndicatorLayout(raw: string | null): IndicatorLayout {
  const empty: IndicatorLayout = { instances: [], priceStretch: DEFAULT_PRICE_STRETCH };
  if (!raw) return empty;
  let parsed: StoredLayout;
  try {
    parsed = JSON.parse(raw) as StoredLayout;
  } catch {
    return empty;
  }
  if (!parsed || parsed.version !== LAYOUT_VERSION || !Array.isArray(parsed.instances)) return empty;

  const instances: IndicatorInstance[] = [];
  const seen = new Set<string>();
  for (const entry of parsed.instances) {
    if (!entry || typeof entry !== 'object') continue;
    const candidate = entry as Partial<IndicatorInstance>;
    if (typeof candidate.indicatorId !== 'string' || typeof candidate.instanceId !== 'string') continue;
    const definition = indicatorById(candidate.indicatorId);
    if (!definition) continue; // retired indicator: drop the row, keep the layout
    if (seen.has(candidate.instanceId)) continue;
    seen.add(candidate.instanceId);
    const styles = normalizeStyles(candidate.styles);
    const stretch = typeof candidate.paneStretch === 'number' && Number.isFinite(candidate.paneStretch)
      ? normalizeStretch(candidate.paneStretch, 1)
      : undefined;
    instances.push({
      instanceId: candidate.instanceId,
      indicatorId: candidate.indicatorId,
      config: normalizeConfig(definition, candidate.config),
      visible: candidate.visible !== false,
      // Omitted rather than set to undefined: an own key holding undefined survives a
      // structural comparison but not JSON, so the two disagree about whether a saved
      // layout round-tripped.
      ...(styles ? { styles } : {}),
      ...(stretch != null ? { paneStretch: stretch } : {}),
    });
    if (instances.length >= MAX_INDICATORS) break;
  }
  return { instances, priceStretch: normalizeStretch(parsed.priceStretch, DEFAULT_PRICE_STRETCH) };
}

function normalizeStyles(raw: unknown): Record<string, IndicatorStyle> | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const styles: Record<string, IndicatorStyle> = {};
  for (const [key, entry] of Object.entries(raw as Record<string, unknown>)) {
    if (!entry || typeof entry !== 'object') continue;
    const style = entry as IndicatorStyle;
    const next: IndicatorStyle = {};
    if (typeof style.color === 'string' && /^#[0-9a-f]{3,8}$/i.test(style.color)) next.color = style.color;
    if (typeof style.lineWidth === 'number' && style.lineWidth >= 1 && style.lineWidth <= 4) {
      next.lineWidth = Math.round(style.lineWidth);
    }
    if (style.lineStyle === 'solid' || style.lineStyle === 'dashed' || style.lineStyle === 'dotted') {
      next.lineStyle = style.lineStyle;
    }
    if (Object.keys(next).length) styles[key] = next;
  }
  return Object.keys(styles).length ? styles : undefined;
}

export function loadIndicatorLayout(): IndicatorLayout {
  return parseIndicatorLayout(read(STORAGE_KEY));
}

export function saveIndicatorLayout(layout: IndicatorLayout): void {
  write(STORAGE_KEY, JSON.stringify({
    version: LAYOUT_VERSION,
    instances: layout.instances,
    priceStretch: layout.priceStretch,
  }));
}

/** Record a pane division the operator produced by dragging a separator. Returns the same
 *  array when nothing moved, so persisting this is a no-op on an ordinary render. */
export function applyPaneStretch(
  instances: IndicatorInstance[],
  byInstance: Record<string, number>,
): IndicatorInstance[] {
  let changed = false;
  const next = instances.map((instance) => {
    const stretch = byInstance[instance.instanceId];
    if (stretch == null || !Number.isFinite(stretch)) return instance;
    const normalized = normalizeStretch(stretch, instance.paneStretch ?? 1);
    // Compared against the EFFECTIVE stretch, not the stored one, so a layout nobody has
    // dragged does not acquire a paneStretch equal to its own default and rewrite storage on
    // the first pointer-up.
    if (Math.abs((instance.paneStretch ?? 1) - normalized) < 0.01) return instance;
    changed = true;
    return { ...instance, paneStretch: normalized };
  });
  return changed ? next : instances;
}

/** Smallest unused ordinal for this indicator, so ids stay readable ("ema#2") and
 *  reproducible in tests — no clock and no randomness. */
export function nextInstanceId(indicatorId: string, instances: IndicatorInstance[]): string {
  const taken = new Set(instances.map((instance) => instance.instanceId));
  for (let ordinal = 1; ordinal <= MAX_INDICATORS + instances.length + 1; ordinal += 1) {
    const candidate = `${indicatorId}#${ordinal}`;
    if (!taken.has(candidate)) return candidate;
  }
  return `${indicatorId}#${instances.length + 1}`;
}

// --------------------------------------------------------------- transitions
// Every mutation is a pure function over the instance list. The component holds the array in
// state and persists it; nothing here reaches for storage or for the chart.

export function addIndicator(instances: IndicatorInstance[], indicatorId: string): IndicatorInstance[] {
  const definition = indicatorById(indicatorId);
  if (!definition || instances.length >= MAX_INDICATORS) return instances;
  return [
    ...instances,
    {
      instanceId: nextInstanceId(indicatorId, instances),
      indicatorId,
      config: defaultConfig(definition),
      visible: true,
    },
  ];
}

export function removeIndicator(instances: IndicatorInstance[], instanceId: string): IndicatorInstance[] {
  return instances.filter((instance) => instance.instanceId !== instanceId);
}

/** A duplicate lands directly after its source and carries its configuration. The common use
 *  is a second length of the same average, so starting from the original's settings rather
 *  than from the registry defaults is the shorter path. */
export function duplicateIndicator(instances: IndicatorInstance[], instanceId: string): IndicatorInstance[] {
  const index = instances.findIndex((instance) => instance.instanceId === instanceId);
  if (index < 0 || instances.length >= MAX_INDICATORS) return instances;
  const source = instances[index];
  const copy: IndicatorInstance = {
    ...source,
    instanceId: nextInstanceId(source.indicatorId, instances),
    config: { ...source.config },
    styles: source.styles ? { ...source.styles } : undefined,
  };
  return [...instances.slice(0, index + 1), copy, ...instances.slice(index + 1)];
}

export function configureIndicator(
  instances: IndicatorInstance[],
  instanceId: string,
  patch: IndicatorConfig,
): IndicatorInstance[] {
  return instances.map((instance) => {
    if (instance.instanceId !== instanceId) return instance;
    const definition = indicatorById(instance.indicatorId);
    if (!definition) return instance;
    // Normalised on the way in, so an out-of-range value can never reach a compute loop.
    return { ...instance, config: normalizeConfig(definition, { ...instance.config, ...patch }) };
  });
}

export function setIndicatorVisibility(
  instances: IndicatorInstance[],
  instanceId: string,
  visible: boolean,
): IndicatorInstance[] {
  return instances.map((instance) => (instance.instanceId === instanceId ? { ...instance, visible } : instance));
}

export function styleIndicator(
  instances: IndicatorInstance[],
  instanceId: string,
  outputKey: string,
  style: IndicatorStyle,
): IndicatorInstance[] {
  return instances.map((instance) => {
    if (instance.instanceId !== instanceId) return instance;
    const styles = { ...(instance.styles ?? {}) };
    styles[outputKey] = { ...(styles[outputKey] ?? {}), ...style };
    return { ...instance, styles };
  });
}

/** Back to the registry's defaults, keeping the instance and its position. */
export function resetIndicator(instances: IndicatorInstance[], instanceId: string): IndicatorInstance[] {
  return instances.map((instance) => {
    if (instance.instanceId !== instanceId) return instance;
    const definition = indicatorById(instance.indicatorId);
    if (!definition) return instance;
    return { ...instance, config: defaultConfig(definition), styles: undefined, visible: true };
  });
}

/** Order decides pane order below the chart, so it is worth being able to change. */
export function moveIndicator(instances: IndicatorInstance[], instanceId: string, delta: number): IndicatorInstance[] {
  const index = instances.findIndex((instance) => instance.instanceId === instanceId);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= instances.length) return instances;
  const next = [...instances];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved);
  return next;
}

export function clearIndicators(): IndicatorInstance[] {
  return [];
}

/** Stable identity for one configured instance. Two instances that would compute the exact
 *  same numbers share a memo entry rather than each running the loop. */
export function instanceComputeKey(instance: IndicatorInstance): string {
  return `${instance.indicatorId}|${configKey(instance.config)}`;
}
