import { useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { QuoteEvent } from '../../lib/wsMarketQuote';
import { useAppStore } from '../../store/useAppStore';

export function useLiveQuote(symbol: string | null) {
  const connection = useAppStore((state) => state.wsStatus);
  const [visible, setVisible] = useState(() => typeof document !== 'undefined' && document.visibilityState === 'visible');
  const [event, setEvent] = useState<QuoteEvent | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [now, setNow] = useState(Date.now);

  useEffect(() => {
    const update = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  useEffect(() => {
    setEvent(null);
    if (!symbol || !visible || connection !== 'connected') return;
    const subscription = wsClient.marketQuote.open(symbol, (next) =>
      setEvent((previous) => ({
        ...next,
        quote: next.quote ?? (previous?.subscriptionId === next.subscriptionId ? previous.quote : null),
      })),
    );
    const lease = window.setInterval(subscription.renew, 25_000);
    const age = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => {
      window.clearInterval(lease);
      window.clearInterval(age);
      subscription.close();
    };
  }, [symbol, visible, connection, retryKey]);

  const current = event?.symbol === symbol ? event : null;
  const quote = current?.quote ?? null;
  const stale = quote != null && Math.max(now, Date.now()) / 1000 - quote.quoteTime > 60;
  const status =
    !visible || !symbol
      ? 'paused'
      : connection !== 'connected'
        ? 'offline'
        : current?.status === 'streaming'
          ? stale
            ? 'delayed'
            : 'streaming'
          : (current?.status ?? 'connecting');
  return { quote, status, retry: () => setRetryKey((value) => value + 1) };
}
