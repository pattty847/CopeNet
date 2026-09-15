import { useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { timeLabel } from './model';
import type { AlertRehearsal as Rehearsal, AlertRule } from './types';

export function AlertRehearsal({ rule }: { rule: AlertRule }) {
  const [result, setResult] = useState<{ key: string; value: Rehearsal } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = JSON.stringify(rule);
  const current = result?.key === key ? result.value : null;
  const rehearse = async () => {
    setBusy(true); setError('');
    try {
      const value = await wsClient.marketMonitoring.rehearseAlert(rule) as Rehearsal;
      setResult({ key, value });
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  return <section>
    <button type="button" className="tw-btn" disabled={busy} onClick={() => void rehearse()}>{busy ? 'Checking history…' : 'Rehearse on cached history'}</button>
    {error && <p className="mm-monitor-error" role="alert">{error}</p>}
    {current && <div className="mm-monitor-readback" aria-live="polite">
      <b>{current.matchCount} historical matches · {current.candles} eligible candles</b>
      {current.error && <span>{current.error}</span>}
      <small>{current.note}</small>
      {current.cacheUpdatedAt && <small>Cache refreshed {timeLabel(current.cacheUpdatedAt)}</small>}
      {current.matches.length > 0 && <details><summary>Recent matches</summary>
        {current.matches.slice(0, 20).map((match) => <p key={match.t}>
          {timeLabel(match.candleCloseAt)} · {match.phase.replaceAll('_', ' ')} · {match.leftValue.toFixed(2)} vs {match.rightValue.toFixed(2)}
        </p>)}
      </details>}
    </div>}
  </section>;
}
