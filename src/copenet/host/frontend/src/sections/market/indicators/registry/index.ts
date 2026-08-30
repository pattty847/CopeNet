// The indicator catalogue.
//
// This module is the single source of truth. The picker, the settings form, the legend, the
// persisted layout and the chart renderer all read from here and from nowhere else — adding
// an indicator means adding one entry to one family file, and nothing in a component changes.

import { EHLERS_INDICATORS } from './ehlers';
import { MEASURE_INDICATORS } from './measures';
import { MOMENTUM_INDICATORS } from './momentum';
import { TREND_INDICATORS } from './trend';
import type { IndicatorCategory, IndicatorDefinition } from '../types';

export const INDICATORS: IndicatorDefinition[] = [
  ...TREND_INDICATORS,
  ...MOMENTUM_INDICATORS,
  ...MEASURE_INDICATORS,
  ...EHLERS_INDICATORS,
];

const BY_ID = new Map(INDICATORS.map((definition) => [definition.id, definition]));

export function indicatorById(id: string): IndicatorDefinition | null {
  return BY_ID.get(id) ?? null;
}

export function indicatorsByCategory(category: IndicatorCategory): IndicatorDefinition[] {
  return INDICATORS.filter((definition) => definition.category === category);
}

/** Substring match over name, id and description. Deliberately not fuzzy: an analyst types
 *  "rsi" or "bol", and a fuzzy matcher that also returns Donchian for "dc" costs more trust
 *  than it saves keystrokes. */
export function searchIndicators(query: string): IndicatorDefinition[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return INDICATORS;
  return INDICATORS.filter((definition) =>
    `${definition.name} ${definition.id} ${definition.description ?? ''}`.toLowerCase().includes(needle));
}
