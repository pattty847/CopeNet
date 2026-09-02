import { useEffect, useRef, useState } from 'react';
import { Bell, Crosshair, X } from 'lucide-react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import { MM, mono } from './marketUi';
import type { PriceAlert } from './types';

export function PriceAlertControl({
  alerts,
  currentPrice,
  pickedPrice,
  placing,
  loading,
  error,
  onStartPlacing,
  onStopPlacing,
  onCreate,
  onCancel,
  disabled = false,
}: {
  alerts: PriceAlert[];
  currentPrice: number;
  pickedPrice: number | null;
  placing: boolean;
  loading: boolean;
  error: string | null;
  onStartPlacing: () => void;
  onStopPlacing: () => void;
  onCreate: (direction: 'above' | 'below', threshold: number) => Promise<boolean>;
  onCancel: (alertId: string) => Promise<void>;
  /** Comparison rebases the price pane, so a price threshold has no meaning while it is on. */
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [thresholdText, setThresholdText] = useState('');
  const [direction, setDirection] = useState<'above' | 'below'>('above');
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (pickedPrice == null) return;
    setThresholdText(pickedPrice.toFixed(2));
    setDirection(pickedPrice >= currentPrice ? 'above' : 'below');
    setOpen(true);
  }, [pickedPrice, currentPrice]);

  const threshold = Number(thresholdText);
  const valid = Number.isFinite(threshold) && threshold > 0 && currentPrice > 0;
  const start = () => {
    setOpen(true);
    if (!alerts.length) onStartPlacing();
  };
  const close = () => {
    setOpen(false);
    onStopPlacing();
  };
  const save = async () => {
    if (!valid) return;
    if (await onCreate(direction, threshold)) {
      setThresholdText('');
      close();
    }
  };

  return (
    <div className="market-price-alert-control" style={{ position: 'relative' }}>
      <button
        ref={triggerRef}
        type="button"
        className="tw-iconbtn"
        onClick={start}
        aria-expanded={open}
        data-active={alerts.length > 0 || open}
        disabled={disabled}
        aria-label={alerts.length ? `${alerts.length} active price alert${alerts.length === 1 ? '' : 's'}` : 'Add price alert'}
        title={disabled ? 'Price alerts are price-anchored and unavailable while the chart is rebased for comparison.' : alerts.length ? `${alerts.length} active price alert${alerts.length === 1 ? '' : 's'}` : 'Add price alert'}
        style={{ position: 'relative' }}
      >
        <Bell size={14} />
        {alerts.length > 0 && (
          <span aria-hidden="true" className="tw-iconbtn__count">{alerts.length}</span>
        )}
      </button>
      <MarketFloatingPopover anchorRef={triggerRef} open={open} onClose={close} className="market-price-alert-popover" width={320} dismissOnOutside={false}>
        <div className="tw-pop">
          <div className="tw-pop__head">
            <div>
              <div className="tw-pop__title">Price alert</div>
              <div className="tw-pop__sub">Evaluated on the daily close after the morning sweep.</div>
            </div>
            <button type="button" className="tw-iconbtn" onClick={close} aria-label="Close price alerts"><X size={13} /></button>
          </div>
          <div className="tw-pop__body">
          <button type="button" className="tw-btn" data-active={placing} onClick={onStartPlacing} style={{ width: '100%', cursor: 'crosshair' }}>
            <Crosshair size={13} /> {placing ? 'Click a price level on the chart…' : 'Pick a level on the chart'}
          </button>
          {pickedPrice != null && <div role="status" style={{ marginTop: 7, color: MM.up, fontSize: 10 }}>Level selected at ${pickedPrice.toFixed(2)}. Review it below, then arm the alert.</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 112px', gap: 8, marginTop: 9 }}>
            <label style={{ display: 'grid', gap: 4, fontSize: 9, color: MM.dim }}>
              Price
              <input
                value={thresholdText}
                onChange={(event) => setThresholdText(event.target.value)}
                inputMode="decimal"
                placeholder={currentPrice ? currentPrice.toFixed(2) : '0.00'}
                className="tw-input"
                style={{ minWidth: 0 }}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 9, color: MM.dim }}>
              Trigger when
              <select value={direction} onChange={(event) => setDirection(event.target.value as 'above' | 'below')} className="tw-input" style={{ fontFamily: 'var(--mkt-sans)', fontSize: 10 }}>
                <option value="above">Closes above</option>
                <option value="below">Closes below</option>
              </select>
            </label>
          </div>
          {error && <div role="alert" style={{ marginTop: 7, fontSize: 9.5, color: MM.down }}>{error}</div>}
          <button type="button" className="tw-btn" onClick={() => void save()} disabled={loading || !valid} style={{ width: '100%', marginTop: 9, borderColor: 'var(--mkt-accent-line)', background: 'var(--mkt-accent-soft)', color: 'var(--mkt-accent)' }}>
            {loading ? (thresholdText ? 'Saving…' : 'Loading alerts…') : 'Arm one-shot alert'}
          </button>
          <div style={{ marginTop: 7, color: MM.dimmer, fontSize: 9, lineHeight: 1.4 }}>Evaluated after the unattended morning market sweep. A crossing creates a Pulse item.</div>
          {alerts.length > 0 && (
            <div style={{ marginTop: 10, borderTop: `1px solid ${MM.border}`, paddingTop: 8, display: 'grid', gap: 6 }}>
              {alerts.map((alert) => (
                <div key={alert.alertId} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ flex: 1, fontFamily: mono, fontSize: 10, color: MM.textSoft }}>{alert.direction === 'above' ? '≥' : '≤'} ${alert.threshold.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <button type="button" onClick={() => void onCancel(alert.alertId)} disabled={loading} style={{ cursor: loading ? 'default' : 'pointer', border: 0, background: 'transparent', color: MM.dim, fontSize: 9.5 }}>Cancel</button>
                </div>
              ))}
            </div>
          )}
          </div>
        </div>
      </MarketFloatingPopover>
    </div>
  );
}
