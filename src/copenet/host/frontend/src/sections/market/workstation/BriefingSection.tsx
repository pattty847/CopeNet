// Briefing — home. The sweep's sentence is the page headline; beneath it, what changed on the
// left and the standing picture on the right; beneath both, the model's synthesis, labelled.
// The composition is fixed (it is one readout, not a set of panels), so it carries no
// Arrange control — the other sections do.

import { RefreshCw } from 'lucide-react';
import type { MarketSection } from '../../../lib/appSectionRouting';
import { EconomicCalendarWidget } from '../EconomicCalendarWidget';
import { StandingPicture } from './StandingPicture';
import { Emphasized, Synthesis } from './Synthesis';
import { WhatChanged } from './WhatChanged';
import type { EconomicCalendarState } from '../useEconomicCalendar';
import type { DashboardPayload, LedgerReport, MarketRead, MorningBriefPayload } from '../types';

function sweptStamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

export function BriefingSection({
  dashboard,
  brief,
  generating,
  onRunSweep,
  read,
  reading,
  readError,
  onRunRead,
  onExplain,
  onOpen,
  onGoTo,
  calendar,
  ledger,
  briefError,
}: {
  dashboard: DashboardPayload;
  brief: MorningBriefPayload | null;
  generating: boolean;
  onRunSweep: () => void;
  read: MarketRead | null;
  reading: boolean;
  readError: string | null;
  onRunRead: () => void;
  onExplain: () => void;
  onOpen: (symbol: string) => void;
  onGoTo: (section: MarketSection) => void;
  calendar: EconomicCalendarState;
  ledger: LedgerReport | null;
  briefError?: string | null;
}) {
  const ledgerLine = ledger && ledger.totalClaims > 0 ? `${ledger.totalClaims} claims logged · ${ledger.pendingHorizons} horizons pending` : null;
  const headline = brief?.headline ?? (briefError ? 'Saved briefing unavailable.' : generating ? 'Building the first delta snapshot…' : 'No saved briefing yet.');

  return (
    <div className="mw-briefing">
      <div className="mw-headline-row">
        <h2 className="mw-headline">{headline}</h2>
        <div className="mw-headline-row__tools">
          {brief && <span className="mw-sect__meta">swept {sweptStamp(brief.generatedAt)}</span>}
          <button type="button" className="tw-btn" onClick={onRunSweep} disabled={generating}>
            <RefreshCw size={12} className={generating ? 'tw-spin' : undefined} />
            {generating ? 'Sweeping…' : brief ? 'Sweep again' : 'Run sweep'}
          </button>
        </div>
      </div>
      {read && (
        <p className="mw-masthead__read" title="The model's read of the tape — interpretation, stamped as such below">
          <span className="mw-masthead__stamp">✦ {read.model}</span>
          <Emphasized text={read.headline} emphasis={read.emphasis} />
        </p>
      )}
      {brief?.note && <p className="mw-quiet" style={{ margin: '-6px 0 10px', fontStyle: 'italic' }}>{brief.note}</p>}

      <div className="mw-brief">
        <WhatChanged
          brief={brief}
          generating={generating}
          briefUnavailable={Boolean(briefError)}
          regime={dashboard.regime}
          calendar={
            <EconomicCalendarWidget
              calendar={calendar.calendar}
              loading={calendar.loading}
              refreshing={calendar.refreshing}
              error={calendar.error}
              onRefresh={() => void calendar.refresh()}
            />
          }
          ledgerLine={ledgerLine}
          onOpen={onOpen}
          onExplain={onExplain}
          onGoTo={onGoTo}
        />
        <StandingPicture dashboard={dashboard} read={read} onOpen={onOpen} onGoTo={onGoTo} />
        <Synthesis
          read={read}
          reading={reading}
          readError={readError}
          onRunRead={onRunRead}
          onExplain={onExplain}
          onOpen={onOpen}
          contrarian={dashboard.contrarian}
        />
      </div>

      <p className="mw-footnote">Reads are evidence-based with caveats — never forecasts. Scans refresh the saved market snapshot.</p>
    </div>
  );
}
