// Realistic mocked runtime data for the Agents UI surfaces.
//
// These mocks are scoped by session key so different sessions show
// different content, making the demo feel alive. Replace with real backend
// data once the runtime endpoints land — the UI already reads these through
// the helpers below, so only the helpers need rewiring.

import type { InboxItem, MessageDestination, MessagingConfig, OrchestrationRun, RunTimeline } from '../types/backend';
import type {
  Artifact,
  ApprovalRequest,
  RunActivity,
  WorkingSet,
} from './types';

const FALLBACK_KEY = '__fallback__';

const workingSetByKey: Record<string, WorkingSet> = {
  [FALLBACK_KEY]: {
    taskSummary: 'Investigate why harness_planned fires before provider init in long-running sessions.',
    status: 'thinking',
    updatedAt: new Date(Date.now() - 1000 * 42).toISOString(),
    entities: [
      { id: 'e1', kind: 'file', label: 'src/copenet/core/orchestrator/runtime.py', detail: '~420 LOC · last touched today' },
      { id: 'e2', kind: 'symbol', label: 'Harness.plan_turn', detail: 'async · plans capability + tool loop' },
      { id: 'e3', kind: 'file', label: 'src/copenet/providers/lm_studio.py' },
      { id: 'e4', kind: 'note', label: 'Trace run 2b1a-9e4f shows provider init fired after harness_planned' },
    ],
    constraints: [
      { id: 'c1', text: 'Do not change session locking semantics', severity: 'block' },
      { id: 'c2', text: 'Preserve append-only transcript guarantee', severity: 'block' },
      { id: 'c3', text: 'Keep tool-loop gating on promptedToolUse', severity: 'info' },
    ],
    questions: [
      { id: 'q1', text: 'Is provider init idempotent across re-entrant plan calls?' },
      { id: 'q2', text: 'Should harness defer planning until provider signals ready?' },
    ],
    referencedArtifactIds: ['a-patch-1', 'a-summary-1'],
  },
};

