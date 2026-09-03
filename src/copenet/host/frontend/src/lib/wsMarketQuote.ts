import { safeUUID } from './wsNormalizers';

export type LiveQuote = {
  symbol: string;
  price: number;
  quoteTime: number;
  receivedAt: number;
  dayVolume: number | null;
  changePct: number | null;
  currency: string | null;
  marketHours: string;
};

export type QuoteEvent = {
  subscriptionId: string;
  symbol: string;
  status: 'connecting' | 'waiting' | 'streaming' | 'reconnecting' | 'unavailable' | 'paused';
  quote: LiveQuote | null;
};

type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;

/** One consumer in this browser; old requests/events cannot revive a departed ticker. */
export function createMarketQuoteApi(request: Request, connected: () => boolean) {
  let active: { id: string; symbol: string; receive: (event: QuoteEvent) => void } | null = null;
  return {
    receive(payload: unknown) {
      const event = payload as QuoteEvent;
      if (event?.subscriptionId === active?.id && event?.symbol === active?.symbol) active?.receive(event);
    },
    open(symbol: string, receive: (event: QuoteEvent) => void) {
      const id = safeUUID();
      active = { id, symbol, receive };
      const renew = () => {
        if (active?.id !== id || !connected()) return;
        void request('market.quote.subscribe', { symbol, subscriptionId: id }).catch(() => {
          if (active?.id === id) receive({ subscriptionId: id, symbol, status: 'unavailable', quote: null });
        });
      };
      renew();
      return {
        renew,
        close() {
          if (active?.id === id) active = null;
          // Do not reconnect a dead host merely to close a view-owned resource.
          if (connected()) void request('market.quote.unsubscribe', { subscriptionId: id }).catch(() => undefined);
        },
      };
    },
  };
}
