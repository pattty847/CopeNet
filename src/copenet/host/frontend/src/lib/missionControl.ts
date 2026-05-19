import type { ApprovalRequest, Session, SessionRunRecord, SessionStateRecord } from '../types/backend';

export type MissionControlLane =
  | 'needs_attention'
  | 'recently_useful'
  | 'ready_to_continue'
  | 'promote_to_workflow';

export type MissionControlKind =
  | 'approval'
  | 'active_run'
  | 'failed_run'
  | 'useful_run'
  | 'resume_session'
  | 'workflow_candidate';

export interface MissionControlItem {
  id: string;
  lane: MissionControlLane;
  kind: MissionControlKind;
  title: string;
  detail: string;
  source: string;
  meta: string;
  sessionKey: string;
  runId: string | null;
  provider: string;
  model: string | null;
  at: string;
}

export interface MissionControlInput {
  sessions: Session[];
  sessionStates: Record<string, SessionStateRecord>;
  runsBySession: Record<string, SessionRunRecord[]>;
  approvals: ApprovalRequest[];
  now?: string;
}

const LANE_ORDER: Record<MissionControlLane, number> = {
  needs_attention: 0,
  recently_useful: 1,
  ready_to_continue: 2,
  promote_to_workflow: 3,
};

function sessionTitle(session: Session): string {
  return session.title?.trim() || session.key || 'Untitled session';
}

function isRunError(run: SessionRunRecord): boolean {
  return Boolean(run.error) || run.status === 'error' || run.status === 'failed';
}

function latestRun(runs: SessionRunRecord[]): SessionRunRecord | null {
  return [...runs].sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())[0] || null;
}

function formatAge(iso: string, now: Date): string {
  const then = new Date(iso);
  const diffMinutes = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 60_000));
  if (diffMinutes < 1) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const hours = Math.floor(diffMinutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function toolMeta(run: SessionRunRecord): string {
  const toolCount = run.toolSteps.length;
  const artifactCount = run.artifactIds.length;
  const toolLabel = `${toolCount} tool${toolCount === 1 ? '' : 's'}`;
  if (artifactCount === 0) return toolLabel;
  return `${toolLabel} · ${artifactCount} artifact${artifactCount === 1 ? '' : 's'}`;
}

function workflowCandidate(runs: SessionRunRecord[], state?: SessionStateRecord): boolean {
  const completedRuns = runs.filter((run) => !isRunError(run));
  const toolSteps = completedRuns.reduce((count, run) => count + run.toolSteps.length, 0);
  const hasReusableSummary = Boolean(state?.task_summary?.trim());
  return completedRuns.length >= 2 && toolSteps >= 4 && hasReusableSummary;
}

export function buildMissionControlItems(input: MissionControlInput): MissionControlItem[] {
  const now = new Date(input.now || new Date().toISOString());
  const activeSessions = input.sessions.filter((session) => !session.archived);
  const sessionByKey = new Map(activeSessions.map((session) => [session.key, session]));
  const items: MissionControlItem[] = [];

  for (const approval of input.approvals) {
    if (approval.status !== 'pending') continue;
    const session = sessionByKey.get(approval.sessionKey);
    if (!session) continue;
    items.push({
      id: `approval:${approval.approvalId}`,
      lane: 'needs_attention',
      kind: 'approval',
      title: `Approval needed: ${approval.toolId}`,
      detail: approval.proposedAction.description || approval.rationale || 'Review the pending action before the run can continue.',
      source: sessionTitle(session),
      meta: formatAge(approval.createdAt, now),
      sessionKey: session.key,
      runId: approval.runId,
      provider: session.provider,
      model: session.model,
      at: approval.createdAt,
    });
  }

  for (const session of activeSessions) {
    if (session.inFlightRunId) {
      items.push({
        id: `active:${session.key}:${session.inFlightRunId}`,
        lane: 'needs_attention',
        kind: 'active_run',
        title: `Run in progress: ${sessionTitle(session)}`,
        detail: 'This session is currently busy. Jump in to watch tool activity and the final answer.',
        source: sessionTitle(session),
        meta: session.model || session.provider,
        sessionKey: session.key,
        runId: session.inFlightRunId,
        provider: session.provider,
        model: session.model,
        at: session.updatedAt,
      });
    }

    const state = input.sessionStates[session.key];
    const runs = input.runsBySession[session.key] || [];
    const latest = latestRun(runs);
    const isWorkflowCandidate = workflowCandidate(runs, state);

    if (latest && isRunError(latest)) {
      items.push({
        id: `failed:${latest.runId}`,
        lane: 'needs_attention',
        kind: 'failed_run',
        title: `Run failed: ${sessionTitle(session)}`,
        detail: latest.error || latest.outputSummary || 'The latest run ended with an error.',
        source: sessionTitle(session),
        meta: formatAge(latest.completedAt || latest.startedAt, now),
        sessionKey: session.key,
        runId: latest.runId,
        provider: session.provider,
        model: session.model,
        at: latest.completedAt || latest.startedAt,
      });
    }

    if (isWorkflowCandidate) {
      items.push({
        id: `workflow:${session.key}`,
        lane: 'promote_to_workflow',
        kind: 'workflow_candidate',
        title: `Promote ${sessionTitle(session)}`,
        detail: state?.task_summary?.trim() || 'This session has enough repeated tool activity to become a workflow.',
        source: sessionTitle(session),
        meta: `${runs.length} runs · ${runs.reduce((count, run) => count + run.toolSteps.length, 0)} tools`,
        sessionKey: session.key,
        runId: latest?.runId || null,
        provider: session.provider,
        model: session.model,
        at: state?.updated_at || latest?.completedAt || latest?.startedAt || session.updatedAt,
      });
    } else if (latest && !isRunError(latest) && (latest.toolSteps.length >= 2 || latest.artifactIds.length > 0)) {
      items.push({
        id: `useful:${latest.runId}`,
        lane: 'recently_useful',
        kind: 'useful_run',
        title: latest.outputSummary?.trim() || `Useful run: ${sessionTitle(session)}`,
        detail: latest.userMessage || 'Recent run produced useful tool activity.',
        source: sessionTitle(session),
        meta: toolMeta(latest),
        sessionKey: session.key,
        runId: latest.runId,
        provider: session.provider,
        model: session.model,
        at: latest.completedAt || latest.startedAt,
      });
    }

    const updatedAt = state?.updated_at || session.updatedAt;
    const ageHours = (now.getTime() - new Date(updatedAt).getTime()) / 3_600_000;
    const openQuestion = state?.unresolved_questions.find((question) => question.trim());
    if (ageHours >= 8 && (openQuestion || state?.task_summary?.trim())) {
      items.push({
        id: `resume:${session.key}`,
        lane: 'ready_to_continue',
        kind: 'resume_session',
        title: `Resume ${sessionTitle(session)}`,
        detail: openQuestion || state?.task_summary?.trim() || 'This session is ready for another pass.',
        source: sessionTitle(session),
        meta: formatAge(updatedAt, now),
        sessionKey: session.key,
        runId: latest?.runId || null,
        provider: session.provider,
        model: session.model,
        at: updatedAt,
      });
    }
  }

  return items.sort((a, b) => {
    const laneDiff = LANE_ORDER[a.lane] - LANE_ORDER[b.lane];
    if (laneDiff !== 0) return laneDiff;
    return new Date(b.at).getTime() - new Date(a.at).getTime();
  });
}