const artifactsByKey: Record<string, Artifact[]> = {
  [FALLBACK_KEY]: [
    {
      id: 'a-patch-1',
      kind: 'patch_plan',
      title: 'Defer harness planning until provider init resolves',
      oneLine: '3 files · +42 / −18 · gated by capability probe',
      producedAt: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
      runId: 'run_2b1a9e4f',
      files: [
        { path: 'src/copenet/core/orchestrator/runtime.py', additions: 24, deletions: 11 },
        { path: 'src/copenet/core/harness/planner.py', additions: 14, deletions: 5 },
        { path: 'tests/integration/test_tool_prompt_matrix.py', additions: 4, deletions: 2 },
      ],
      diffBlocks: [
        {
          path: 'src/copenet/core/orchestrator/runtime.py',
          hunkHeader: '@@ -180,12 +180,18 @@ async def plan_turn',
          lines: [
            { kind: 'ctx', text: 'async def plan_turn(self, turn: Turn) -> HarnessPlan:' },
            { kind: 'ctx', text: '    capability = self._capability_profile()' },
            { kind: 'remove', text: '    return self._build_plan(turn, capability)' },
            { kind: 'add', text: '    if not self._provider_ready:' },
            { kind: 'add', text: '        await self._await_provider_ready()' },
            { kind: 'add', text: '    return self._build_plan(turn, capability)' },
          ],
        },
        {
          path: 'src/copenet/core/harness/planner.py',
          hunkHeader: '@@ -52,6 +52,12 @@ class Planner',
          lines: [
            { kind: 'ctx', text: 'class Planner:' },
            { kind: 'ctx', text: '    def __init__(self, capability: CapabilityProfile) -> None:' },
            { kind: 'add', text: '        self._deferred_turns: list[Turn] = []' },
            { kind: 'ctx', text: '        self.capability = capability' },
          ],
        },
      ],
    },
    {
      id: 'a-summary-1',
      kind: 'summary',
      title: 'Root cause: provider init races harness planner',
      oneLine: 'Capability probe reads stale client before lm_studio resolver completes',
      producedAt: new Date(Date.now() - 1000 * 60 * 11).toISOString(),
      runId: 'run_2b1a9e4f',
      bodyMarkdown:
        'Harness currently calls `_capability_profile()` synchronously inside `plan_turn`. ' +
        'When LM Studio is still performing its model manifest probe, the capability block ' +
        'falls back to a generic default — which in turn sets `promptedToolUse: false`, ' +
        'and the tool loop never arms.\n\n' +
        '**Fix shape:** gate `plan_turn` behind `_provider_ready` and re-probe capability ' +
        'once the provider resolves. Add a deterministic fake-provider test that simulates ' +
        'slow resolve and asserts `willAttemptToolLoop === true`.',
    },
    {
      id: 'a-answer-1',
      kind: 'answer',
      title: 'Yes — `providers.list` is the right gate, not `availableToolIds`',
      oneLine: 'Answer drafted for user; 1 citation attached',
      producedAt: new Date(Date.now() - 1000 * 60 * 17).toISOString(),
      runId: 'run_2b1a9e4f',
      bodyMarkdown:
        'The gate is `harness_planned.capabilityProfile.promptedToolUse`. ' +
        '`availableToolIds` only lists declared handlers; it does not decide whether the ' +
        'current provider/model combo will actually be prompted for tool use.',
    },
    {
      id: 'a-bundle-1',
      kind: 'tool_bundle',
      title: 'Orchestrator + harness read bundle',
      oneLine: '6 safe reads merged · 412 lines scanned',
      producedAt: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
      runId: 'run_2b1a9e4f',
      toolIds: ['fs.read_file', 'fs.grep', 'fs.read_file', 'fs.grep', 'fs.read_file', 'fs.read_file'],
    },
    {
      id: 'a-approval-1',
      kind: 'approval_request',
      title: 'Approval required: send message to Telegram',
      oneLine: 'Agent wants to send a summary to @copenet_ops · awaiting your decision',
      producedAt: new Date(Date.now() - 1000 * 45).toISOString(),
      runId: 'run_2b1a9e4f',
      approvalData: {
        approvalId: 'appr_c3d9f1a2',
        runId: 'run_2b1a9e4f',
        sessionKey: '__fallback__',
        status: 'pending',
        actionClass: 'external_communication',
        toolId: 'send_message',
        proposedAction: {
          description: 'Send a run summary to the configured Telegram destination.',
          target: 'telegram:@copenet_ops',
          payload: {
            message:
              'Run complete: provider init race fixed.\n\nPatch plan drafted (3 files, +42/−18). Gated on capability probe. Ready for operator review.',
          },
        },
        rationale:
          'User asked to send results to Telegram when the investigation finishes. Run has produced a patch plan and summary artifact.',
        createdAt: new Date(Date.now() - 1000 * 45).toISOString(),
        resolvedAt: null,
        outcome: null,
      },
    },
    {
      id: 'a-outbound-1',
      kind: 'outbound_message',
      title: 'Message sent → Telegram @copenet_ops',
      oneLine: 'Delivered · 47 chars · approved by operator',
      producedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
      runId: 'run_prev_4f91cc01',
      outboundData: {
        messageId: 'msg_8a2e19f0',
        runId: 'run_prev_4f91cc01',
        sessionKey: '__fallback__',
        platform: 'telegram',
        target: 'telegram:@copenet_ops',
        targetDisplayName: '@copenet_ops',
        messageText: 'Harness investigation complete. No regressions found in the tool-loop probe suite.',
        status: 'sent',
        approvalId: 'appr_prev_aa11bb22',
        sentAt: new Date(Date.now() - 1000 * 60 * 29).toISOString(),
        failureReason: null,
        createdAt: new Date(Date.now() - 1000 * 60 * 31).toISOString(),
      },
    },
    {
      id: 'a-orch-1',
      kind: 'orchestration_run',
      title: 'Probe analysis: grounding distribution',
      oneLine: 'Completed · 8 tool calls · 4.2s',
      producedAt: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
      runId: 'run_2b1a9e4f',
      orchestrationData: {
        orchestrationId: 'orch_e7a1b2c3',
        runId: 'run_2b1a9e4f',
        sessionKey: '__fallback__',
        status: 'completed',
        goal: 'Scan all probe outputs, count grounded successes, and summarize the distribution across repo-explain and patch-plan tasks.',
        scriptSummary: 'Search for probe output files, read each, tally grounded vs listing-only outcomes.',
        toolsUsed: [
          { toolId: 'files.search', count: 3, summary: 'probe output paths → 12 files found' },
          { toolId: 'files.read', count: 4, summary: 'probe run data → 412 lines scanned' },
          { toolId: 'context.prepare', count: 1, summary: 'session/repo overview' },
        ],
        toolBudget: 10,
        toolCallsUsed: 8,
        timeoutSeconds: 30,
        durationMs: 4212,
        outputSummary: '3 of 8 repo-explain probes are now grounded via files.read. 5 others remain listing-only. patch-plan probes: 2/4 grounded, 2/4 shallow. Improvement vs baseline confirmed.',
        relatedArtifactIds: ['a-summary-1'],
        approvalRequired: false,
        approvalId: null,
        startedAt: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
        completedAt: new Date(Date.now() - 1000 * 60 * 18 + 4212).toISOString(),
        error: null,
      } as OrchestrationRun,
    },
  ],
};

