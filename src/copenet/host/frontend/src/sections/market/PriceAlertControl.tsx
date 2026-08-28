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
    <div style={{ position: 'relative' }}>
      <button
        ref={triggerRef}
        type="button"
        className="market-price-alert-trigger"
        onClick={start}
        aria-expanded={open}
        aria-label={alerts.length ? `${alerts.length} active price alert${alerts.length === 1 ? '' : 's'}` : 'Add price alert'}
        title={alerts.length ? `${alerts.length} active price alert${alerts.length === 1 ? '' : 's'}` : 'Add price alert'}
        style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${alerts.length ? 'rgba(251,148,35,.35)' : MM.border}`, background: alerts.length ? MM.accentSoft : '#050506', color: alerts.length ? MM.accent : MM.muted, borderRadius: 8, padding: '6px 9px', font: '600 10px Inter' }}
      >
        <Bell size={12} />
        <span className="market-price-alert-trigger__label">{alerts.length ? `${alerts.length} alert${alerts.length === 1 ? '' : 's'}` : 'Add alert'}</span>
        {alerts.length > 0 && <span className="market-price-alert-trigger__count">{alerts.length}</span>}
      </button>
      <MarketFloatingPopover anchorRef={triggerRef} open={open} onClose={close} className="market-price-alert-popover" width={320} dismissOnOutside={false}>
        <div style={{ border: `1px solid ${MM.borderHi}`, borderRadius: 12, background: '#0b0b0d', padding: 12, boxShadow: '0 18px 36px rgba(0,0,0,.55)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ font: '700 9px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent }}>Daily-close price alert</span>
            <button type="button" onClick={close} aria-label="Close price alerts" style={{ border: 0, background: 'transparent', color: MM.dim, cursor: 'pointer', padding: 2 }}><X size={13} /></button>
          </div>
          <button type="button" onClick={onStartPlacing} style={{ width: '100%', cursor: 'crosshair', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, border: `1px solid ${placing ? MM.accent : MM.border}`, background: placing ? MM.accentSoft : 'rgba(254,252,244,.02)', color: placing ? MM.accent : MM.textSoft, borderRadius: 8, padding: '8px 10px', font: '600 10.5px Inter' }}>
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
                style={{ minWidth: 0, border: `1px solid ${MM.border}`, background: '#050506', color: MM.text, borderRadius: 7, padding: '7px 8px', fontFamily: mono, fontSize: 11 }}
              />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 9, color: MM.dim }}>
              Trigger when
              <select value={direction} onChange={(event) => setDirection(event.target.value as 'above' | 'below')} style={{ border: `1px solid ${MM.border}`, background: '#050506', color: MM.textSoft, borderRadius: 7, padding: '7px 8px', fontSize: 10 }}>
                <option value="above">Closes above</option>
                <option value="below">Closes below</option>
              </select>
            </label>
          </div>
          {error && <div role="alert" style={{ marginTop: 7, fontSize: 9.5, color: MM.down }}>{error}</div>}
          <button type="button" onClick={() => void save()} disabled={loading || !valid} style={{ width: '100%', marginTop: 9, cursor: loading || !valid ? 'default' : 'pointer', border: 0, borderRadius: 8, padding: '8px 10px', background: MM.accent, color: '#1a1205', font: '700 10px Inter', opacity: loading || !valid ? .45 : 1 }}>
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
      </MarketFloatingPopover>
    </div>
  );
}
