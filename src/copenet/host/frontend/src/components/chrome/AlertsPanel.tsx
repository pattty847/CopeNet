import { useEffect, useMemo, useState } from 'react';
import { Bell, ChevronRight } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';
import { conditionLabel, timeLabel } from '../../sections/market/monitoring/model';
import type { AlertsState } from '../../sections/market/monitoring/types';
import { ChromeDrawer, ChromeSection } from './ChromeDrawer';
import { markAlertsSeen } from './alertInbox';

/** What fired, newest first, from the same evidence log Scans & alerts shows. Rules are
 *  managed there; this is the inbox. */
export function AlertsPanel({ onClose }: { onClose: () => void }) {
  const openMarketTicker = useAppStore((state) => state.openMarketTicker);
  const openMarketSection = useAppStore((state) => state.openMarketSection);
  const [state, setState] = useState<AlertsState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    markAlertsSeen();
    wsClient.marketMonitoring.alerts().then(setState).catch((reason: Error) => setError(reason.message));
  }, []);

  const rulesById = useMemo(() => new Map((state?.alerts ?? []).map((rule) => [rule.alertId, rule])), [state]);
  const armed = (state?.alerts ?? []).filter((rule) => rule.enabled).length;

  const manage = () => {
    openMarketSection('scans');
    onClose();
  };

  return (
    <ChromeDrawer eyebrow="Market" title="Alerts" icon={Bell} onClose={onClose}>
      {error && <p className="text-[12px] text-operator-error">Couldn't load alerts: {error}</p>}
      {!state && !error && <p className="text-[12px] text-shell-muted">Loading…</p>}
      {state && (
        <>
          <ChromeSection title="Recent events" hint={`${armed} armed rule${armed === 1 ? '' : 's'}. Events fire on completed candles after a linked scan runs.`}>
            {state.events.length === 0 ? (
              <p className="rounded-xl border border-dashed border-shell-border px-3.5 py-4 text-[12px] text-shell-muted">
                Nothing has fired yet. Place a level on a chart or add a rule in Scans &amp; alerts.
              </p>
            ) : (
              <ul className="divide-y divide-shell-border overflow-hidden rounded-xl border border-shell-border bg-shell-panel">
                {state.events.slice(0, 40).map((event) => {
                  const rule = rulesById.get(event.alertId);
                  return (
                    <li key={event.eventId}>
                      <button
                        type="button"
                        onClick={() => {
                          openMarketTicker(event.symbol);
                          onClose();
                        }}
                        className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-shell-panel-strong"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="font-mono text-[13px] font-semibold text-shell-text">
                              {event.symbol} <span className="font-sans text-[11px] font-normal text-shell-muted">· {event.timeframe}</span>
                            </span>
                            <time className="shrink-0 text-[11px] text-shell-muted">{timeLabel(event.evaluatedAt)}</time>
                          </div>
                          <div className="truncate text-[12px] text-shell-muted">
                            {rule ? conditionLabel(rule) : event.condition}
                            {event.phase ? ` · ${event.phase.replaceAll('_', ' ')}` : ''}
                          </div>
                        </div>
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-shell-muted" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </ChromeSection>
          <button
            type="button"
            onClick={manage}
            className="inline-flex items-center gap-1 text-[12px] font-medium text-shell-accent hover:underline"
          >
            Manage rules in Scans &amp; alerts <ChevronRight className="h-3 w-3" />
          </button>
        </>
      )}
    </ChromeDrawer>
  );
}
