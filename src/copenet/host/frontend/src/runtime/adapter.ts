// Runtime data adapter — single entry point for every runtime UI surface.
//
// Components never import mocks directly. They call the hooks here, and the
// hooks delegate to a swappable RuntimeSource. Today that source returns
// mocked data synchronously; when the backend lands, replace `mockSource` (or
// call `setRuntimeSource(...)`) with an RPC-backed source and the components
// light up untouched.
//
// Shape is deliberately small:
//   AsyncResource<T> -> { status, data, error }
// Components fan out to four render branches (loading/empty/error/ready).
// The adapter never throws — it catches and returns an error resource.

import { useMemo } from 'react';
import {
  getArtifactById,
  getArtifacts,
  getBatchById,
  getRunActivity,
  getWorkingSet,
} from './mocks';
import type {
  ActivityBundle,
  ActivityReadBatch,
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

export interface RuntimeSource {
  workingSet(sessionKey: string | null): AsyncResource<WorkingSet>;
  artifacts(sessionKey: string | null): AsyncResource<Artifact[]>;
  artifact(sessionKey: string | null, id: string | null): AsyncResource<Artifact>;
  runActivity(sessionKey: string | null): AsyncResource<RunActivity>;
  batch(sessionKey: string | null, id: string | null): AsyncResource<BatchResource>;
}

// Default source: reads from the mocked dataset. Synchronous — status is
// always one of ready/empty/error, never loading. When a backend source
// lands, loading states start flowing naturally and the components are
// already wired for them.
const mockSource: RuntimeSource = {
  workingSet(sessionKey) {
    if (!sessionKey) return empty();
    try {
      return ready(getWorkingSet(sessionKey));
    } catch (e) {
      return errored(String(e));
    }
  },
  artifacts(sessionKey) {
    if (!sessionKey) return empty();
    try {
      const data = getArtifacts(sessionKey);
      return data.length === 0 ? empty() : ready(data);
    } catch (e) {
      return errored(String(e));
    }
  },
  artifact(sessionKey, id) {
    if (!sessionKey || !id) return empty();
    try {
      const data = getArtifactById(sessionKey, id);
      return data ? ready(data) : empty();
    } catch (e) {
      return errored(String(e));
    }
  },
  runActivity(sessionKey) {
    if (!sessionKey) return empty();
    try {
      const data = getRunActivity(sessionKey);
      return data.items.length === 0 ? empty() : ready(data);
    } catch (e) {
      return errored(String(e));
    }
  },
  batch(sessionKey, id) {
    if (!sessionKey || !id) return empty();
    try {
      const data = getBatchById(sessionKey, id);
      return data ? ready(data) : empty();
    } catch (e) {
      return errored(String(e));
    }
  },
};

let currentSource: RuntimeSource = mockSource;

// Swap the runtime source. Intended for backend wiring later, or for tests
// that want to inject loading/error states.
export function setRuntimeSource(source: RuntimeSource): void {
  currentSource = source;
}

export function getRuntimeSource(): RuntimeSource {
  return currentSource;
}

// Hooks — all memoized on the session key (and id where relevant). These
// are the only things components should import from the runtime layer.

export function useWorkingSet(sessionKey: string | null): AsyncResource<WorkingSet> {
  return useMemo(() => currentSource.workingSet(sessionKey), [sessionKey]);
}

export function useArtifacts(sessionKey: string | null): AsyncResource<Artifact[]> {
  return useMemo(() => currentSource.artifacts(sessionKey), [sessionKey]);
}

export function useArtifact(
  sessionKey: string | null,
  id: string | null,
): AsyncResource<Artifact> {
  return useMemo(() => currentSource.artifact(sessionKey, id), [sessionKey, id]);
}

export function useRunActivity(sessionKey: string | null): AsyncResource<RunActivity> {
  return useMemo(() => currentSource.runActivity(sessionKey), [sessionKey]);
}

export function useBatch(
  sessionKey: string | null,
  id: string | null,
): AsyncResource<BatchResource> {
  return useMemo(() => currentSource.batch(sessionKey, id), [sessionKey, id]);
}
