import { ArrowLeft, FunctionSquare } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { ChartStage } from './ChartStage';
import type { ChartComparisonLine } from './chartComparison';
import { CHART_RANGES, CHART_TIMEFRAMES, visibleBars, type ChartRange, type ChartTimeframe } from './chartRanges';
import type { IndicatorRowActions } from './indicators/IndicatorRows';
import { MM } from './marketUi';
import { SymbolJump } from './SymbolJump';
import { useChartComparisons } from './useChartComparisons';
import type { Ohlcv } from './types';
import './tickerWorkspace.css';

const NO_INDICATOR_ACTIONS: IndicatorRowActions = {
  onConfigure: () => undefined,
  onStyle: () => undefined,
  onVisibility: () => undefined,
  onDuplicate: () => undefined,
  onReset: () => undefined,
  onRemove: () => undefined,
  onMove: () => undefined,
};

function indexedPoints(points: { t: number; value: number }[]): { t: number; value: number }[] {
  const originIndex = points.findIndex((point) => point.value !== 0);
  const indexed = originIndex >= 0 ? points.slice(originIndex) : [];
  const origin = indexed[0]?.value;
  if (!origin) return [];
  return indexed.map((point) => ({ t: point.t, value: ((point.value / origin) - 1) * 100 }));
}

function carrierBars(points: { t: number; value: number }[]): Ohlcv[] {
  return points.map((point) => ({ t: point.t, o: point.value, h: point.value, l: point.value, c: point.value, v: 0 }));
}

export function FormulaWorkspace({
  expression,
  onClose,
  onNavigate,
}: {
  expression: string;
  onClose: () => void;
  onNavigate: (value: string, type?: 'symbol' | 'formula') => void;
}) {
  const [timeframe, setTimeframe] = useState<ChartTimeframe>('W');
  const [range, setRange] = useState<ChartRange>('5Y');
  const [display, setDisplay] = useState<'value' | 'indexed'>('value');
  const [logScale, setLogScale] = useState(false);
  const [jumpOpen, setJumpOpen] = useState(false);
  const formulaData = useChartComparisons([expression], timeframe);
  const formula = formulaData.payload?.formulas[0] ?? null;
  const visiblePoints = useMemo(() => visibleBars(formula?.points ?? [], range), [formula?.points, range]);
  const shownPoints = display === 'indexed' ? indexedPoints(visiblePoints) : visiblePoints;
  const bars = carrierBars(visiblePoints);
  const canonical = formula?.expression ?? expression.trim().toUpperCase();
  const line: ChartComparisonLine = {
    id: canonical,
    label: canonical,
    color: MM.accent,
    valueMode: display === 'indexed' ? 'percent' : 'number',
    data: shownPoints,
  };
  const latest = visiblePoints.at(-1)?.value;
  const previous = visiblePoints.at(-2)?.value;
  const change = latest != null && previous ? ((latest / previous) - 1) * 100 : null;
  const hasNonPositive = visiblePoints.some((point) => point.value <= 0);
  const warning = formula?.warnings.join(' · ') || (display === 'indexed' && shownPoints.length === 0 ? 'Indexed view needs a non-zero first value.' : null);

  useEffect(() => {
    if (hasNonPositive && logScale) setLogScale(false);
  }, [hasNonPositive, logScale]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.closest('input, button, a, [role="dialog"]') || target.isContentEditable)) return;
      if (event.key === '/') {
        setJumpOpen(true);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <div className="tw tw-formula">
      <header className="tw-assetbar">
        <button type="button" className="tw-iconbtn" onClick={onClose} title="Back to Market" aria-label="Back to Market">
          <ArrowLeft size={14} />
        </button>
        <div className="tw-assetbar__identity tw-formula__identity">
          <FunctionSquare size={15} color={MM.accent} aria-hidden="true" />
          <h1 className="tw-assetbar__symbol">{canonical}</h1>
          <span className="tw-assetbar__kind">Formula symbol</span>
        </div>
        <div className="tw-formula__components" aria-label="Formula components">
          {(formula?.components ?? []).map((component) => <span key={component}>{component}</span>)}
        </div>
        <div className="tw-assetbar__spacer" />
        <div className="tw-assetbar__quote">
          <span className="tw-assetbar__price">{latest == null ? '—' : latest.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
          <span className="tw-assetbar__change" style={{ color: change == null ? MM.dim : change >= 0 ? MM.up : MM.down }}>
            {change == null ? '—' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`}
          </span>
        </div>
      </header>

      <div className="tw-body">
        <main className="tw-main">
          <div className="tw-toolbar" role="toolbar" aria-label="Formula chart controls">
            <div className="tw-segment" role="group" aria-label="Formula interval">
              {CHART_TIMEFRAMES.map((value) => (
                <button key={value} type="button" aria-pressed={timeframe === value} onClick={() => setTimeframe(value)}>{value}</button>
              ))}
            </div>
            <div className="tw-segment" role="group" aria-label="Formula visible range">
              {CHART_RANGES.map((value) => (
                <button key={value} type="button" aria-pressed={range === value} onClick={() => setRange(value)}>{value}</button>
              ))}
            </div>
            <span className="tw-sep" />
            <div className="tw-segment" role="group" aria-label="Formula value display">
              <button type="button" aria-pressed={display === 'value'} onClick={() => setDisplay('value')}>Value</button>
              <button type="button" aria-pressed={display === 'indexed'} onClick={() => setDisplay('indexed')}>Indexed %</button>
            </div>
            <span className="tw-toolbar__spacer" />
            <span className="tw-formula__basis">Split-adjusted closes · shared timestamps</span>
            <button
              type="button"
              className="tw-axis-toggle"
              onClick={() => setLogScale((value) => !value)}
              disabled={hasNonPositive}
              aria-pressed={logScale}
              title={hasNonPositive ? 'Log scale is unavailable while the formula has non-positive values' : 'Toggle logarithmic scale'}
            >
              {logScale ? 'Log' : 'Lin'}
            </button>
          </div>

          {formulaData.loading && !formula ? (
            <div className="tw-stage"><div className="tw-stage__empty">Calculating formula history…</div></div>
          ) : formulaData.error ? (
            <div className="tw-stage"><div className="tw-stage__empty" role="alert">{formulaData.error}</div></div>
          ) : (
            <ChartStage
              symbol={canonical}
              timeframe={timeframe}
              bars={bars}
              events={[]}
              evidence={[]}
              plots={[]}
              warning={warning}
              comparisonMode
              comparisonLines={shownPoints.length ? [line] : []}
              comparisonError={null}
              financialOverlayValuation={false}
              financialOverlayInverted={false}
              priceAlerts={[]}
              draftAlertPrice={null}
              alertPlacementActive={false}
              onAlertPriceSelected={() => undefined}
              insiderDisplayMode="individual"
              logScale={logScale}
              showVolume={false}
              indicators={[]}
              indicatorActions={NO_INDICATOR_ACTIONS}
              indicatorPriceStretch={3}
              onIndicatorPaneStretch={() => undefined}
              layoutKey={`${timeframe}:${range}:${display}`}
              overlay={jumpOpen ? (
                <SymbolJump
                  seed=""
                  onClose={() => setJumpOpen(false)}
                  onPick={(value, type) => { setJumpOpen(false); onNavigate(value, type); }}
                />
              ) : null}
            />
          )}
        </main>
      </div>
    </div>
  );
}
