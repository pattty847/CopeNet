import type { SessionRunRecord } from '../types/backend';
import { normalizeToolResultPreview, type PreviewLimits } from '../lib/wsNormalizers';
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
    preview: previewSummary(step.preview),
    previewFullChars: previewFullChars(step.preview),
    arguments: step.arguments ?? null,
    argumentsTruncated: step.argumentsTruncated ?? null,
  };
}

/**
 * Budgets for the Inspect drawer. The inline transcript deliberately shows a
 * teaser; this is the "show me everything" surface, so it keeps whatever the
 * backend was willing to send. maxChars matches contracts.py's
 * INSPECTOR_INLINE_BODY_CHARS so nothing survives the wire only to be clipped here.
 */
const DRAWER_PREVIEW_LIMITS: PreviewLimits = {
  maxChars: 4000,
  maxLines: 2000,
  maxMatches: 200,
  maxResults: 50,
};

/**
 * Render a tool-result preview to inspectable text.
 *
 * Run-record previews arrive as the raw backend dict and MUST be normalized
 * first. contracts.py::_preview_payload tags diff/plan/web_search/web_doc but
 * sends files.read as a bare `{path, content}`, files.rg as `{matches}` whose
 * rows carry `text` (not `snippet`), and shell.exec/artifact.create as
 * `{preview}`. This function used to tag-dispatch the raw dict, so every one of
 * those fell through to null — file reads, searches, and shell commands, the
 * three most common calls, rendered blank in the drawer while the live inline
 * rows showed them fine (the WS path already normalized). Same normalizer here,
 * with drawer-sized budgets, closes that gap.
 */
function previewSummary(raw: unknown): string | null {
  const preview = normalizeToolResultPreview(raw, DRAWER_PREVIEW_LIMITS);
  if (!preview) return null;
  if (preview.type === 'file_read') {
    const lines = Array.isArray(preview.lines) ? preview.lines.filter((line) => typeof line === 'string') : [];
    return lines.length > 0 ? lines.join('\n') : null;
  }
  if (preview.type === 'repo_search') {
    const matches = Array.isArray(preview.matches) ? preview.matches : [];
    if (matches.length === 0) return null;
    return matches.map((match) => `${match.path}:${match.line} ${match.snippet}`).join('\n');
  }
  if (preview.type === 'diff') {
    return preview.diff || null;
  }
  if (preview.type === 'plan') {
    return preview.items.map((it) => `[${it.status === 'completed' ? 'x' : ' '}] ${it.content}`).join('\n') || null;
  }
  if (preview.type === 'web_search') {
    return preview.results.map((r) => `${r.title} — ${r.url}`).join('\n') || null;
  }
  if (preview.type === 'web_doc') {
    return preview.text || `${preview.title} (${preview.url})` || null;
  }
  return preview.text || null;
}

/**
 * True body length when the backend clipped a preview, so the drawer can say so.
 *
 * Reads the RAW payload on purpose: normalizeToolResultPreview's raw fallback
 * rebuilds `{type, text}` and drops fullChars/truncated along the way.
 */
function previewFullChars(raw: unknown): number | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  if (!payload.truncated) return null;
  return typeof payload.fullChars === 'number' ? payload.fullChars : null;
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
    previewFullChars: previewFullChars(member.preview),
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
      // On a failure the error is why the operator opened the drawer, so it leads.
      // On success the result body leads — policySummary is set on allowed calls
      // too ("Read stayed inside the home workspace"), and letting it win here hid
      // every successful result behind a policy note. It gets its own line instead.
      fullOutput: call.ok
        ? call.preview ?? call.policySummary ?? null
        : call.error ?? call.preview ?? call.policySummary ?? null,
      fullOutputChars: call.previewFullChars ?? null,
      policySummary: call.policySummary ?? null,
      arguments: call.arguments ?? null,
      argumentsTruncated: call.argumentsTruncated ?? null,
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
