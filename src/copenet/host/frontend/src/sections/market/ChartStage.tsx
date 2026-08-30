// The chart and everything that belongs ON it.
//
// The baseline wrapped the chart in three permanent metadata strips — OHLCV above, overlay
// provenance below, marker state in a footer. All of it was chart state, so all of it moves
// onto the chart as a legend, which is both the conventional place to look and free in
// pixels. What is left underneath the chart is nothing at all.

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { TriangleAlert, X } from 'lucide-react';
import { CandleChart } from './CandleChart';
import { MM, mono, toneColor } from './marketUi';
import { timeframeLabel, type ChartTimeframe } from './chartRanges';
import type { ChartComparisonLine } from './chartComparison';
import { legendColor, legendOutputs, type ComputedIndicator } from './indicators/compute';
import { IndicatorControls } from './indicators/IndicatorControls';
import type { IndicatorRowActions } from './indicators/IndicatorRows';
import type { FinancialOverlayPoint } from './financialOverlay';
import type { InsiderDisplayMode } from './chartRanges';
import type { ChartEvent, EvidenceItem, Ohlcv, PriceAlert } from './types';

function money(value?: number | null): string {
  return value == null ? '—' : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function volume(value?: number | null): string {
  if (value == null) return '—';
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return value.toLocaleString();
}

export interface StagePlot {
  id: string;
  label: string;
  color: string;
  value?: string;
  onRemove?: () => void;
}

export function ChartStage({
  symbol,
  timeframe,
  bars,
  events,
  evidence,
  plots,
  warning,
  comparisonMode,
  comparisonLines,
  comparisonError,
  financialOverlay,
  financialOverlayKind,
  financialOverlayUnit,
  financialOverlayValuation,
  financialOverlayInverted,
  priceAlerts,
  draftAlertPrice,
  alertPlacementActive,
  onAlertPriceSelected,
  insiderDisplayMode,
  logScale,
  showVolume,
  indicators,
  indicatorActions,
  layoutKey,
  overlay,
}: {
  symbol: string;
  timeframe: ChartTimeframe;
  bars: Ohlcv[];
  events: ChartEvent[];
  evidence: EvidenceItem[];
  plots: StagePlot[];
  warning: string | null;
  comparisonMode: boolean;
  comparisonLines: ChartComparisonLine[];
  comparisonError: string | null;
  financialOverlay?: FinancialOverlayPoint[];
  financialOverlayKind?: string;
  financialOverlayUnit?: string;
  financialOverlayValuation: boolean;
  financialOverlayInverted: boolean;
  priceAlerts: PriceAlert[];
  draftAlertPrice: number | null;
  alertPlacementActive: boolean;
  onAlertPriceSelected: (price: number) => void;
  insiderDisplayMode: InsiderDisplayMode;
  logScale: boolean;
  showVolume: boolean;
  indicators: ComputedIndicator[];
  indicatorActions: IndicatorRowActions;
  /** Changes whenever something outside the chart resizes its region — the drawer snap, the
   *  rail. The chart is re-measured on this rather than only on a ResizeObserver, because an
   *  observer that silently never fires leaves the chart at its old height, overflowing. */
  layoutKey: string;
  overlay?: ReactNode;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(420);
  const [hovered, setHovered] = useState<Ohlcv | null>(null);

  // Rounding to 8px keeps sub-pixel layout jitter from churning the chart's size.
  const measure = useCallback(() => {
    const node = stageRef.current;
    if (!node) return;
    // Never taller than the region it lives in: an oversized chart overflows the stage and
    // paints its time axis across whatever is docked below.
    const next = Math.max(120, Math.round(node.clientHeight / 8) * 8);
    setHeight((current) => (Math.abs(current - next) > 4 ? next : current));
  }, []);

  // Three triggers, because no single one is reliable. `layoutKey` covers the deliberate
  // resizes (drawer snap, rail collapse) and is the one that always fires; the window
  // listener covers viewport changes; the observer covers everything else, including layout
  // that settles a frame late.
  useLayoutEffect(measure, [measure, layoutKey]);

  useLayoutEffect(() => {
    const node = stageRef.current;
    if (!node) return;
    window.addEventListener('resize', measure);
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => {
      window.removeEventListener('resize', measure);
      observer.disconnect();
    };
  }, [measure]);

  useEffect(() => setHovered(null), [symbol, timeframe]);

  const shown = hovered ?? bars[bars.length - 1];
  const barDate = shown
    ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(shown.t * 1000))
    : null;

  return (
    <div className="tw-stage" ref={stageRef}>
      {bars.length === 0 ? (
        <div className="tw-stage__empty">No price history in this range.</div>
      ) : (
        <>
          <div className="tw-legend" aria-live="off">
            <div className="tw-legend__row">
              <span className="tw-legend__symbol">{symbol}</span>
              <span style={{ color: MM.dimmer, fontSize: 10 }}>{timeframeLabel(timeframe)}</span>
              {barDate && <span style={{ color: MM.dimmer, fontSize: 10 }}>{barDate}</span>}
            </div>
            {shown && !comparisonMode && (
              <div className="tw-legend__row tw-legend__ohlc">
                <span>O <b>{money(shown.o)}</b></span>
                <span>H <b>{money(shown.h)}</b></span>
                <span>L <b>{money(shown.l)}</b></span>
                <span>C <b style={{ color: toneColor(shown.c >= shown.o ? 'up' : 'down') }}>{money(shown.c)}</b></span>
                {showVolume && <span>V <b>{volume(shown.v)}</b></span>}
              </div>
            )}
            {plots.map((plot) => (
              <div key={plot.id} className="tw-legend__row tw-legend__plot">
                <span className="tw-legend__swatch" style={{ background: plot.color }} />
                <span style={{ color: MM.muted, fontSize: 10 }}>{plot.label}</span>
                {plot.value && <span style={{ color: plot.color, fontFamily: mono, fontSize: 10 }}>{plot.value}</span>}
                {plot.onRemove && (
                  <button type="button" onClick={plot.onRemove} title={`Remove ${plot.label}`} aria-label={`Remove ${plot.label}`}><X size={10} /></button>
                )}
              </div>
            ))}
            {/* PRICE OVERLAYS ONLY. A pane indicator reports inside its own pane, anchored
                with IPaneApi.getHTMLElement() — so its reading sits where its line is rather
                than in a stack over the price pane describing something two panes down. */}
            {indicators
              .filter((indicator) => indicator.visible && indicator.placement === 'price')
              .map((indicator) => (
              <div key={indicator.instanceId} className="tw-legend__row tw-legend__plot">
                <span className="tw-legend__swatch" style={{ background: legendColor(indicator) }} />
                <span style={{ color: MM.muted, fontSize: 10 }}>{indicator.label}</span>
                {indicator.insufficientHistory ? (
                  <span style={{ color: MM.dimmer, fontFamily: mono, fontSize: 10 }}>needs history</span>
                ) : (
                  legendOutputs(indicator)
                    .filter((output) => output.latest != null)
                    .map((output) => (
                      <span key={output.key} title={output.label} style={{ color: output.color, fontFamily: mono, fontSize: 10 }}>
                        {output.latest}
                      </span>
                    ))
                )}
                <IndicatorControls indicator={indicator} actions={indicatorActions} />
              </div>
            ))}
            {comparisonMode && (
              <div className="tw-legend__row" style={{ gap: 12 }}>
                {comparisonLines.map((line) => {
                  const last = line.data[line.data.length - 1]?.value;
                  return (
                    <span key={line.id} style={{ color: line.color, fontSize: 10 }}>
                      {line.label} {last == null ? '—' : `${last > 0 ? '+' : ''}${last.toFixed(1)}%`}
                    </span>
                  );
                })}
              </div>
            )}
          </div>

          <CandleChart
            bars={bars}
            events={events}
            evidence={evidence}
            height={height}
            financialOverlay={financialOverlay}
            financialOverlayKind={financialOverlayKind}
            financialOverlayUnit={financialOverlayUnit}
            financialOverlayValuation={financialOverlayValuation}
            financialOverlayInverted={financialOverlayInverted}
            priceAlerts={priceAlerts}
            draftAlertPrice={draftAlertPrice}
            alertPlacementActive={alertPlacementActive}
            onAlertPriceSelected={onAlertPriceSelected}
            comparisonMode={comparisonMode}
            comparisonLines={comparisonLines}
            insiderDisplayMode={insiderDisplayMode}
            logScale={logScale}
            showVolume={showVolume}
            indicators={indicators}
            indicatorActions={indicatorActions}
            onHoverBar={setHovered}
          />

          {/* A data-quality caveat qualifies every trend claim on the page, so it surfaces
              here where the claims are — and stays completely silent when nothing is wrong. */}
          {(warning || comparisonError) && (
            <div className="tw-warnband" role="status">
              <TriangleAlert size={12} aria-hidden="true" />
              <span>{comparisonError ?? warning}</span>
            </div>
          )}
        </>
      )}
      {overlay}
    </div>
  );
}
