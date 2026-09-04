import { useViewResource } from './viewState/resources';
import { signedPct, toneHex, toneOf } from './workspaceViz';
import { useLiveQuote } from './useLiveQuote';
import './tickerLiveQuote.css';

const LABELS = {
  connecting: 'Connecting',
  waiting: 'Awaiting quote',
  streaming: 'Streaming',
  delayed: 'Delayed / idle',
  reconnecting: 'Reconnecting',
  unavailable: 'Unavailable',
  paused: 'Paused',
  offline: 'Offline',
};

/** Tick state stays here so the historical chart/indicator tree does not rerender per trade. */
export function TickerLiveQuote({
  symbol,
  price,
  changePct,
  pending,
}: {
  symbol: string;
  price: number | null;
  changePct: number | null;
  pending: boolean;
}) {
  const live = useLiveQuote(pending ? null : symbol);
  const quote = live.quote;
  const shownPrice = quote?.price ?? price;
  const change = quote ? quote.changePct : changePct;
  const timestamp = quote ? new Date(quote.quoteTime * 1000).toLocaleString() : null;
  const currency = quote?.currency;
  useViewResource(symbol, { key: 'quote:displayed', kind: 'quote', label: 'Displayed quote',
    status: live.status === 'streaming' ? 'loaded' : shownPrice == null ? 'empty' : 'stale',
    observedAt: quote ? new Date(quote.quoteTime * 1000).toISOString() : null,
    rows: [{ price: shownPrice, changePct: change, ...(quote ?? {}) }],
    metadata: { status: live.status, source: quote ? 'yahoo_stream' : 'cached', pending } });

  const formattedPrice =
    shownPrice == null
      ? '—'
      : shownPrice.toLocaleString(undefined, {
          ...(currency && /^[A-Z]{3}$/.test(currency) ? { style: 'currency', currency } : {}),
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        });
  return (
    <div className="tw-livequote" style={{ opacity: pending ? 0.5 : 1 }}>
      <div className="tw-assetbar__quote">
        <span className="tw-livequote__label">{quote ? 'Last' : 'Cached'}</span>
        <span className="tw-assetbar__price">{formattedPrice}</span>
        <span className="tw-assetbar__change" style={{ color: toneHex(toneOf(change)) }}>
          {signedPct(change, 2)}
        </span>
      </div>
      <div className="tw-livequote__meta" aria-live="off">
        <span title="Yahoo streaming quote; may be delayed. Historical candles and completed-candle alerts are unchanged.">
          {LABELS[live.status]}
        </span>
        {quote && (
          <>
            <span>{quote.marketHours}</span>
            <time dateTime={new Date(quote.quoteTime * 1000).toISOString()} title={timestamp ?? undefined}>
              {new Date(quote.quoteTime * 1000).toLocaleTimeString()}
            </time>
            <span title="Yahoo-reported cumulative day volume, not volume for the displayed chart interval. Missing volume is not zero.">
              Day vol{' '}
              {quote.dayVolume == null ? '—' : quote.dayVolume.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 })}
            </span>
          </>
        )}
        {(live.status === 'unavailable' || live.status === 'paused') && !pending && (
          <button type="button" onClick={live.retry}>
            Retry stream
          </button>
        )}
      </div>
    </div>
  );
}
