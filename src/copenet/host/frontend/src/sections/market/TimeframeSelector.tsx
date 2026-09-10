// The interval control: a few pinned buttons and a dropdown for everything else.
//
// The dropdown carries each interval's real depth, because the depth is the surprising part.
// An operator picking 15m has no way to guess it reaches 60 days while 3m reaches 30 — that
// is a property of which native grain the backend fetches, and discovering it as a chart
// that stops early is worse than reading it before the click.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import { ChartPopoverShell } from './chartPopoverShell';
import type { IntradayIntervalInfo } from '../../types/backend';
import { CHART_TIMEFRAMES, isIntradayTimeframe, timeframeLabel, type ChartTimeframe } from './chartRanges';
import { loadPinnedTimeframes, savePinnedTimeframes } from './tickerWorkspaceState';

function depthLabel(days: number): string {
  if (days >= 365) return `${(days / 365).toFixed(days % 365 === 0 ? 0 : 1)}y`;
  if (days >= 30) return `${Math.round(days / 30)}mo`;
  return `${days}d`;
}

export function TimeframeSelector({
  timeframe,
  onTimeframe,
}: {
  timeframe: ChartTimeframe;
  onTimeframe: (value: ChartTimeframe) => void;
}) {
  const [pinned, setPinned] = useState(loadPinnedTimeframes);
  const [catalog, setCatalog] = useState<IntradayIntervalInfo[]>([]);
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement | null>(null);

  // Asked once per session and shared by every ticker — the catalog describes the vendor,
  // not the symbol.
  useEffect(() => {
    let cancelled = false;
    void wsClient.marketIntradayIntervals()
      .then((next) => { if (!cancelled) setCatalog(next.intervals); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const pin = useCallback((value: ChartTimeframe) => {
    setPinned((current) => {
      const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
      // Refuse to empty the strip: an empty pinned list would leave no way back to a daily
      // chart except through the dropdown.
      const settled = next.length ? next : current;
      savePinnedTimeframes(settled);
      return settled;
    });
  }, []);

  // The selected interval always appears, pinned or not, so the strip cannot show a
  // selection the operator has no button for.
  const strip: ChartTimeframe[] = pinned.includes(timeframe) ? pinned : [...pinned, timeframe];

  return (
    <>
      <div className="tw-segment" role="group" aria-label="Bar interval">
        {strip.map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={timeframe === value}
            onClick={() => onTimeframe(value)}
            title={`${timeframeLabel(value)} bars`}
          >
            {value}
          </button>
        ))}
        <button
          ref={anchor}
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          title="All intervals"
          aria-label="Choose an interval"
        >
          <ChevronDown size={11} />
        </button>
      </div>

      {/* The shared frame, not a hand-rolled one — its own comment says two popovers
          re-declaring the same padding is how two popovers start looking different. Rolling
          my own is exactly how this one shipped transparent, with the rows reading straight
          through onto the chart behind them. */}
      {open && (
        <ChartPopoverShell anchor={anchor} open={open} onClose={() => setOpen(false)} title="Intervals" width={280}>
          <div className="tw-tfmenu">
            <div className="tw-tfmenu__head">Intraday</div>
            {catalog.length === 0 && <div className="tw-tfmenu__empty">Loading…</div>}
            {catalog.map((info) => (
              <Row
                key={info.interval}
                value={info.interval}
                label={info.interval}
                depth={depthLabel(info.windowDays)}
                note={info.derived ? `from ${info.grain}` : 'native'}
                selected={timeframe === info.interval}
                pinned={pinned.includes(info.interval)}
                onSelect={() => { onTimeframe(info.interval); setOpen(false); }}
                onPin={() => pin(info.interval)}
              />
            ))}

            <div className="tw-tfmenu__head">Daily and longer</div>
            {CHART_TIMEFRAMES.map((value) => (
              <Row
                key={value}
                value={value}
                label={value}
                depth="full history"
                note={timeframeLabel(value).toLowerCase()}
                selected={timeframe === value}
                pinned={pinned.includes(value)}
                onSelect={() => { onTimeframe(value); setOpen(false); }}
                onPin={() => pin(value)}
              />
            ))}
            <div className="tw-tfmenu__foot">
              Depth is what the vendor serves. Pin an interval to keep it in the toolbar.
            </div>
          </div>
        </ChartPopoverShell>
      )}
    </>
  );
}

function Row({
  label, depth, note, selected, pinned, onSelect, onPin,
}: {
  value: ChartTimeframe;
  label: string;
  depth: string;
  note: string;
  selected: boolean;
  pinned: boolean;
  onSelect: () => void;
  onPin: () => void;
}) {
  return (
    <div className="tw-tfrow" data-selected={selected}>
      <button type="button" className="tw-tfrow__pick" onClick={onSelect}>
        <span className="tw-tfrow__label">{label}</span>
        <span className="tw-tfrow__note">{note}</span>
        <span className="tw-tfrow__depth">{depth}</span>
      </button>
      <button
        type="button"
        className="tw-tfrow__pin"
        aria-pressed={pinned}
        onClick={onPin}
        title={pinned ? 'Unpin from the toolbar' : 'Pin to the toolbar'}
        aria-label={pinned ? `Unpin ${label}` : `Pin ${label}`}
      >
        ★
      </button>
    </div>
  );
}

export { isIntradayTimeframe };
