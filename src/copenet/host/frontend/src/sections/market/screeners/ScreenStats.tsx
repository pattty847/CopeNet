// One line of screen-level context under the definition: how many matched, how
// concentrated they are, and what the typical match is doing. Run-level facts
// (observed time, coverage) live in the header, not here.
import { compactMoney } from './model';
import type { ScreenSummary } from './screenSummary';

const signed = (value: number | null, digits = 1) => (value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`);
const tone = (value: number | null) => (value == null || value === 0 ? '' : value > 0 ? 'Bullish' : 'Bearish');

export function ScreenStats({ summary, eligible, missingFields }: { summary: ScreenSummary; eligible: number; missingFields: number }) {
  const lead = summary.sectors[0];
  const sectorCount = summary.sectors.length + (summary.otherSectors ? 1 : 0);
  return (
    <div className="scr-stats" role="list">
      <div role="listitem">
        <span className="scr-eyebrow">Matches</span>
        <b>{summary.count}</b>
        <span className="scr-stats__dim">of {eligible.toLocaleString()} eligible</span>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Sector lead</span>
        <b>{lead ? `${lead.name} ${Math.round((lead.count / summary.count) * 100)}%` : '—'}</b>
        {summary.count > 0 && (
          <span className="scr-sectorbar" aria-hidden="true">
            {summary.sectors.map((sector) => (
              <i key={sector.name} style={{ width: `${((sector.count / summary.count) * 100).toFixed(1)}%` }} title={`${sector.name} ${sector.count}`} />
            ))}
            <i data-rest style={{ flex: 1 }} title={`Other ${summary.otherSectors}`} />
          </span>
        )}
        <span className="scr-stats__dim">{sectorCount} sectors</span>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Median day</span>
        <b data-direction={tone(summary.medians.change)}>{signed(summary.medians.change, 2)}</b>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Median 1-mo</span>
        <b data-direction={tone(summary.medians.monthReturn)}>{signed(summary.medians.monthReturn)}</b>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Median rel. vol</span>
        <b>{summary.medians.relativeVolume == null ? '—' : `${summary.medians.relativeVolume.toFixed(2)}×`}</b>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Median liquidity</span>
        <b>{summary.medians.dollarVolume == null ? '—' : compactMoney(summary.medians.dollarVolume)}</b>
        <span className="scr-stats__dim">/day</span>
      </div>
      <div role="listitem">
        <span className="scr-eyebrow">Missing fields</span>
        <b className={missingFields ? '' : 'scr-stats__dim'}>{missingFields}</b>
      </div>
    </div>
  );
}
