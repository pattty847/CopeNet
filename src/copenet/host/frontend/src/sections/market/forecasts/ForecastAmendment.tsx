import { useRef, useState } from 'react';
import { safeUUID } from '../../../lib/wsNormalizers';
import { wsClient } from '../../../lib/wsClient';
import { forecastSetup, type ForecastRecord } from './types';

export function ForecastAmendment({ record, onSaved }: { record: ForecastRecord; onSaved: (record: ForecastRecord) => void }) {
  const original = forecastSetup(record);
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState(String(original?.entry.price ?? ''));
  const [stop, setStop] = useState(String(original?.stop ?? ''));
  const [targets, setTargets] = useState(original?.targets.map((target) => ({ ...target })) ?? []);
  const [rationale, setRationale] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<{ body: string; id: string } | null>(null);
  if (!original) return null;
  const save = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const changes = { entry: { ...original.entry, price: Number(entry) }, stop: Number(stop), targets };
      const body = JSON.stringify({ changes, rationale });
      if (pending.current?.body !== body) pending.current = { body, id: safeUUID() };
      const result = await wsClient.marketForecast.amend(record.forecastId, record.revision, {
        amendmentId: pending.current.id, rationale, changes,
      });
      onSaved(result.forecast); setOpen(false); pending.current = null;
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not record amendment.'); }
    finally { setBusy(false); }
  };
  return <>
    <button type="button" className="tw-btn" onClick={() => setOpen(!open)}>{open ? 'Close amendment' : 'Record an amendment'}</button>
    {open && <form onSubmit={(event) => { event.preventDefault(); void save(); }} className="cf-amendment">
      <p>This records your revision separately. Original chart levels and original model scores continue unchanged.</p>
      <label>Entry · original price basis<input className="tw-input" type="number" step="any" min="0.000000001" required value={entry} onChange={(event) => setEntry(event.target.value)} /></label>
      <label>Stop loss<input className="tw-input" type="number" step="any" min="0.000000001" required value={stop} onChange={(event) => setStop(event.target.value)} /></label>
      {targets.map((target, index) => <div className="mm-monitor-fields" key={index}>
        <label>Target {index + 1}<input className="tw-input" type="number" step="any" min="0.000000001" required value={target.price} onChange={(event) => setTargets((current) => current.map((row, at) => at === index ? { ...row, price: Number(event.target.value) } : row))} /></label>
        <label>Exit fraction<input className="tw-input" type="number" step="any" min="0.000000001" max="1" required value={target.fraction} onChange={(event) => setTargets((current) => current.map((row, at) => at === index ? { ...row, fraction: Number(event.target.value) } : row))} /></label>
      </div>)}
      <label>Reason<textarea className="tw-input" required maxLength={4000} rows={3} value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
      {error && <p className="mm-monitor-error" role="alert">{error}</p>}
      <button type="submit" className="tw-btn" disabled={busy}>{busy ? 'Recording…' : 'Record operator amendment'}</button>
    </form>}
  </>;
}
