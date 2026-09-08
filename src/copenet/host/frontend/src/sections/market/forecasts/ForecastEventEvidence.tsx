import { useState } from 'react';
import { wsClient } from '../../../lib/wsClient';

export function ForecastEventEvidence({ forecastId, evidenceId }: { forecastId: string; evidenceId: string }) {
  const [open, setOpen] = useState(false);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const inspect = async () => {
    setOpen(!open);
    if (open || evidence) return;
    setError('');
    try { setEvidence((await wsClient.marketForecast.evidence(forecastId, evidenceId)).evidence); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Evaluation evidence unavailable.'); }
  };
  return <div><button className="tw-btn" onClick={() => void inspect()}>{open ? 'Close' : 'Inspect'} evaluation evidence</button>
    {open && (error ? <p role="alert">{error}</p> : !evidence ? <p role="status">Loading evidence…</p> : <pre className="mm-monitor-json">{JSON.stringify(evidence, null, 2)}</pre>)}
  </div>;
}
