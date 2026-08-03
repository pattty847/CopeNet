import { useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { FinancialMetricInfo } from './types';

// The metric registry only changes on deploy, so one fetch serves the page lifetime.
let cached: FinancialMetricInfo[] | null = null;

// Keeps the overlay controls usable before the RPC answers or if it fails.
const FALLBACK: FinancialMetricInfo[] = [
  { id: 'revenue', label: 'Revenue', factType: 'duration', validUnits: ['USD'], aggregation: 'sum' },
  { id: 'trailing_pe', label: 'Trailing P/E', factType: 'valuation', validUnits: ['ratio'], aggregation: 'composite', derived: true },
];

export function useFinancialMetrics(): FinancialMetricInfo[] {
  const [metrics, setMetrics] = useState<FinancialMetricInfo[]>(cached ?? FALLBACK);

  useEffect(() => {
    if (cached) return;
    let cancelled = false;
    wsClient
      .marketFinancialMetrics()
      .then((list) => {
        if (!list.length) return;
        cached = list;
        if (!cancelled) setMetrics(list);
      })
      .catch(() => {
        /* fallback list keeps the controls usable */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return metrics;
}

export function metricInfo(metrics: FinancialMetricInfo[], id: string | null): FinancialMetricInfo | null {
  if (!id) return null;
  return metrics.find((metric) => metric.id === id) ?? null;
}

export function isValuationMetric(metrics: FinancialMetricInfo[], id: string | null): boolean {
  return metricInfo(metrics, id)?.factType === 'valuation';
}
