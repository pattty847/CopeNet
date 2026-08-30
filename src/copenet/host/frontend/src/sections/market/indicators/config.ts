// Reading, defaulting and repairing indicator configs.
//
// A config arrives from three places — the registry's declared defaults, the settings form,
// and a localStorage blob written by an older build. Only the first is trustworthy, so every
// path funnels through `normalizeConfig`, which clamps numbers to their declared bounds,
// rejects enum values that are no longer offered, and fills anything missing. The calculation
// families can then read a config without a single defensive check of their own.

import type {
  IndicatorConfig,
  IndicatorConfigValue,
  IndicatorDefinition,
  IndicatorSource,
} from './types';
import { INDICATOR_SOURCES } from './types';

export function readNumber(config: IndicatorConfig, key: string, fallback: number): number {
  const value = config[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

/** Periods are integers. A fractional period silently produces a different indicator than
 *  the one named in the legend, so it is rounded here rather than deep in a loop. */
export function readPeriod(config: IndicatorConfig, key: string, fallback: number): number {
  return Math.max(1, Math.round(readNumber(config, key, fallback)));
}

export function readString(config: IndicatorConfig, key: string, fallback: string): string {
  const value = config[key];
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

export function readBoolean(config: IndicatorConfig, key: string, fallback: boolean): boolean {
  const value = config[key];
  return typeof value === 'boolean' ? value : fallback;
}

export function readSource(config: IndicatorConfig, key = 'source', fallback: IndicatorSource = 'close'): IndicatorSource {
  const value = config[key];
  return INDICATOR_SOURCES.some((entry) => entry.value === value) ? (value as IndicatorSource) : fallback;
}

export function defaultConfig(definition: IndicatorDefinition): IndicatorConfig {
  const config: IndicatorConfig = {};
  for (const input of definition.inputs) config[input.key] = input.default;
  return config;
}

/** Repair an arbitrary blob into a config this definition can actually run.
 *
 *  Deliberately total: it never throws and never returns a partial config. A saved layout
 *  from a build where "period" allowed 500 must not be able to run a 500-bar loop the current
 *  build declares a maximum of 200 for. */
export function normalizeConfig(definition: IndicatorDefinition, raw: unknown): IndicatorConfig {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const config: IndicatorConfig = {};
  for (const input of definition.inputs) {
    const value = source[input.key];
    switch (input.kind) {
      case 'number': {
        const numeric = typeof value === 'number' && Number.isFinite(value) ? value : input.default;
        const clamped = Math.min(input.max, Math.max(input.min, numeric));
        // Snap to the declared step so a hand-edited 14.37 does not become a period nobody
        // can reproduce through the UI.
        const stepped = input.step >= 1 ? Math.round(clamped) : clamped;
        config[input.key] = stepped;
        break;
      }
      case 'enum':
        config[input.key] = input.choices.some((choice) => choice.value === value)
          ? (value as string)
          : input.default;
        break;
      case 'source':
        config[input.key] = INDICATOR_SOURCES.some((entry) => entry.value === value)
          ? (value as string)
          : input.default;
        break;
      case 'boolean':
        config[input.key] = typeof value === 'boolean' ? value : input.default;
        break;
    }
  }
  return config;
}

/** Stable identity for a config, used as the memo key. Keys are sorted so two configs that
 *  differ only in property order share one cache entry instead of computing twice. */
export function configKey(config: IndicatorConfig): string {
  return Object.keys(config)
    .sort()
    .map((key) => `${key}=${String(config[key] as IndicatorConfigValue)}`)
    .join(',');
}
