/**
 * runIndex — one run-record fetch per session, shared by every turn that needs it.
 *
 * The in-thread internals line renders under *every* assistant message, so a
 * naive `useEffect` fetch per bubble would issue one `sessions.runs` call per
 * turn on every render pass. A module-level promise cache keyed by
 * (sessionKey, revision) collapses those to one; the revision changes when a run
 * starts or finishes, which is exactly when the records change.
 *
 * Trace events are fetched separately and only on expand — they are the
 * expensive part, and most turns are never expanded.
 *
 * This also replaces `useRunActivity`'s fetch-ten-render-one: that hook asked for
 * 10 runs and rendered `runs[runs.length - 1]`, discarding nine.
 */

import { useEffect, useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import type { ObservabilityRunDetail, SessionRunRecord } from '../types/backend';

const RUN_LOOKBACK = 60;

export interface SessionRunIndex {
  byRunId: Map<string, SessionRunRecord>;
  ordered: SessionRunRecord[];
  latest: SessionRunRecord | null;
}

const EMPTY_INDEX: SessionRunIndex = { byRunId: new Map(), ordered: [], latest: null };

const runIndexCache = new Map<string, Promise<SessionRunIndex>>();
const runDetailCache = new Map<string, Promise<ObservabilityRunDetail | null>>();

function buildIndex(runs: SessionRunRecord[]): SessionRunIndex {
  const ordered = [...runs].sort(
    (a, b) => new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime(),
  );
  return {
    byRunId: new Map(ordered.map((run) => [run.runId, run])),
    ordered,
    latest: ordered[ordered.length - 1] || null,
  };
}

function loadRunIndex(sessionKey: string, revision: string): Promise<SessionRunIndex> {
  const key = `${sessionKey}::${revision}`;
  const cached = runIndexCache.get(key);
  if (cached) return cached;
  const pending = wsClient
    .listSessionRuns(sessionKey, RUN_LOOKBACK)
    .then(buildIndex)
    .catch(() => EMPTY_INDEX);
  runIndexCache.set(key, pending);
  // Only the newest revision of a session is ever read again; drop the rest so a
  // long session does not accumulate one cached index per run.
  for (const existing of [...runIndexCache.keys()]) {
    if (existing !== key && existing.startsWith(`${sessionKey}::`)) runIndexCache.delete(existing);
  }
  return pending;
}

/** A run's trace/artifact detail. Cached forever per runId — a finished run's
 *  trace never changes, and the cache is per page load. */
export function loadRunDetail(sessionKey: string, runId: string): Promise<ObservabilityRunDetail | null> {
  const cached = runDetailCache.get(runId);
  if (cached) return cached;
  const pending = wsClient.getObservabilityRun(sessionKey, runId).catch(() => null);
  runDetailCache.set(runId, pending);
  return pending;
}

/** Test/reset seam — the caches are module state, so a purge has to clear them. */
export function clearRunCaches(): void {
  runIndexCache.clear();
  runDetailCache.clear();
}

export function useSessionRunIndex(sessionKey: string | null): SessionRunIndex {
  const activeRunId = useAppStore((state) => (sessionKey ? state.activeRunsBySession[sessionKey] || null : null));
  const sessionUpdatedAt = useAppStore(
    (state) => state.sessions.find((session) => session.key === sessionKey)?.updatedAt || null,
  );
  const [index, setIndex] = useState<SessionRunIndex>(EMPTY_INDEX);

  useEffect(() => {
    if (!sessionKey) {
      setIndex(EMPTY_INDEX);
      return;
    }
    let cancelled = false;
    void loadRunIndex(sessionKey, `${activeRunId || 'idle'}:${sessionUpdatedAt || ''}`).then((value) => {
      if (!cancelled) setIndex(value);
    });
    return () => {
      cancelled = true;
    };
  }, [sessionKey, activeRunId, sessionUpdatedAt]);

  return index;
}
