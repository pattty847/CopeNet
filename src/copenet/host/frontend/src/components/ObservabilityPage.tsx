import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Bug, RefreshCw } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import type { ObservabilityRunDetail, ObservabilitySettings, SessionRunRecord } from '../types/backend';
import { RunInspector } from './observability/RunInspector';
import { RunListPane } from './observability/RunListPane';

const RUN_LOOKBACK_PER_SESSION = 30;
const REFRESH_MS = 12_000;

function initialSelection(): { runId: string | null; sessionKey: string | null } {
  const params = new URLSearchParams(window.location.search);
  return { runId: params.get('run'), sessionKey: params.get('session') };
}

export function ObservabilityPage() {
  const sessions = useAppStore((state) => state.sessions);
  const activeSessions = useMemo(() => sessions.filter((session) => !session.archived), [sessions]);
  const initial = useMemo(initialSelection, []);
  const [runs, setRuns] = useState<SessionRunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initial.runId);
  const [selectedSessionKey, setSelectedSessionKey] = useState<string | null>(initial.sessionKey);
  const [detail, setDetail] = useState<ObservabilityRunDetail | null>(null);
  const [settings, setSettings] = useState<ObservabilitySettings | null>(null);
  const [query, setQuery] = useState('');
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number | null>(null);

  const loadRuns = useCallback(async () => {
    if (activeSessions.length === 0) {
      setRuns([]);
      setLastFetch(Date.now());
      return;
    }
    setLoadingRuns(true);
    try {
      const results = await Promise.all(
        activeSessions.map((session) => wsClient.listSessionRuns(session.key, RUN_LOOKBACK_PER_SESSION).catch(() => [])),
      );
      const merged = results.flat().sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime());
      setRuns(merged);
      setLastFetch(Date.now());
      setSelectedRunId((currentRunId) => {
        if (currentRunId || !merged[0]) return currentRunId;
        setSelectedSessionKey(merged[0].sessionKey);
        return merged[0].runId;
      });
    } finally {
      setLoadingRuns(false);
    }
  }, [activeSessions]);

  useEffect(() => {
    void loadRuns();
    const timer = window.setInterval(() => void loadRuns(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [loadRuns]);

  useEffect(() => {
    wsClient.getObservabilitySettings().then(setSettings).catch((reason) => {
      setError(reason instanceof Error ? reason.message : 'Could not load trace settings.');
    });
  }, []);

  useEffect(() => {
    if (!selectedRunId || !selectedSessionKey) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    setError(null);
    wsClient.getObservabilityRun(selectedSessionKey, selectedRunId)
      .then((value) => {
        if (!cancelled) setDetail(value);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load this run.');
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => { cancelled = true; };
  }, [selectedRunId, selectedSessionKey]);

  const selectRun = (run: SessionRunRecord) => {
    setSelectedRunId(run.runId);
    setSelectedSessionKey(run.sessionKey);
    const url = new URL(window.location.href);
    url.searchParams.set('run', run.runId);
    url.searchParams.set('session', run.sessionKey);
    window.history.replaceState({}, '', url);
  };

  const toggleDebugCapture = async () => {
    if (!settings || savingSettings) return;
    setSavingSettings(true);
    setError(null);
    try {
      setSettings(await wsClient.updateObservabilitySettings(!settings.debugCapture));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update Debug capture.');
    } finally {
      setSavingSettings(false);
    }
  };

  const stats = useMemo(() => {
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const recent = runs.filter((run) => new Date(run.startedAt).getTime() >= dayAgo);
    return {
      runs: recent.length,
      tools: recent.reduce((count, run) => count + run.toolSteps.length, 0),
      errors: recent.filter((run) => run.error || run.status === 'error' || run.status === 'failed').length,
    };
  }, [runs]);

  return (
    <div className="animate-fade-in-up space-y-3">
      <header className="flex flex-col gap-3 border-b border-shell-border pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-shell-accent" />
            <h1 className="text-[16px] font-semibold text-shell-text">Run inspector</h1>
          </div>
          <p className="mt-1 text-[11px] text-shell-muted">
            {stats.runs} runs · {stats.tools} tool calls · {stats.errors} errors in the last 24 hours
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {settings?.debugCapture && (
            <span className="rounded-md bg-amber-400/10 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-amber-300">
              subsequent runs captured locally
            </span>
          )}
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(settings?.debugCapture)}
            onClick={toggleDebugCapture}
            disabled={!settings || savingSettings}
            className={`focus-ring inline-flex h-8 items-center gap-2 rounded-lg border px-3 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              settings?.debugCapture
                ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
                : 'border-shell-border bg-shell-panel text-shell-muted hover:text-shell-text'
            }`}
            title="Capture sanitized prompts, tool schemas, reasoning summaries, and raw run events for subsequent runs"
          >
            <Bug className="h-3.5 w-3.5" />
            Debug capture {settings?.debugCapture ? 'on' : 'off'}
          </button>
          <button
            type="button"
            onClick={() => void loadRuns()}
            className="focus-ring inline-flex h-8 items-center gap-2 rounded-lg border border-shell-border bg-shell-panel px-3 text-[11px] text-shell-muted transition-colors hover:text-shell-text"
            title={lastFetch ? `Last refreshed ${new Date(lastFetch).toLocaleTimeString()}` : 'Refresh runs'}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingRuns ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {error && !loadingDetail && (
        <div role="alert" className="rounded-lg border border-shell-error/30 bg-shell-error/5 px-3 py-2 text-[11px] text-shell-error">
          {error}
        </div>
      )}

      <section className="grid min-h-[34rem] overflow-hidden rounded-xl border border-shell-border bg-shell-panel shadow-shell lg:grid-cols-[20rem_minmax(0,1fr)]">
        <RunListPane
          runs={runs}
          sessions={activeSessions}
          selectedRunId={selectedRunId}
          loading={loadingRuns}
          query={query}
          onQueryChange={setQuery}
          onSelect={selectRun}
        />
        <RunInspector detail={detail} loading={loadingDetail} error={error} />
      </section>
    </div>
  );
}
