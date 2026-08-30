// One chart control system.
//
// The baseline was six widget families in a horizontally scrolling strip, each with its own
// visual language and colour. This is one grammar: intervals and ranges stay TEXTUAL because
// that is the conventional notation and an icon for "3Y" would be a puzzle; everything else
// is a 28px icon that opens a popover. Grouping is semantic — what period am I looking at,
// what is drawn on it, how is it drawn — and the groups are separated by seams, not by gaps.

import { useRef, useState, type ReactNode, type RefObject } from 'react';
import { ChartSpline, FileText, GitCompareArrows, PanelBottomClose, PanelBottomOpen, Settings2 } from 'lucide-react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import type { ChartRange, ChartTimeframe } from './chartRanges';
import { CHART_RANGES, CHART_TIMEFRAMES } from './chartRanges';

export function ChartToolbar({
  timeframe,
  onTimeframe,
  range,
  onRange,
  logScale,
  onLogScale,
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
  onLogScale: (value: boolean) => void;
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
      <div className="tw-segment" role="group" aria-label="Bar interval">
        {CHART_TIMEFRAMES.map((value) => (
          <button key={value} type="button" aria-pressed={timeframe === value} onClick={() => onTimeframe(value)} title={`${value === 'D' ? 'Daily' : value === 'W' ? 'Weekly' : 'Monthly'} bars`}>
            {value}
          </button>
        ))}
      </div>

      <div className="tw-segment" role="group" aria-label="Visible range">
        {CHART_RANGES.map((value) => (
          <button key={value} type="button" aria-pressed={range === value} onClick={() => onRange(value)}>
            {value === 'MAX' ? 'MAX' : value}
          </button>
        ))}
      </div>

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

      <div className="tw-segment" role="group" aria-label="Price axis">
        <button type="button" aria-pressed={!logScale} onClick={() => onLogScale(false)} title="Linear price axis">Lin</button>
        <button type="button" aria-pressed={logScale} onClick={() => onLogScale(true)} title="Logarithmic price axis">Log</button>
      </div>

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
