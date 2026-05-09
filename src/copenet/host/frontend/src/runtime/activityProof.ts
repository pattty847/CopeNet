import type { SessionRunRecord } from '../types/backend';
import type {
  ActivityItem,
  ActivityNote,
  ActivityProofGroup,
  ActivityProofGroupKind,
  ActivityProofMember,
  ActivityToolCall,
  Artifact,
  RunActivity,
} from './types';

function compactLabel(text: string): string {
  const compact = text.trim();
  if (compact.length <= 56) return compact;
  return `${compact.slice(0, 53)}...`;
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
    artifactId: step.artifactId ?? null,
    target: step.target ?? null,
    workspaceRoot:
      step.workspaceRoot ??
      (typeof run.metadata?.workspaceRoot === 'string' ? run.metadata.workspaceRoot : null),
    scope: step.scope ?? null,
    accessAction: step.accessAction ?? null,
    policyDecision: step.policyDecision ?? null,
    policySummary: step.policySummary ?? null,
    error: step.error ?? null,
  };
}

function previewSummary(preview: SessionRunRecord['toolSteps'][number]['members'][number]['preview'] | undefined): string | null {
  if (!preview) return null;
  if (preview.type === 'file_read') {
    const lines = Array.isArray(preview.lines) ? preview.lines.filter((line) => typeof line === 'string') : [];
    return lines.length > 0 ? lines.join('\n') : null;
  }
  if (preview.type === 'repo_search') {
    const matches = Array.isArray(preview.matches) ? preview.matches : [];
    if (matches.length === 0) return null;
    return matches
      .map((match) => `${match.path}:${match.line} ${match.snippet}`)
      .join('\n');
  }
  return preview.text || null;
}

function expandRunStep(run: SessionRunRecord, step: SessionRunRecord['toolSteps'][number], index: number): ActivityToolCall[] {
  const members = Array.isArray(step.members) ? step.members : [];
  if (step.toolId !== 'tool.batch' || members.length === 0) {
    return [mapToolStep(run, step, index)];
  }
  return members.map((member, memberIndex) => ({
    id: `${run.runId}-tool-${index}-member-${memberIndex}`,
    kind: 'tool_call',
    toolId: member.toolId,
    summary: member.summary,
    ok: member.ok,
    durationMs: 0,
    at: run.completedAt || run.startedAt,
    artifactId: member.artifactId ?? null,
    target: member.target ?? null,
    workspaceRoot:
      member.workspaceRoot ??
      step.workspaceRoot ??
      (typeof run.metadata?.workspaceRoot === 'string' ? run.metadata.workspaceRoot : null),
    scope: member.scope ?? null,
    accessAction: member.accessAction ?? null,
    policyDecision: member.policyDecision ?? null,
    policySummary: member.policySummary ?? null,
    error: member.error ?? null,
    preview: previewSummary(member.preview),
  }));
}

function groupStatus(call: ActivityToolCall): ActivityProofMember['status'] {
  if (call.ok) return 'success';
  return call.policyDecision === 'write_blocked' || call.policyDecision === 'approval_required' ? 'blocked' : 'failed';
}

function isFileReadCall(call: ActivityToolCall): boolean {
  if (call.accessAction === 'read') return true;
  return /(read|grep|search|list)/i.test(call.toolId);
}

function isFileEditCall(call: ActivityToolCall): boolean {
  if (call.accessAction === 'write') return true;
  return /(edit|write|patch|apply)/i.test(call.toolId);
}

function isSkillCall(call: ActivityToolCall): boolean {
  return /^skill\./i.test(call.toolId) || /^context\./i.test(call.toolId);
}

function isArtifactCall(call: ActivityToolCall): boolean {
  return /^artifact\./i.test(call.toolId);
}

function groupKindForCall(call: ActivityToolCall): ActivityProofGroupKind {
  if (isArtifactCall(call)) return 'artifacts';
  if (isFileEditCall(call)) return 'files_edited';
  if (isFileReadCall(call)) return 'files_read';
  if (isSkillCall(call)) return 'skills';
  return 'commands';
}

function memberLabel(call: ActivityToolCall): string {
  return call.target || call.summary || call.toolId;
}

function memberDetail(call: ActivityToolCall): string | undefined {
  if (call.target && call.summary && call.summary !== call.target) return call.summary;
  return call.policySummary || call.error || undefined;
}