const runActivityByKey: Record<string, RunActivity> = {
  [FALLBACK_KEY]: {
    runId: 'run_2b1a9e4f',
    startedAt: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
    endedAt: null,
    items: [
      {
        id: 'act-1',
        kind: 'read_batch',
        label: 'Survey orchestrator + harness',
        at: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
        calls: [
          { id: 'c1', kind: 'tool_call', toolId: 'fs.read_file', summary: 'runtime.py (420 lines)', ok: true, durationMs: 14, at: '' },
          { id: 'c2', kind: 'tool_call', toolId: 'fs.grep', summary: 'plan_turn usages → 7 hits', ok: true, durationMs: 23, at: '' },
          { id: 'c3', kind: 'tool_call', toolId: 'fs.read_file', summary: 'planner.py (192 lines)', ok: true, durationMs: 9, at: '' },
          { id: 'c4', kind: 'tool_call', toolId: 'fs.grep', summary: '_provider_ready → 3 hits', ok: true, durationMs: 12, at: '' },
        ],
        mergedSummary: 'Provider init runs lazily on first send; planner does not await it.',
      },
      {
        id: 'act-2',
        kind: 'bundle',
        label: 'Gather capability probe traces',
        at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
        calls: [
          { id: 'c5', kind: 'tool_call', toolId: 'trace.read', summary: 'run 2b1a-9e4f events', ok: true, durationMs: 31, at: '' },
          { id: 'c6', kind: 'tool_call', toolId: 'trace.read', summary: 'run 4f91-cc01 events', ok: true, durationMs: 28, at: '' },
        ],
        producedArtifactId: 'a-summary-1',
      },
      {
        id: 'act-3',
        kind: 'tool_call',
        toolId: 'code.edit',
        summary: 'Drafted 3-file patch plan (see artifact)',
        ok: true,
        durationMs: 182,
        at: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
      },
      {
        id: 'act-4',
        kind: 'note',
        at: new Date(Date.now() - 1000 * 60 * 1).toISOString(),
        text: 'Awaiting operator review on the patch plan before applying.',
      },
      {
        id: 'act-5',
        kind: 'tool_call',
        toolId: 'send_message',
        summary: 'Requested to send run summary to telegram:@copenet_ops — awaiting approval',
        ok: true,
        durationMs: 8,
        at: new Date(Date.now() - 1000 * 45).toISOString(),
      },
    ],
  },
};

function resolveKey<T>(map: Record<string, T>, sessionKey: string | null): T {
  if (sessionKey && map[sessionKey]) return map[sessionKey];
  return map[FALLBACK_KEY];
}

export function getWorkingSet(sessionKey: string | null): WorkingSet {
  return resolveKey(workingSetByKey, sessionKey);
}

