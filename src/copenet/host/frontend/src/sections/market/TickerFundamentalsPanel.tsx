import { lazy, Suspense, useMemo, useState } from 'react';
import { FinancialHistoryTable } from './FinancialHistoryTable';
import {
  buildFinancialChartRows,
  FINANCIAL_STORIES,
  type FinancialStory,
} from './financialExplorer';
import type { FinancialFrequency } from './types';
import { useFinancialSeries } from './useFinancialSeries';

const FinancialExplorerChart = lazy(() => import('./FinancialExplorerChart').then((module) => ({ default: module.FinancialExplorerChart })));

export function TickerFundamentalsPanel({ symbol, active }: { symbol: string; active: boolean }) {
  const [storyId, setStoryId] = useState(FINANCIAL_STORIES[0].id);
  const [frequency, setFrequency] = useState<FinancialFrequency>(FINANCIAL_STORIES[0].defaultFrequency);
  const story = FINANCIAL_STORIES.find((candidate) => candidate.id === storyId) ?? FINANCIAL_STORIES[0];

  const selectStory = (next: FinancialStory) => {
    setStoryId(next.id);
    setFrequency((current) => next.frequencies.includes(current) ? current : next.defaultFrequency);
  };

  return (
    <section className="ticker-fundamentals-panel" aria-label="Point-in-time fundamentals">
      <header className="ticker-embedded-panel-header financial-explorer-header">
        <div><h3>Financial explorer</h3><p>Canonical SEC series, plotted by reporting period with source dates preserved below.</p></div>
        <div className="financial-frequency-control" role="group" aria-label="Financial reporting frequency">
          {(['annual', 'quarterly', 'ttm'] as const).map((option) => (
            <button key={option} type="button" aria-pressed={frequency === option} disabled={!story.frequencies.includes(option)} onClick={() => setFrequency(option)}>
              {option === 'annual' ? 'Annual' : option === 'quarterly' ? 'Quarterly' : 'TTM'}
            </button>
          ))}
        </div>
      </header>
      <div className="financial-story-nav" role="group" aria-label="Financial statement view">
        {FINANCIAL_STORIES.map((candidate) => (
          <button key={candidate.id} type="button" aria-pressed={story.id === candidate.id} onClick={() => selectStory(candidate)}>{candidate.label}</button>
        ))}
      </div>
      <FinancialStoryView key={`${symbol}:${story.id}`} symbol={symbol} story={story} frequency={frequency} active={active} />
    </section>
  );
}

function FinancialStoryView({
  symbol,
  story,
  frequency,
  active,
}: {
  symbol: string;
  story: FinancialStory;
  frequency: FinancialFrequency;
  active: boolean;
}) {
  const metric0 = story.metrics[0];
  const metric1 = story.metrics[1];
  const metric2 = story.metrics[2];
  const metric3 = story.metrics[3];
  const state0 = useFinancialSeries(symbol, metric0?.id ?? '', frequency, active && metric0 != null);
  const state1 = useFinancialSeries(symbol, metric1?.id ?? '', frequency, active && metric1 != null);
  const state2 = useFinancialSeries(symbol, metric2?.id ?? '', frequency, active && metric2 != null);
  const state3 = useFinancialSeries(symbol, metric3?.id ?? '', frequency, active && metric3 != null);
  const metricStates = useMemo(() => [state0, state1, state2, state3], [state0, state1, state2, state3]);
  const [visibleMetrics, setVisibleMetrics] = useState(() => new Set(story.metrics.map((metric) => metric.id)));
  const rows = useMemo(
    () => buildFinancialChartRows(story.metrics.map((metric, index) => ({ metric, payload: metricStates[index]?.data ?? null })), story.id === 'valuation' ? 20 : frequency === 'annual' ? 8 : 12),
    [frequency, metricStates, story],
  );
  const loading = metricStates.some((state, index) => story.metrics[index] && state.loading);
  const errors = metricStates.flatMap((state, index) => story.metrics[index] && state.error ? [`${story.metrics[index].shortLabel}: ${state.error}`] : []);
  const warnings = [...new Set(metricStates.flatMap((state) => state.data?.warnings ?? []))];
  const observations = metricStates.reduce((total, state) => total + (state.data?.observations.length ?? 0), 0);

  const toggleMetric = (metricId: string) => {
    setVisibleMetrics((current) => {
      const next = new Set(current);
      if (next.has(metricId)) {
        if (next.size === 1) return current;
        next.delete(metricId);
      } else {
        next.add(metricId);
      }
      return next;
    });
  };

  return (
    <div className="financial-story-view">
      <div className="financial-story-heading">
        <div><h3>{story.label}</h3><p>{story.description}</p></div>
        <span>{loading ? 'Loading filing history…' : `${rows.length} periods plotted`}</span>
      </div>
      <div className="financial-series-legend" role="group" aria-label={`${story.label} plotted series`}>
        {story.metrics.map((metric) => (
          <button key={metric.id} type="button" aria-pressed={visibleMetrics.has(metric.id)} onClick={() => toggleMetric(metric.id)}>
            <i style={{ background: metric.color }} /><span>{metric.shortLabel}</span>
          </button>
        ))}
      </div>
      {errors.length > 0 ? <div className="financial-explorer-errors" role="alert">{errors.map((error) => <span key={error}>{error}</span>)}</div> : null}
      {active && rows.length > 0 ? (
        <Suspense fallback={<FinancialChartSkeleton />}>
          <FinancialExplorerChart rows={rows} story={story} visibleMetrics={visibleMetrics} />
        </Suspense>
      ) : loading ? <FinancialChartSkeleton /> : <div className="financial-explorer-empty">No canonical {story.label.toLowerCase()} history is available for this issuer.</div>}
      {rows.length > 0 ? <FinancialHistoryTable rows={rows} story={story} visibleMetrics={visibleMetrics} frequency={frequency} onToggleMetric={toggleMetric} /> : null}
      <footer className="financial-explorer-provenance">
        <span>{observations.toLocaleString()} source observations · availability-aligned</span>
        {warnings.slice(0, 3).map((warning) => <span key={warning} data-warning="true">{warning.replaceAll('_', ' ')}</span>)}
      </footer>
    </div>
  );
}

function FinancialChartSkeleton() {
  return <div className="financial-chart-skeleton" aria-label="Loading financial chart"><span /><span /><span /><span /></div>;
}
