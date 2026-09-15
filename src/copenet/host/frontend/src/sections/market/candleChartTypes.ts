import type { ChartWorkspaceBridge } from './drawings/types';
import type { ChartEvent, EvidenceItem, Ohlcv, PriceAlert } from './types';
import type { FinancialOverlayPoint } from './financialOverlay';
import type { ChartComparisonLine } from './chartComparison';
import type { InsiderDisplayMode } from './chartRanges';
import type { ComputedIndicator } from './indicators/compute';
import type { IndicatorRowActions } from './indicators/IndicatorRows';
import type { ChartReplayBinding } from './replay/chartReplay';

export interface CandleChartProps {
  chartWorkspace?: ChartWorkspaceBridge;
  bars: Ohlcv[];
  /** What the candle series draws, aligned index-for-index with `bars`. Defaults to `bars`.
   *  A style like Heikin Ashi substitutes here and nowhere else: every other consumer —
   *  volume, markers, decorations, alert lines — keeps reading prices that actually traded. */
  displayBars?: Ohlcv[];
  /** Present only on a chart that can be replayed. Drives the start-point picker and, once
   *  active, suspends auto-fitting so the framing stays the operator's. */
  replay?: ChartReplayBinding;
  events?: ChartEvent[];
  /** Full evidence rows backing the markers — clicking a marker day pops their details. */
  evidence?: EvidenceItem[];
  height?: number;
  /** Filing-date-aligned financial observations on their own left-side scale. */
  financialOverlay?: FinancialOverlayPoint[];
  /** Metric id — any entry from market.financial.metrics.list. */
  financialOverlayKind?: string;
  /** Unit the overlay observations carry (USD, ratio, USD/shares, shares). */
  financialOverlayUnit?: string;
  /** Valuation series step per price bar; financial series step per filing. */
  financialOverlayValuation?: boolean;
  /** Inverted valuations (yields) format as percentages instead of multiples. */
  financialOverlayInverted?: boolean;
  priceAlerts?: PriceAlert[];
  draftAlertPrice?: number | null;
  alertPlacementActive?: boolean;
  onAlertPriceSelected?: (price: number) => void;
  /** Volume is an ordinary plot the operator can remove, not a permanent fixture. */
  showVolume?: boolean;
  /** Technical indicators, already computed. Price overlays share the candle pane; the rest
   *  each get their own pane below it. The chart hands these straight to the indicator layer
   *  and never inspects them. */
  indicators?: ComputedIndicator[];
  /** Supplied when the operator may act on an indicator from the chart itself. Omitted, the
   *  pane heads still show their legend but carry no controls. */
  indicatorActions?: IndicatorRowActions;
  /** How much of the chart the price pane holds against each indicator pane. */
  indicatorPriceStretch: number;
  /** Fires when a pane separator has been dragged, so the division can be persisted. */
  onIndicatorPaneStretch?: (next: { priceStretch: number; byInstance: Record<string, number> }) => void;
  /** Crosshair bar under the pointer, or null when the pointer leaves the chart. Lets the
   *  legend live ON the chart instead of in a metadata strip wrapped around it. */
  onHoverBar?: (bar: Ohlcv | null) => void;
  comparisonMode?: boolean;
  comparisonLines?: ChartComparisonLine[];
  insiderDisplayMode?: InsiderDisplayMode;
  logScale?: boolean;
}