export function getArtifacts(sessionKey: string | null): Artifact[] {
  return resolveKey(artifactsByKey, sessionKey);
}

export function getArtifactById(sessionKey: string | null, id: string): Artifact | null {
  return getArtifacts(sessionKey).find((a) => a.id === id) ?? null;
}

export function getRunActivity(sessionKey: string | null): RunActivity {
  return resolveKey(runActivityByKey, sessionKey);
}

export function getBatchById(sessionKey: string | null, id: string) {
  const activity = getRunActivity(sessionKey);
  for (const item of activity.items) {
    if ((item.kind === 'read_batch' || item.kind === 'bundle') && item.id === id) {
      return item;
    }
  }
  return null;
}

export function getMockPendingApproval(sessionKey: string | null): ApprovalRequest | null {
  const artifacts = resolveKey(artifactsByKey, sessionKey);
  const artifact = artifacts.find((a) => a.kind === 'approval_request' && a.approvalData?.status === 'pending');
  return artifact?.approvalData ?? null;
}

// ---------------------------------------------------------------------------
// Approval history — resolved entries from previous runs/sessions
// ---------------------------------------------------------------------------

export const MOCK_APPROVAL_HISTORY: ApprovalRequest[] = [
  // Current pending (will be overridden by the pending entry in artifactsByKey for the live session)
  {
    approvalId: 'appr_c3d9f1a2',
    runId: 'run_2b1a9e4f',
    sessionKey: '__fallback__',
    status: 'pending',
    actionClass: 'external_communication',
    toolId: 'send_message',
    proposedAction: {
      description: 'Send a run summary to the configured Telegram destination.',
      target: 'telegram:@copenet_ops',
      payload: {
        message:
          'Run complete: provider init race fixed.\n\nPatch plan drafted (3 files, +42/−18). Gated on capability probe. Ready for operator review.',
      },
    },
    rationale: 'User asked to send results to Telegram when the investigation finishes.',
    createdAt: new Date(Date.now() - 1000 * 45).toISOString(),
    resolvedAt: null,
    outcome: null,
  },
  // Modified — operator rewrote the message before sending
  {
    approvalId: 'appr_bb77ee11',
    runId: 'run_4a3c8d12',
    sessionKey: '__fallback__',
    status: 'modified',
    actionClass: 'external_communication',
    toolId: 'send_message',
    proposedAction: {
      description: 'Send probe results to Telegram after tool-loop regression run.',
      target: 'telegram:@copenet_ops',
      payload: {
        message:
          'Regression probe complete. 3 of 8 repo-explain probes now use files.read as primary grounding. Previous: 1 of 8.',
      },
    },
    rationale: 'Probe run completed; user asked for a summary to be sent.',
    createdAt: new Date(Date.now() - 1000 * 60 * 73).toISOString(),
    resolvedAt: new Date(Date.now() - 1000 * 60 * 72).toISOString(),
    outcome: {
      decision: 'modified',
      modifiedPayload: {
        message: 'Probe done. 3/8 repo-explain probes now grounded. Improvement vs baseline.',
      },
      note: 'Shortened message before sending',
      decidedAt: new Date(Date.now() - 1000 * 60 * 72).toISOString(),
    },
  },
  // Approved — no changes
  {
    approvalId: 'appr_aa55cc99',
    runId: 'run_prev_4f91cc01',
    sessionKey: '__fallback__',
    status: 'approved',
    actionClass: 'external_communication',
    toolId: 'send_message',
    proposedAction: {
      description: 'Send harness investigation summary to Telegram.',
      target: 'telegram:@copenet_ops',
      payload: {
        message: 'Harness investigation complete. No regressions found in the tool-loop probe suite.',
      },
    },
    rationale: 'Investigation session finished. User requested notification on completion.',
    createdAt: new Date(Date.now() - 1000 * 60 * 31).toISOString(),
    resolvedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    outcome: {
      decision: 'approved',
      note: null,
      decidedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    },
  },
  // Rejected — operator decided not to send
  {
    approvalId: 'appr_dd22ff88',
    runId: 'run_8c5a1b3e',
    sessionKey: '__fallback__',
    status: 'rejected',
    actionClass: 'external_communication',
    toolId: 'send_message',
    proposedAction: {
      description: 'Send intermediate progress update to Telegram mid-investigation.',
      target: 'telegram:@copenet_ops',
      payload: { message: 'Still investigating. Provider init race confirmed. Working on fix.' },
    },
    rationale: 'Agent decided to proactively update the operator mid-run.',
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
    resolvedAt: new Date(Date.now() - 1000 * 60 * 60 * 5 + 1000 * 90).toISOString(),
    outcome: {
      decision: 'rejected',
      note: 'Not yet — wait until investigation is done',
      decidedAt: new Date(Date.now() - 1000 * 60 * 60 * 5 + 1000 * 90).toISOString(),
    },
  },
];

