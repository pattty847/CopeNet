import { ArrowLeft, RefreshCw, Star } from 'lucide-react';
import type { AssetProfile } from './assetProfile';
import { signedPct, toneHex, toneOf } from './workspaceViz';
import type { TickerDetailPayload } from './types';

export function TickerAssetBar({
  detail,
  profile,
  watched,
  watchBusy,
  pending,
  onBack,
  onToggleWatch,
  onOpenPosition,
}: {
  detail: TickerDetailPayload;
  profile: AssetProfile;
  watched: boolean;
  watchBusy: boolean;
  /** The symbol being fetched while this asset stays on screen, or null. */
  pending: string | null;
  onBack: () => void;
  onToggleWatch: () => void;
  onOpenPosition: () => void;
}) {
  const change = detail.quote.changePct;
  const position = detail.intelligence?.portfolio;

  return (
    <header className="tw-assetbar">
      <button type="button" className="tw-iconbtn" onClick={onBack} title="Back to Market" aria-label="Back to Market">
        <ArrowLeft size={14} />
      </button>

      <div className="tw-assetbar__identity">
        <h1 className="tw-assetbar__symbol">{detail.symbol}</h1>
        {detail.name.trim().toUpperCase() !== detail.symbol.toUpperCase() && (
          <span className="tw-assetbar__name">{detail.name}</span>
        )}
        <span className="tw-assetbar__kind">{profile.label}</span>
        {/* Keeping the previous asset painted is only honest if the operator can see that a
            different one is on its way. */}
        {pending && (
          <span className="tw-assetbar__pending" role="status">
            <RefreshCw size={10} className="tw-spin" aria-hidden="true" /> {pending}
          </span>
        )}
      </div>

      <button
        type="button"
        className="tw-iconbtn"
        onClick={onToggleWatch}
        disabled={watchBusy}
        aria-pressed={watched}
        title={watched ? 'Remove from watchlist' : 'Add to watchlist'}
        aria-label={watched ? 'Remove from watchlist' : 'Add to watchlist'}
      >
        {watchBusy ? <RefreshCw size={13} className="tw-spin" /> : <Star size={13} fill={watched ? 'currentColor' : 'none'} />}
      </button>

      <div className="tw-assetbar__spacer" />

      {/* A position changes how every other number here reads, so it is permanent when it
          exists and absent when it does not. */}
      {position && (
        <button type="button" className="tw-position-chip" onClick={onOpenPosition} title="Open position detail">
          <span>Held</span>
          <span className="tw-position-chip__pnl" style={{ color: toneHex(toneOf(position.pnlPct)) }}>{signedPct(position.pnlPct)}</span>
          <span className="tw-position-chip__pnl" style={{ opacity: 0.75 }}>{signedPct(position.allocationPct)} wt</span>
        </button>
      )}

      <div className="tw-assetbar__quote" style={{ opacity: pending ? 0.5 : 1, transition: 'opacity .12s ease' }}>
        <span className="tw-assetbar__price">
          {detail.quote.price == null
            ? '—'
            : detail.quote.price.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 })}
        </span>
        <span className="tw-assetbar__change" style={{ color: toneHex(toneOf(change)) }}>{signedPct(change, 2)}</span>
      </div>
    </header>
  );
}
