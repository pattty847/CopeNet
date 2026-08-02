/**
 * The InspectorDrawer's view of one turn's internals.
 *
 * Loads the run record and its lifecycle trace on open — not before, because
 * most turns are never inspected — and renders the shared `RunInternalsBody`.
 *
 * `showDid` is false here: the thread already lists every tool call as its own
 * row directly above, so repeating them inside the overlay is the redundancy
 * this whole restructure exists to remove. The Observability inspector, which
 * has no such rows, still renders it.
 */

import { useEffect, useState } from 'react';
import type { ObservabilityTraceEvent, SessionArtifactRecord, SessionRunRecord } from '../../types/backend';
import { buildRunInternals } from '../../runtime/runInternals';
import { loadRunDetail } from '../../runtime/runIndex';
import { RunInternalsBody } from './RunInternals';

interface Loaded {
  run: SessionRunRecord | null;
  events: ObservabilityTraceEvent[];
  artifacts: SessionArtifactRecord[];
}

export function RunInternalsDrawerBody({ sessionKey, runId }: { sessionKey: string; runId: string }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadRunDetail(sessionKey, runId).then((detail) => {
      if (cancelled) return;
      setLoaded({
        run: detail?.run || null,
        events: detail?.events || [],
        artifacts: detail?.artifacts || [],
      });
    });
    return () => {
      cancelled = true;
    };
  }, [sessionKey, runId]);

  if (!loaded) {
    return <p className="px-4 py-8 text-center text-[12px] text-operator-muted">Loading run internals…</p>;
  }
  if (!loaded.run) {
    return (
      <p className="px-4 py-8 text-center text-[12px] text-operator-muted">
        No durable record for this run. It may have been archived, or the run never completed.
      </p>
    );
  }

  return (
    <div className="px-4 py-4">
      <RunInternalsBody
        internals={buildRunInternals(loaded.run, loaded.events)}
        artifacts={loaded.artifacts}
        palette="operator"
        showDid={false}
        traceStatus={loaded.events.length > 0 ? 'loaded' : 'absent'}
      />
    </div>
  );
}
