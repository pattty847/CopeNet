import { useEffect, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { ChartEvidence } from './types';

/** Lazy, bounded inspection of the immutable source behind an annotation. */
export function ChartEvidenceViewer({ reference, sessionKey, includeAccountContext, documentId }: {
  reference: ChartEvidence; sessionKey: string | null; includeAccountContext: boolean; documentId: string;
}) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<Awaited<ReturnType<typeof wsClient.marketChart.read>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setResult(null); setError(null);
    void wsClient.marketChart.read(sessionKey, reference, offset, includeAccountContext, documentId).then((next) => {
      if (active) setResult(next);
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : 'Evidence unavailable.'); });
    return () => { active = false; };
  }, [open, sessionKey, reference, offset, includeAccountContext, documentId]);
  return <div className="ca-source">
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Close' : 'Inspect'} {reference.resourceKey}</button>
    {open && <>
      <small>Observation {reference.observationId}</small>
      {error ? <p role="alert">{error}</p> : !result ? <p role="status">Loading captured evidence…</p> : <>
        <p>{result.label} · {result.rows.length ? `${offset + 1}–${offset + result.rows.length}` : '0'} of {result.matchedCount} matching rows</p>
        <pre tabIndex={0}>{JSON.stringify(result.rows, null, 2)}</pre>
        <div><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
          <button type="button" disabled={result.nextOffset == null} onClick={() => setOffset(result.nextOffset!)}>Next</button></div>
      </>}
    </>}
  </div>;
}
