/**
 * TurnInternals — the in-thread mount of the shared internals view.
 *
 * Renders one muted line beneath an assistant turn and expands it in place. The
 * run record comes from the session-wide index (one fetch, shared); the trace is
 * fetched only when the operator expands, because most turns never are.
 *
 * Renders nothing while the turn has no run record or is still streaming — a
 * draft, an optimistic bubble, or the in-flight run. That is deliberate: the
 * plan's hard rule is no layout shift during a live run, so the line appears
 * once, after the run lands, and never mid-stream.
 */

import { useEffect, useState } from 'react';
import type { ObservabilityTraceEvent, SessionArtifactRecord } from '../../types/backend';
import { buildRunInternals } from '../../runtime/runInternals';
import { loadRunDetail, useSessionRunIndex } from '../../runtime/runIndex';
import { useAppStore } from '../../store/useAppStore';
import { RunInternalsPanel } from './RunInternals';

interface LoadedDetail {
  events: ObservabilityTraceEvent[];
  artifacts: SessionArtifactRecord[];
}

export function TurnInternals({ sessionKey, runId }: { sessionKey: string | null; runId: string | null }) {
  const index = useSessionRunIndex(sessionKey);
  const activeRunId = useAppStore((state) => (sessionKey ? state.activeRunsBySession[sessionKey] || null : null));
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<LoadedDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!expanded || !sessionKey || !runId || detail) return;
    let cancelled = false;
    setLoading(true);
    void loadRunDetail(sessionKey, runId)
      .then((value) => {
        if (cancelled) return;
        setDetail({ events: value?.events || [], artifacts: value?.artifacts || [] });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, sessionKey, runId, detail]);

  const run = runId ? index.byRunId.get(runId) || null : null;
  if (!run || activeRunId === runId) return null;

  return (
    <RunInternalsPanel
      internals={buildRunInternals(run, detail?.events || [])}
      artifacts={detail?.artifacts}
      traceStatus={detail ? (detail.events.length > 0 ? 'loaded' : 'absent') : 'loading'}
      palette="operator"
      expanded={expanded}
      onToggle={() => setExpanded((value) => !value)}
      loading={loading}
    />
  );
}
