import type { Message } from '../types/backend';

/** Validate the optional immutable reference at the transcript transport boundary. */
export function normalizeMarketContext(raw: unknown): Message['marketContext'] {
  if (!raw || typeof raw !== 'object') return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.observationId !== 'string' || typeof item.documentId !== 'string' || typeof item.viewId !== 'string') return null;
  if (item.detail !== 'quick' && item.detail !== 'balanced' && item.detail !== 'deep') return null;
  if (item.access !== 'read' && item.access !== 'annotate') return null;
  return {
    observationId: item.observationId, documentId: item.documentId, viewId: item.viewId,
    detail: item.detail, access: item.access, hasExternalProse: item.hasExternalProse === true,
    ...(typeof item.symbol === 'string' ? { symbol: item.symbol } : {}),
    ...(item.timeframe === 'D' || item.timeframe === 'W' || item.timeframe === 'M' ? { timeframe: item.timeframe } : {}),
  };
}
