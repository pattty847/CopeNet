// One chart control system.
//
// The baseline was six widget families in a horizontally scrolling strip, each with its own
// visual language and colour. This is one grammar: intervals and ranges stay TEXTUAL because
// that is the conventional notation and an icon for "3Y" would be a puzzle; everything else
// is a 28px icon that opens a popover. Grouping is semantic — what period am I looking at,
// what is drawn on it, how is it drawn — and the groups are separated by seams, not by gaps.

import { useRef, useState, type ReactNode, type RefObject } from 'react';
import { ChartSpline, FileText, GitCompareArrows, PanelBottomClose, PanelBottomOpen, Rewind, Settings2 } from 'lucide-react';
import { FloatingPopover } from '../../components/FloatingPopover';
import { rangesFor, type ChartRange, type ChartTimeframe } from './chartRanges';
import { TimeframeSelector } from './TimeframeSelector';
import type { CandleStyle } from './heikinAshi';
import type { ReplayPhase } from './replay/useChartReplay';

export function ChartToolbar({
  timeframe,
  onTimeframe,
  range,
  onRange,
  logScale,
  candleStyle,
  onCandleStyle,
  onLoadEarlier,
  loadingEarlier,
  onLogScale,
  replayPhase,
  replayAvailable,
  onToggleReplay,
  comparisonActive,
  comparisonCount,
  plotCount,
  eventsActive,
  alertControl,
  drawerOpen,
  onToggleDrawer,
  plotsMenu,
  compareMenu,
  eventsMenu,
  settingsMenu,
}: {
  timeframe: ChartTimeframe;
  onTimeframe: (value: ChartTimeframe) => void;
  range: ChartRange;
  onRange: (value: ChartRange) => void;
  logScale: boolean;
  candleStyle: CandleStyle;
  onCandleStyle: (style: CandleStyle) => void;
  /** Present only on a 1m chart, the one grain the vendor caps below its own window. */
  onLoadEarlier?: () => void;
  loadingEarlier?: boolean;
  onLogScale: (value: boolean) => void;
  replayPhase: ReplayPhase;
  /** False when there is nothing to walk through — a single bar is not a replay. */
  replayAvailable: boolean;
  onToggleReplay: () => void;
  comparisonActive: boolean;
  comparisonCount: number;
  plotCount: number;
  eventsActive: boolean;
  alertControl: ReactNode;
  drawerOpen: boolean;
  onToggleDrawer: () => void;
  plotsMenu: (anchor: RefObject<HTMLButtonElement | null>, open: boolean, close: () => void) => ReactNode;
  compareMenu: (anchor: RefObject<HTMLButtonElement | null>, open: boolean, close: () => void) => ReactNode;
  eventsMenu: (anchor: RefObject<HTMLButtonElement | null>, open: boolean, close: () => void) => ReactNode;
  settingsMenu: (anchor: RefObject<HTMLButtonElement | null>, open: boolean, close: () => void) => ReactNode;
}) {
  return (
    <div className="tw-toolbar" role="toolbar" aria-label="Chart controls">
      <TimeframeSelector timeframe={timeframe} onTimeframe={onTimeframe} />

      {/* The ranges follow the lane. 5Y on a 5m chart would return the same 60 days as MAX
          and look broken doing it. */}
      <div className="tw-segment" role="group" aria-label="Visible range">
        {rangesFor(timeframe).map((value) => (
          <button key={value} type="button" aria-pressed={range === value} onClick={() => onRange(value)}>
            {value === 'MAX' ? 'MAX' : value}
          </button>
        ))}
      </div>

      {onLoadEarlier && (
        <button type="button" className="tw-btn" onClick={onLoadEarlier} disabled={loadingEarlier}
          title="Fetch another week of 1-minute history — the only interval the vendor caps per request">
          {loadingEarlier ? 'Loading…' : 'Load earlier'}
        </button>
      )}

      {/* Replay belongs to the period group: it is another answer to "what stretch of time
          am I looking at", not another thing drawn on the chart. */}
      <button
        type="button"
        className="tw-iconbtn"
        data-active={replayPhase !== 'off'}
        aria-pressed={replayPhase !== 'off'}
        disabled={!replayAvailable}
        onClick={onToggleReplay}
        title={replayPhase === 'arming' ? 'Cancel — pick a start bar on the chart  (esc)' : replayPhase === 'active' ? 'Exit replay  (r)' : 'Replay this range bar by bar  (r)'}
        aria-label={replayPhase === 'off' ? 'Replay this range bar by bar' : 'Exit replay'}
      >
        <Rewind size={14} />
      </button>

      <span className="tw-sep" />

      <ToolbarMenu
        label="Plots"
        icon={<ChartSpline size={14} />}
        active={plotCount > 0}
        count={plotCount}
        render={plotsMenu}
      />
      <ToolbarMenu
        label="Compare"
        icon={<GitCompareArrows size={14} />}
        active={comparisonActive}
        count={comparisonCount}
        render={compareMenu}
      />
      <ToolbarMenu
        label="Filings & events"
        icon={<FileText size={14} />}
        active={eventsActive}
        render={eventsMenu}
      />
      {alertControl}

      <span className="tw-toolbar__spacer" />

      {/* Heikin Ashi is a way of DRAWING the same bars, so it sits with the axis toggle
          rather than in the indicator picker: it adds no series and computes no signal. */}
      <button
        type="button"
        className="tw-axis-toggle"
        aria-pressed={candleStyle === 'heikin-ashi'}
        onClick={() => onCandleStyle(candleStyle === 'heikin-ashi' ? 'candles' : 'heikin-ashi')}
        aria-label={`Candles: ${candleStyle === 'heikin-ashi' ? 'Heikin Ashi' : 'standard'}. Switch to ${candleStyle === 'heikin-ashi' ? 'standard' : 'Heikin Ashi'}`}
        title={
          candleStyle === 'heikin-ashi'
            ? 'Heikin Ashi — smoothed bars, not traded prices. Click for standard candles'
            : 'Standard candles · click for Heikin Ashi'
        }
      >
        {candleStyle === 'heikin-ashi' ? 'HA' : 'Std'}
      </button>

      <button
        type="button"
        className="tw-axis-toggle"
        onClick={() => onLogScale(!logScale)}
        aria-label={`Price axis: ${logScale ? 'logarithmic' : 'linear'}. Switch to ${logScale ? 'linear' : 'logarithmic'}`}
        title={`${logScale ? 'Logarithmic' : 'Linear'} axis · click for ${logScale ? 'linear' : 'logarithmic'}`}
      >
        {logScale ? 'Log' : 'Lin'}
      </button>

      <ToolbarMenu label="Chart settings & data source" icon={<Settings2 size={14} />} render={settingsMenu} />

      <span className="tw-sep" />

      <button
        type="button"
        className="tw-iconbtn"
        onClick={onToggleDrawer}
        title={drawerOpen ? 'Collapse research drawer  (\\)' : 'Open research drawer  (\\)'}
        aria-label={drawerOpen ? 'Collapse research drawer' : 'Open research drawer'}
      >
        {drawerOpen ? <PanelBottomClose size={14} /> : <PanelBottomOpen size={14} />}
      </button>
    </div>
  );
}

/** An icon trigger plus its popover. The count badge is the only thing that distinguishes a
 *  tool holding state from one that is merely available — which is what you want to see at a
 *  glance on a toolbar you have stopped reading. */
function ToolbarMenu({
  label,
  icon,
  active = false,
  count,
  render,
}: {
  label: string;
  icon: ReactNode;
  active?: boolean;
  count?: number;
  render: (anchor: RefObject<HTMLButtonElement | null>, open: boolean, close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={anchor}
        type="button"
        className="tw-iconbtn"
        data-active={active || open}
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => setOpen((value) => !value)}
      >
        {icon}
        {count != null && count > 0 && <span aria-hidden="true" className="tw-iconbtn__count">{count}</span>}
      </button>
      {render(anchor, open, () => setOpen(false))}
    </>
  );
}
