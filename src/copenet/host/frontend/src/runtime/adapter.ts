import { useEffect, useMemo, useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import type { SessionRunRecord, SessionStateRecord } from '../types/backend';
import {
  getArtifactById,
  getArtifacts,
  getBatchById as getMockBatchById,
  getWorkingSet,
} from './mocks';
import type {
  ActivityBundle,
  ActivityReadBatch,
  ActivityToolCall,
  Artifact,
  RunActivity,
  WorkingSet,
} from './types';

export type ResourceStatus = 'loading' | 'ready' | 'empty' | 'error';

export interface AsyncResource<T> {
  status: ResourceStatus;
  data: T | null;
  error: string | null;
}

export type BatchResource = ActivityReadBatch | ActivityBundle;

function ready<T>(data: T): AsyncResource<T> {
  return { status: 'ready', data, error: null };
}

function empty<T>(): AsyncResource<T> {
  return { status: 'empty', data: null, error: null };
}

function errored<T>(message: string): AsyncResource<T> {
  return { status: 'error', data: null, error: message };
}

function loading<T>(): AsyncResource<T> {
  return { status: 'loading', data: null, error: null };
}

function useSyncResource<T>(factory: () => AsyncResource<T>, deps: ReadonlyArray<unknown>): AsyncResource<T> {
  return useMemo(factory, deps);
}

export function useWorkingSet(sessionKey: string | null): AsyncResource<WorkingSet> {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const [resource, setResource] = useState<AsyncResource<WorkingSet>>(sessionKey ? loading() : empty());

  useEffect(() => {
    if (!sessionKey) {
      setResource(empty());
      return;
    }

    let cancelled = false;
    setResource(loading());
    void Promise.all([
      wsClient.resolveSessionState(sessionKey),
      wsClient.listSessionRuns(sessionKey, 1),
    ])
      .then(([state, runs]) => {
        if (cancelled) return;
        if (state) {
          setResource(ready(mapSessionStateToWorkingSet(state, runs[0] ?? null, activeRunId)));
          return;
        }
        setResource(ready(withRuntimeStatus(getWorkingSet(sessionKey), activeRunId)));
      })
      .catch((error) => {
        if (!cancelled) setResource(errored(error instanceof Error ? error.message : String(error)));
      });

    return () => {
      cancelled = true;
    };
  }, [activeRunId, sessionKey]);

  return resource;
}

export function useArtifacts(sessionKey: string | null): AsyncResource<Artifact[]> {
  return useSyncResource(() => {
    if (!sessionKey) return empty();
    try {
      const artifacts = getArtifacts(sessionKey);
      return artifacts.length === 0 ? empty() : ready(artifacts);
    } catch (error) {
      return errored(String(error));
    }
  }, [sessionKey]);
}

export function useArtifact(sessionKey: string | null, id: string | null): AsyncResource<Artifact> {
  return useSyncResource(() => {
    if (!sessionKey || !id) return empty();
    try {
      const artifact = getArtifactById(sessionKey, id);
      return artifact ? ready(artifact) : empty();
    } catch (error) {
      return errored(String(error));
    }
  }, [sessionKey, id]);
}

export function useRunActivity(sessionKey: string | null): AsyncResource<RunActivity> {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const sessionUpdatedAt = useAppStore(
    (state) => state.sessions.find((session) => session.key === sessionKey)?.updatedAt || null,
  );
  const [resource, setResource] = useState<AsyncResource<RunActivity>>(sessionKey ? loading() : empty());

  useEffect(() => {
    if (!sessionKey) {
      setResource(empty());
      return;
    }

    let cancelled = false;
    setResource(loading());
    void wsClient
      .listSessionRuns(sessionKey, 10)
      .then((runs) => {
        if (cancelled) return;
        if (runs.length === 0) {
          setResource(empty());
          return;
        }
        setResource(ready(mapRunToActivity(runs[runs.length - 1])));
      })
      .catch((error) => {
        if (!cancelled) setResource(errored(error instanceof Error ? error.message : String(error)));
      });

    return () => {
      cancelled = true;
    };
  }, [activeRunId, sessionKey, sessionUpdatedAt]);

  return resource;
}

export function useBatch(sessionKey: string | null, id: string | null): AsyncResource<BatchResource> {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const sessionUpdatedAt = useAppStore(
    (state) => state.sessions.find((session) => session.key === sessionKey)?.updatedAt || null,
  );
  const [resource, setResource] = useState<AsyncResource<BatchResource>>(sessionKey && id ? loading() : empty());

  useEffect(() => {
    if (!sessionKey || !id) {
      setResource(empty());
      return;
    }

    let cancelled = false;
    setResource(loading());
    void wsClient
      .listSessionRuns(sessionKey, 10)
      .then((runs) => {
        if (cancelled) return;
        const activity = [...runs].reverse().map(mapRunToActivity);
        for (const run of activity) {
          for (const item of run.items) {
            if ((item.kind === 'read_batch' || item.kind === 'bundle') && item.id === id) {
              setResource(ready(item));
              return;
            }
          }
        }
        const fallback = getMockBatchById(sessionKey, id);
        setResource(fallback ? ready(fallback) : empty());
      })
      .catch((error) => {
        if (!cancelled) setResource(errored(error instanceof Error ? error.message : String(error)));
      });

    return () => {
      cancelled = true;
    };
  }, [activeRunId, sessionKey, sessionUpdatedAt, id]);

  return resource;
}

function mapRunToActivity(run: SessionRunRecord): RunActivity {
  const calls = run.toolSteps.map((step, index) => mapToolStep(run, step, index));
  const items: RunActivity['items'] = [];

  if (calls.length > 1) {
    items.push({
      id: `batch-${run.runId}`,
      kind: 'read_batch',
      label: compactLabel(run.userMessage),
      at: run.startedAt,
      calls,
      mergedSummary: run.outputSummary || undefined,
    });
  } else if (calls.length === 1) {
    items.push(calls[0]);
  }

  if (run.outputSummary) {
    items.push({
      id: `note-${run.runId}`,
      kind: 'note',
      at: run.completedAt || run.startedAt,
      text: run.outputSummary,
    });
  }

  return {
    runId: run.runId,
    startedAt: run.startedAt,
    endedAt: run.completedAt,
    items,
  };
}

function mapToolStep(run: SessionRunRecord, step: SessionRunRecord['toolSteps'][number], index: number): ActivityToolCall {
  return {
    id: `${run.runId}-tool-${index}`,
    kind: 'tool_call',
    toolId: step.toolId,
    summary: step.summary,
    ok: step.ok,
    durationMs: 0,
    at: run.completedAt || run.startedAt,
  };
}

function compactLabel(text: string): string {
  const compact = text.trim();
  if (compact.length <= 56) return compact;
  return `${compact.slice(0, 53)}...`;
}

function mapSessionStateToWorkingSet(
  state: SessionStateRecord,
  run: SessionRunRecord | null,
  activeRunId: string | null,
): WorkingSet {
  return {
    taskSummary: state.task_summary?.trim() || run?.userMessage?.trim() || 'Session runtime state',
    status: activeRunId && run?.runId === activeRunId ? 'thinking' : 'awaiting_input',
    updatedAt: state.updated_at || run?.completedAt || run?.startedAt || new Date().toISOString(),
    entities: state.active_entities.map((value, index) => ({
      id: `entity-${index}`,
      kind: inferEntityKind(value),
      label: value,
    })),
    constraints: state.constraints.map((value, index) => ({
      id: `constraint-${index}`,
      text: value,
      severity: 'block',
    })),
    questions: state.unresolved_questions.map((value, index) => ({
      id: `question-${index}`,
      text: value,
    })),
    referencedArtifactIds: state.relevant_artifact_ids,
  };
}

function withRuntimeStatus(workingSet: WorkingSet, activeRunId: string | null): WorkingSet {
  return {
    ...workingSet,
    status: activeRunId ? 'thinking' : 'awaiting_input',
  };
}

function inferEntityKind(value: string): WorkingSet['entities'][number]['kind'] {
  if (value.includes('/') || value.endsWith('.py') || value.endsWith('.ts') || value.endsWith('.tsx') || value.endsWith('.md')) {
    return 'file';
  }
  if (value.includes('.')) return 'symbol';
  return 'note';
}
