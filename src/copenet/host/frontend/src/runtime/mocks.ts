// Realistic mocked runtime data for the Agents UI surfaces.
//
// These mocks are scoped by session key so different sessions show
// different content, making the demo feel alive. Replace with real backend
// data once the runtime endpoints land — the UI already reads these through
// the helpers below, so only the helpers need rewiring.

import type {
  Artifact,
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