// ---------------------------------------------------------------------------
// Messaging destinations
// ---------------------------------------------------------------------------

export const MOCK_DESTINATIONS: MessageDestination[] = [
  {
    id: 'tg-ops',
    platform: 'telegram',
    target: 'telegram:@copenet_ops',
    displayName: '@copenet_ops',
    isDefault: true,
    requiresApproval: true,
    status: 'configured',
  },
  {
    id: 'tg-private-test',
    platform: 'telegram',
    target: 'telegram:987654321',
    displayName: 'Private Test Chat',
    threadLabel: null,
    isDefault: false,
    requiresApproval: false,
    status: 'configured',
  },
  {
    id: 'tg-engineering',
    platform: 'telegram',
    target: 'telegram:-1001234567890:42',
    displayName: 'Engineering Group',
    threadLabel: 'Alerts thread',
    isDefault: false,
    requiresApproval: true,
    status: 'configured',
  },
];

export function getMockDestinations(): MessageDestination[] {
  return MOCK_DESTINATIONS;
}

export function getMockApprovalHistory(): ApprovalRequest[] {
  return MOCK_APPROVAL_HISTORY;
}

// ---------------------------------------------------------------------------
// Messaging config (operator platform settings)
// ---------------------------------------------------------------------------

export const MOCK_MESSAGING_CONFIG: MessagingConfig = {
  telegram: {
    botUsername: '@CopeNetBot',
    tokenMasked: 'tg:7321...xxxx',
    connectionStatus: 'connected',
    lastVerifiedAt: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    errorMessage: null,
  },
  destinations: MOCK_DESTINATIONS,
  approvalPolicy: {
    requireApprovalByDefault: true,
    hardlineBlocklist: [],
  },
  telegramDefaults: {
    provider: 'codex-cli',
    model: 'gpt-5.4',
    systemPromptId: 'default',
    taskPromptId: 'none',
  },
  routes: [],
};

export function getMockMessagingConfig(): MessagingConfig {
  return MOCK_MESSAGING_CONFIG;
}

// ---------------------------------------------------------------------------
// Run timeline (paused-run lifecycle)
// ---------------------------------------------------------------------------

