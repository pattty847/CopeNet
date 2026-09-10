import { isIntradayTimeframe, type ChartTimeframe } from '../chartRanges';
import { createContext, useContext, useState, type ReactNode } from 'react';
import { Bell } from 'lucide-react';
import type { ComputedIndicator } from '../indicators/compute';
import { AlertEditor } from './AlertEditor';
import { MonitoringSheet } from './MonitoringSheet';
import { newAlert } from './model';
import { useMonitoring } from './useMonitoring';
import './monitoring.css';

export const TickerAlertContext = createContext<{ symbol: string; timeframe: 'D' | 'W' | 'M' } | null>(null);

function TickerAlertEditor({ indicator, onClose }: { indicator: ComputedIndicator; onClose: () => void }) {
  const context = useContext(TickerAlertContext)!;
  const { scans, notifications, catalogue, error, reload } = useMonitoring();
  if (!scans || !notifications || !catalogue.length)
    return (
      <MonitoringSheet title="Create indicator alert" onClose={onClose}>
        <div className="mm-monitor-form">
          <p role={error ? 'alert' : 'status'}>{error || 'Loading scan and indicator settings…'}</p>
          <button className="tw-btn" onClick={() => void reload()}>
            Retry
          </button>
        </div>
      </MonitoringSheet>
    );
  const rule = {
    ...newAlert(context.symbol),
    timeframe: ({ D: 'daily', W: 'weekly', M: 'monthly' } as const)[context.timeframe],
    scanId:
      scans.scans.find((scan) => scan.enabled && scan.sources.includes('prices') && scan.resolvedSymbols.includes(context.symbol))?.id ??
      '',
    left: {
      kind: 'indicator' as const,
      indicatorId: indicator.indicatorId,
      config: indicator.instance.config,
      output: indicator.outputs[0].key,
    },
  };
  return (
    <AlertEditor initial={rule} scans={scans} notifications={notifications} catalogue={catalogue} onClose={onClose} onSaved={reload} />
  );
}

export function IndicatorAlertButton({ indicator }: { indicator: ComputedIndicator }) {
  const context = useContext(TickerAlertContext);
  const [open, setOpen] = useState(false);
  if (!context) return null;
  return (
    <>
      <button
        type="button"
        className="tw-iconbtn tw-iconbtn--xs"
        aria-label={`Create alert for ${indicator.label}`}
        title="Create alert with these indicator settings"
        onClick={() => setOpen(true)}
      >
        <Bell size={11} />
      </button>
      {open && <TickerAlertEditor indicator={indicator} onClose={() => setOpen(false)} />}
    </>
  );
}

export function TickerAlertProvider({ symbol, timeframe, children }: { symbol: string; timeframe: ChartTimeframe; children: ReactNode }) {
  // The alert engine evaluates COMPLETED DAILY CLOSES — there is no intraday evaluation lane
  // yet (that is Sentinel Phase 1, which the intraday store unblocks but does not deliver).
  // So an alert placed while reading a 5m chart is still a daily alert, and saying `daily`
  // here is the truth about what will be evaluated rather than a guess at what was on screen.
  const evaluated = isIntradayTimeframe(timeframe) ? 'D' : timeframe;
  return <TickerAlertContext.Provider value={{ symbol, timeframe: evaluated }}>{children}</TickerAlertContext.Provider>;
}