function formatArtifactCount(count: number): string {
  return count === 1 ? 'Produced 1 artifact' : `Produced ${count} artifacts`;
}

function labelForGroup(kind: ActivityProofGroupKind, count: number): string {
  if (kind === 'commands') return count === 1 ? 'Ran 1 command' : `Ran ${count} commands`;
  if (kind === 'files_read') return count === 1 ? 'Read 1 file' : `Read ${count} files`;
  if (kind === 'files_edited') return count === 1 ? 'Edited 1 file' : `Edited ${count} files`;
  if (kind === 'skills') return count === 1 ? 'Used 1 skill' : `Used ${count} skills`;
  return formatArtifactCount(count);
}

function artifactMember(artifact: Artifact): ActivityProofMember {
  const fileCount = artifact.files?.length ?? 0;
  const changeSummary =
    fileCount > 0
      ? `${fileCount} ${fileCount === 1 ? 'file' : 'files'} · +${artifact.files?.reduce((sum, file) => sum + file.additions, 0) ?? 0} / -${artifact.files?.reduce((sum, file) => sum + file.deletions, 0) ?? 0}`
      : artifact.oneLine;
  return {
    id: `artifact-${artifact.id}`,
    label: artifact.title,
    detail: changeSummary,
    status: 'success',
    artifactId: artifact.id,
    artifactKind: artifact.kind,
    additions: artifact.files?.reduce((sum, file) => sum + file.additions, 0) ?? null,
    deletions: artifact.files?.reduce((sum, file) => sum + file.deletions, 0) ?? null,
    fileCount: fileCount || null,
  };
}

function callsToGroup(run: SessionRunRecord, kind: ActivityProofGroupKind, calls: ActivityToolCall[]): ActivityProofGroup {
  return {
    id: `${run.runId}-${kind}`,
    kind: 'proof_group',
    group: kind,
    label: labelForGroup(kind, calls.length),
    at: calls[0]?.at || run.startedAt,
    summary: calls.length === 1 ? calls[0]?.summary : undefined,
    members: calls.map((call) => ({
      id: call.id,
      label: memberLabel(call),
      detail: memberDetail(call),
      status: groupStatus(call),
      toolId: call.toolId,
      target: call.target ?? null,
      artifactId: call.artifactId ?? null,
      outputPreview: call.summary,
      fullOutput: call.error ?? call.policySummary ?? call.preview ?? null,
      additions: null,
      deletions: null,
      fileCount: null,
      artifactKind: isArtifactCall(call) ? 'summary' : null,
    })),
  };
}

function artifactsToGroup(run: SessionRunRecord, artifacts: Artifact[]): ActivityProofGroup {
  return {
    id: `${run.runId}-artifacts`,
    kind: 'proof_group',
    group: 'artifacts',
    label: formatArtifactCount(artifacts.length),
    at: artifacts[0]?.producedAt || run.completedAt || run.startedAt,
    summary: artifacts.length === 1 ? artifacts[0]?.oneLine : undefined,
    members: artifacts.map(artifactMember),
  };
}

export function mapRunToActivity(run: SessionRunRecord, artifacts: Artifact[] = []): RunActivity {
  const calls = run.toolSteps.flatMap((step, index) => expandRunStep(run, step, index));
  const groups = new Map<ActivityProofGroupKind, ActivityToolCall[]>();
  const order: ActivityProofGroupKind[] = [];

  for (const call of calls) {
    const kind = groupKindForCall(call);
    if (!groups.has(kind)) {
      groups.set(kind, []);
      order.push(kind);
    }
    groups.get(kind)!.push(call);
  }

  const items: ActivityItem[] = order.map((kind) => callsToGroup(run, kind, groups.get(kind) || []));

  const runArtifacts = artifacts.filter((artifact) => artifact.runId === run.runId);
  if (runArtifacts.length > 0) {
    items.push(artifactsToGroup(run, runArtifacts));
  }

  if (run.outputSummary) {
    const note: ActivityNote = {
      id: `note-${run.runId}`,
      kind: 'note',
      at: run.completedAt || run.startedAt,
      text: run.outputSummary,
    };
    items.push(note);
  }

  if (items.length === 0 && run.userMessage) {
    items.push({
      id: `note-empty-${run.runId}`,
      kind: 'note',
      at: run.startedAt,
      text: compactLabel(run.userMessage),
    });
  }

  return {
    runId: run.runId,
    startedAt: run.startedAt,
    endedAt: run.completedAt,
    items,
  };
}