export const MOCK_RUN_TIMELINE: RunTimeline = {
  runId: 'run_2b1a9e4f',
  sessionKey: '__fallback__',
  pausedAt: new Date(Date.now() - 1000 * 45).toISOString(),
  resumedAt: null,
  events: [
    {
      id: 'tl-1',
      kind: 'run_started',
      at: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
      label: 'Run started',
      detail: 'Investigate provider init race in harness',
      status: 'ok',
    },
    {
      id: 'tl-2',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
      label: 'files.read_file',
      detail: 'src/copenet/core/orchestrator/runtime.py (420 lines)',
      status: 'ok',
      toolId: 'files.read_file',
      durationMs: 14,
    },
    {
      id: 'tl-3',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 22).toISOString(),
      label: 'files.grep',
      detail: 'plan_turn usages → 7 hits',
      status: 'ok',
      toolId: 'files.grep',
      durationMs: 23,
    },
    {
      id: 'tl-4',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 21).toISOString(),
      label: 'files.read_file',
      detail: 'src/copenet/core/harness/planner.py (192 lines)',
      status: 'ok',
      toolId: 'files.read_file',
      durationMs: 9,
    },
    {
      id: 'tl-5',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      label: 'trace.read',
      detail: 'run 2b1a-9e4f harness events (31ms)',
      status: 'ok',
      toolId: 'trace.read',
      durationMs: 31,
    },
    {
      id: 'tl-6',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
      label: 'trace.read',
      detail: 'run 4f91-cc01 harness events (28ms)',
      status: 'ok',
      toolId: 'trace.read',
      durationMs: 28,
    },
    {
      id: 'tl-7',
      kind: 'tool_called',
      at: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
      label: 'code.edit',
      detail: 'Drafted 3-file patch plan (runtime.py, planner.py, tests)',
      status: 'ok',
      toolId: 'code.edit',
      durationMs: 182,
    },
    {
      id: 'tl-8',
      kind: 'approval_requested',
      at: new Date(Date.now() - 1000 * 45).toISOString(),
      label: 'send_message → approval required',
      detail: 'Agent wants to send run summary to telegram:@copenet_ops',
      status: 'paused',
      toolId: 'send_message',
      linkedApprovalId: 'appr_c3d9f1a2',
    },
  ],
};

export function getMockRunTimeline(): RunTimeline {
  return MOCK_RUN_TIMELINE;
}

// ---------------------------------------------------------------------------
// Operator inbox items (derived from approval history + outbound messages)
// ---------------------------------------------------------------------------

export function buildInboxItems(
  approvals: ApprovalRequest[],
  runPausedReason: 'awaiting_approval' | null,
): InboxItem[] {
  const items: InboxItem[] = [];

  // Paused-run urgent item (most priority)
  if (runPausedReason === 'awaiting_approval') {
    const pending = approvals.find((a) => a.status === 'pending');
    if (pending) {
      items.push({
        id: `inbox-paused-${pending.approvalId}`,
        priority: 'urgent',
        kind: 'paused_run',
        title: 'Run paused — action required',
        subtitle: `${pending.toolId} → ${pending.proposedAction.target ?? 'unknown target'}`,
        createdAt: pending.createdAt,
        sessionKey: pending.sessionKey,
        runId: pending.runId,
        approvalData: pending,
      });
    }
  }

  // Pending approvals not yet shown as paused-run
  for (const approval of approvals) {
    if (approval.status !== 'pending') continue;
    const alreadyShown = items.some((i) => i.approvalData?.approvalId === approval.approvalId);
    if (!alreadyShown) {
      items.push({
        id: `inbox-approval-${approval.approvalId}`,
        priority: 'attention',
        kind: 'pending_approval',
        title: `Pending: ${approval.toolId}`,
        subtitle: approval.proposedAction.description,
        createdAt: approval.createdAt,
        sessionKey: approval.sessionKey,
        runId: approval.runId,
        approvalData: approval,
      });
    }
  }

  // Recently resolved — show last 5
  const resolved = approvals
    .filter((a) => a.status !== 'pending')
    .slice(0, 5);

  for (const approval of resolved) {
    const decisionLabel =
      approval.status === 'approved' ? 'Approved'
      : approval.status === 'modified' ? 'Modified'
      : approval.status === 'rejected' ? 'Rejected'
      : 'Expired';
    items.push({
      id: `inbox-resolved-${approval.approvalId}`,
      priority: 'info',
      kind: 'resolved_approval',
      title: `${decisionLabel}: ${approval.toolId}`,
      subtitle: approval.proposedAction.description,
      createdAt: approval.resolvedAt ?? approval.createdAt,
      sessionKey: approval.sessionKey,
      runId: approval.runId,
      approvalData: approval,
    });
  }

  // Sort: urgent first, then attention, then info; within same priority by newest first
  const PRIORITY_ORDER: Record<string, number> = { urgent: 0, attention: 1, info: 2 };
  items.sort((a, b) => {
    const pDiff = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
    if (pDiff !== 0) return pDiff;
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });

  return items;
}
