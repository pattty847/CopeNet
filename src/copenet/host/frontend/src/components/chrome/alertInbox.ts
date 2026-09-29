import { useCallback, useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';
import type { AlertEvent } from '../../sections/market/monitoring/types';

const LAST_SEEN_KEY = 'copenet.alerts.lastSeenAt';
const SEEN_EVENT = 'copenet:alerts-seen';

function readLastSeen(): string {
  try {
    return window.localStorage.getItem(LAST_SEEN_KEY) ?? '';
  } catch {
    return '';
  }
}

/** Record that the operator opened the inbox. Per browser on purpose: "unseen" is about
 *  this screen, and a phone and a desk each deserve their own badge. */
export function markAlertsSeen(): void {
  try {
    window.localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
  } catch {
    // Blocked storage: the badge just stays until the next page load.
  }
  window.dispatchEvent(new Event(SEEN_EVENT));
}

export function unseenAlertCount(events: AlertEvent[], lastSeenAt: string): number {
  if (!lastSeenAt) return events.length;
  const seen = Date.parse(lastSeenAt);
  return events.filter((event) => Date.parse(event.evaluatedAt) > seen).length;
}

/** The bell's badge: alert events evaluated since this browser last opened the inbox. */
export function useUnseenAlertCount(): number {
  const connected = useAppStore((state) => state.wsStatus === 'connected');
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [lastSeenAt, setLastSeenAt] = useState(readLastSeen);

  const refresh = useCallback(() => {
    wsClient.marketMonitoring.alerts().then((state) => setEvents(state.events)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (connected) refresh();
  }, [connected, refresh]);

  useEffect(() => {
    const onSeen = () => setLastSeenAt(readLastSeen());
    window.addEventListener(SEEN_EVENT, onSeen);
    return () => window.removeEventListener(SEEN_EVENT, onSeen);
  }, []);

  return unseenAlertCount(events, lastSeenAt);
}
