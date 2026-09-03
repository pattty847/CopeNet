import { useEffect, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { wsClient } from '../../../lib/wsClient';
import { timeLabel } from './model';

export function NextScanControl({ onOpen }: { onOpen: () => void }) {
  const [label, setLabel] = useState('Scan controls');
  const [detail, setDetail] = useState('View scan scopes and schedules');
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const state = await wsClient.marketMonitoring.scans();
        if (!alive) return;
        const scan = state.scans.find((item) => item.id === state.nextScanId);
        setLabel(
          state.nextRunAt
            ? `Next · ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone: scan?.timezone, timeZoneName: 'short' }).format(new Date(state.nextRunAt))}`
            : 'Scans paused',
        );
        setDetail(
          state.nextRunAt
            ? `${scan?.name ?? 'Scan'} · ${timeLabel(state.nextRunAt, scan?.timezone)}`
            : 'No automatic scan scheduled. Open scan controls.',
        );
      } catch {
        if (alive) {
          setLabel('Scan status unavailable');
          setDetail('Open scan controls to retry');
        }
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);
  return (
    <button type="button" className="tw-btn" onClick={onOpen} title={detail} aria-label={`Scan controls · ${label}`}>
      <Clock3 size={12} />
      {label}
    </button>
  );
}
