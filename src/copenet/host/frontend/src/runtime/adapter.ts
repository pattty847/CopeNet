import { useEffect, useMemo, useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import type { SessionArtifactRecord } from '../types/backend';
import { buildInboxItems } from './inboxItems';
import { mapRunToActivity } from './activityProof';
import type { InboxItem, LiveToolCall, MessageDestination, MessagingConfig, OutboundMessageRecord, PatProfile, ProfileChangelogItem, ProviderAuthStatus, PulseRecord, ReturnBriefingPayload, RunTimeline } from '../types/backend';
import type {
  ActivityBundle,
  ActivityReadBatch,
  ApprovalRequest,
  ApprovalOutcome,
  Artifact,
  RunActivity,
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

export function useArtifact(sessionKey: string | null, id: string | null): AsyncResource<Artifact> {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const sessionUpdatedAt = useAppStore(
    (state) => state.sessions.find((session) => session.key === sessionKey)?.updatedAt || null,
  );
  const [resource, setResource] = useState<AsyncResource<Artifact>>(sessionKey && id ? loading() : empty());

  useEffect(() => {
    if (!sessionKey || !id) {
      setResource(empty());
      return;
    }

    let cancelled = false;
    setResource(loading());
    void wsClient
      .listSessionArtifacts(sessionKey, 100)
      .then((records) => {
        if (cancelled) return;
        const record = records.find((item) => item.artifactId === id);
        setResource(record ? ready(mapSessionArtifact(record)) : empty());
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
        setResource(ready(mapRunToActivity(runs[runs.length - 1], [])));
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
        const activity = [...runs].reverse().map((run) => mapRunToActivity(run, []));
        for (const run of activity) {
          for (const item of run.items) {
            if ((item.kind === 'read_batch' || item.kind === 'bundle') && item.id === id) {
              setResource(ready(item));
              return;
            }
          }
        }
        setResource(empty());
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


function mapSessionArtifact(record: SessionArtifactRecord): Artifact {
  const normalizedKind = (() => {
    const kind = String(record.type || '').trim();
    if (kind === 'tool_output') return 'tool_bundle';
    if (
      kind === 'summary' ||
      kind === 'patch_plan' ||
      kind === 'answer' ||
      kind === 'tool_bundle' ||
      kind === 'diff' ||
      kind === 'approval_request' ||
      kind === 'outbound_message' ||
      kind === 'orchestration_run'
    ) {
      return kind;
    }
    return 'summary';
  })();
  const compactBody = String(record.body || '').trim();
  return {
    id: record.artifactId,
    kind: normalizedKind,
    title: record.title || 'Artifact',
    oneLine: compactBody ? compactBody.split('\n')[0].slice(0, 180) : 'Runtime artifact',
    producedAt: record.updatedAt || record.createdAt,
    runId: record.runId || null,
    bodyMarkdown: compactBody || undefined,
  };
}

// Returns the live pending approval from the store.
// Returns null when no real backend approval has been pushed.
export function usePendingApproval(_sessionKey: string | null): ApprovalRequest | null {
  return useAppStore((state) => state.pendingApproval);
}

// Returns the full approval history from the store.
// Empty until the backend pushes approval events for this session.
export function useApprovalHistory(_sessionKey: string | null): ApprovalRequest[] {
  return useAppStore((state) => state.approvalHistory);
}

// Returns the configured messaging destinations from the store.
// Empty until the backend pushes destination config.
export function useDestinations(): MessageDestination[] {
  return useAppStore((state) => state.destinations);
}

// ---------------------------------------------------------------------------
// Mock event/state transitions
// Lets UI demo components drive realistic state progressions without a backend.
// ---------------------------------------------------------------------------
export function useMockTransitions() {
  const setPendingApproval = useAppStore((s) => s.setPendingApproval);
  const resolveApproval = useAppStore((s) => s.resolveApproval);
  const upsertApprovalInHistory = useAppStore((s) => s.upsertApprovalInHistory);
  const setRunPausedReason = useAppStore((s) => s.setRunPausedReason);
  const setRightPanelTab = useAppStore((s) => s.setRightPanelTab);
  const setRightPanelOpen = useAppStore((s) => s.setRightPanelOpen);
  const resetComposer = useAppStore((s) => s.resetComposer);

  const simulateApprovalRequested = (partial?: Partial<ApprovalRequest>) => {
    const req: ApprovalRequest = {
      approvalId: `appr_sim_${Date.now()}`,
      runId: `run_sim_${Date.now()}`,
      sessionKey: '__fallback__',
      status: 'pending',
      actionClass: 'external_communication',
      toolId: 'send_message',
      proposedAction: {
        description: 'Send a message to the configured Telegram destination.',
        target: 'telegram:@copenet_ops',
        payload: { message: 'Simulated outbound message from demo transition.' },
      },
      rationale: 'Simulated approval request for demo purposes.',
      createdAt: new Date().toISOString(),
      resolvedAt: null,
      outcome: null,
      ...partial,
    };
    setPendingApproval(req);
    setRightPanelTab('approvals');
    setRightPanelOpen(true);
  };

  const simulateApprove = (approvalId: string, note?: string) => {
    const outcome: ApprovalOutcome = {
      decision: 'approved',
      note: note ?? null,
      decidedAt: new Date().toISOString(),
    };
    resolveApproval(approvalId, outcome); // optimistic local update
    void wsClient.decideApproval(approvalId, 'approved', note); // wake the parked run
  };

  const simulateReject = (approvalId: string, note?: string) => {
    const outcome: ApprovalOutcome = {
      decision: 'rejected',
      note: note ?? 'Rejected by operator',
      decidedAt: new Date().toISOString(),
    };
    resolveApproval(approvalId, outcome); // optimistic local update
    void wsClient.decideApproval(approvalId, 'rejected', note); // wake the parked run
  };

  const simulateModify = (approvalId: string, newMessage: string, note?: string) => {
    const outcome: ApprovalOutcome = {
      decision: 'modified',
      modifiedPayload: { message: newMessage },
      note: note ?? 'Operator modified message',
      decidedAt: new Date().toISOString(),
    };
    resolveApproval(approvalId, outcome);
  };

  const simulateRunResumed = () => {
    setRunPausedReason(null);
  };

  const simulateSendMessageComposed = (target: string, message: string): OutboundMessageRecord => {
    const dest = useAppStore.getState().destinations.find((d) => d.target === target);
    const needsApproval = dest?.requiresApproval ?? true;
    const record: OutboundMessageRecord = {
      messageId: `msg_sim_${Date.now()}`,
      runId: `run_sim_${Date.now()}`,
      sessionKey: '__fallback__',
      platform: target.split(':')[0],
      target,
      targetDisplayName: dest?.displayName ?? null,
      messageText: message,
      status: needsApproval ? 'pending_approval' : 'sent',
      approvalId: needsApproval ? `appr_sim_${Date.now()}` : null,
      sentAt: needsApproval ? null : new Date().toISOString(),
      failureReason: null,
      createdAt: new Date().toISOString(),
    };
    if (needsApproval) {
      simulateApprovalRequested({
        proposedAction: {
          description: `Send message to ${dest?.displayName ?? target}`,
          target,
          payload: { message },
        },
        approvalId: record.approvalId!,
      });
    }
    resetComposer();
    return record;
  };

  return {
    simulateApprovalRequested,
    simulateApprove,
    simulateReject,
    simulateModify,
    simulateRunResumed,
    simulateSendMessageComposed,
  };
}

// ---------------------------------------------------------------------------
// Pat Profile hooks — real store state only; null until backend ships
// ---------------------------------------------------------------------------

// Returns the active Pat Profile from the store.
// Null until the backend profile:loaded RPC fires.
export function usePatProfile(): PatProfile | null {
  return useAppStore((s) => s.patProfile);
}

// Returns the pending return briefing from the store.
// Null until the backend briefing:ready RPC fires (or dev trigger seeds it).
export function useReturnBriefing(): ReturnBriefingPayload | null {
  return useAppStore((s) => s.returnBriefing);
}

// Returns the profile changelog from the store.
// Empty until the backend pushes profile mutation events.
export function useProfileChangelog(): ProfileChangelogItem[] {
  return useAppStore((s) => s.profileChangelog);
}

// ---------------------------------------------------------------------------
// Returns a priority-ordered list of inbox items for the operator action center.
// Aggregates: paused run, pending approvals, recently resolved approvals.
// When the backend ships, replace buildInboxItems() with a real RPC call.
export function useInboxItems(sessionKey: string | null): InboxItem[] {
  const runPausedReason = useAppStore((s) => s.runPausedReason);
  const approvalHistory = useApprovalHistory(sessionKey);
  const pulses = useAppStore((s) => s.pulses);
  return useMemo(
    () => [...mapPulsesToInboxItems(pulses), ...buildInboxItems(approvalHistory, runPausedReason)],
    [approvalHistory, runPausedReason, pulses],
  );
}

// Returns the operator's messaging platform configuration from the store.
// Null until the backend pushes a real config.
export function useMessagingConfig(): MessagingConfig | null {
  return useAppStore((s) => s.messagingConfig);
}

// Returns the paused-run timeline for the current session.
// Populated by the backend when a run pauses; cleared when the run resumes.
export function useRunTimeline(_sessionKey: string | null): RunTimeline | null {
  const storeTimeline = useAppStore((s) => s.runTimeline);
  const runPausedReason = useAppStore((s) => s.runPausedReason);
  const setRunTimeline = useAppStore((s) => s.setRunTimeline);

  useEffect(() => {
    if (!runPausedReason) {
      // Clear timeline when run resumes so stale data doesn't persist
      setRunTimeline(null);
    }
  }, [runPausedReason, setRunTimeline]);

  return storeTimeline;
}

function mapPulsesToInboxItems(pulses: PulseRecord[]): InboxItem[] {
  return pulses.map((pulse) => ({
    id: `pulse:${pulse.pulseId}`,
    priority: 'attention',
    kind: 'pulse',
    title: pulse.title,
    subtitle: pulse.whyNow,
    createdAt: pulse.createdAt,
    sessionKey: pulse.sourceSessionKeys[0] || '__pulse__',
    runId: pulse.sourceRunIds[0] || null,
    pulseData: pulse,
  }));
}

// ---------------------------------------------------------------------------
// Phase 4 hooks — live tool activity, turn state, provider auth
// ---------------------------------------------------------------------------

// Returns live tool calls streaming in during the active run.
// Populated by wsClient from toolExecution payloads on delta/final events.
// Empty when no run is active (components should switch to RunActivityPanel).
export function useLiveToolCalls(): LiveToolCall[] {
  return useAppStore((s) => s.liveToolCalls);
}

// Returns the auth status for a provider, fetching from the backend on mount.
// Backend required: provider.auth.status RPC.
// Falls back to a typed null when RPC is unavailable.
export function useProviderAuth(providerId: string | null): {
  status: ProviderAuthStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const stored = useAppStore((s) => (providerId ? s.providerAuthStatuses[providerId] ?? null : null));
  const setStatus = useAppStore((s) => s.setProviderAuthStatus);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = () => {
    if (!providerId) return;
    setLoading(true);
    setError(null);
    wsClient
      .providerAuthStatus(providerId)
      .then((s) => {
        setStatus(providerId, s);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  };

  useEffect(() => {
    if (providerId && !stored) fetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId]);

  return { status: stored, loading, error, refresh: fetch };
}
