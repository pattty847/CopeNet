import assert from 'node:assert/strict';
import test from 'node:test';

import { mapRunToActivity } from '../src/runtime/activityProof';
import type { SessionRunRecord } from '../src/types/backend';
import type { Artifact } from '../src/runtime/types';

function makeRun(): SessionRunRecord {
  return {
    runId: 'run-proof-1',
    sessionKey: 'session-1',
    provider: 'openai-codex',
    model: 'gpt-5.4',
    status: 'completed',
    userMessage: 'Inspect and patch the provider adapter files',
    toolExecutionMode: 'batch',
    willAttemptToolLoop: true,
    startedAt: '2026-05-08T03:00:00.000Z',
    completedAt: '2026-05-08T03:00:04.000Z',
    workingSet: {},
    toolSteps: [
      { toolId: 'files.read', ok: true, summary: 'Read file src/copenet/providers/base.py.', target: 'src/copenet/providers/base.py', accessAction: 'read' },
      { toolId: 'files.read', ok: true, summary: 'Read file src/copenet/providers/codex_cli.py.', target: 'src/copenet/providers/codex_cli.py', accessAction: 'read' },
      { toolId: 'patch.apply', ok: true, summary: 'Updated provider adapter wiring.', target: 'src/copenet/providers/__init__.py', accessAction: 'write', artifactId: 'artifact-diff-1' },
      { toolId: 'shell.exec', ok: true, summary: 'Ran python3 -m py_compile ...', target: 'python3 -m py_compile $(rg --files src/copenet -g "*.py")' },
    ],
    artifactIds: ['artifact-diff-1'],
    outputSummary: 'Provider adapter wiring updated and compile check passed.',
    error: null,
    metadata: {},
  };
}

test('mapRunToActivity groups tool proof into collapsed-friendly categories', () => {
  const artifacts: Artifact[] = [
    {
      id: 'artifact-diff-1',
      kind: 'diff',
      title: 'Provider adapter wiring diff',
      oneLine: '1 file · +6 / -2',
      producedAt: '2026-05-08T03:00:03.500Z',
      runId: 'run-proof-1',
      files: [{ path: 'src/copenet/providers/__init__.py', additions: 6, deletions: 2 }],
    },
  ];

  const activity = mapRunToActivity(makeRun(), artifacts);
  const proofGroups = activity.items.filter((item) => item.kind === 'proof_group');

  assert.equal(proofGroups.length, 4);
  assert.deepEqual(proofGroups.map((item) => item.group), ['files_read', 'files_edited', 'commands', 'artifacts']);
  assert.equal(proofGroups[0].label, 'Read 2 files');
  assert.equal(proofGroups[1].label, 'Edited 1 file');
  assert.equal(proofGroups[2].label, 'Ran 1 command');
  assert.equal(proofGroups[3].label, 'Produced 1 artifact');

  const readMembers = proofGroups[0].members.map((member) => member.label);
  assert.deepEqual(readMembers, [
    'src/copenet/providers/base.py',
    'src/copenet/providers/codex_cli.py',
  ]);

  const artifactMember = proofGroups[3].members[0];
  assert.equal(artifactMember.additions, 6);
  assert.equal(artifactMember.deletions, 2);

  const note = activity.items.find((item) => item.kind === 'note');
  assert.ok(note);
});

test('mapRunToActivity expands preserved tool.batch members into grouped proof rows', () => {
  const run: SessionRunRecord = {
    ...makeRun(),
    runId: 'run-proof-batch',
    toolSteps: [
      {
        toolId: 'tool.batch',
        ok: false,
        summary: 'Executed 1 safe read; 1 remaining tool request must be requested individually.',
        error: 'mixed batch request repaired',
        policyDecision: 'unsafe_unknown',
        policySummary: 'TOOL_BATCH only supports read-only repo/context work.',
        members: [
          {
            callId: 'member-1',
            toolId: 'files.read',
            ok: true,
            summary: 'Read file docs/tests/example.md.',
            target: 'docs/tests/example.md',
            accessAction: 'read',
            preview: {
              type: 'file_read',
              path: 'docs/tests/example.md',
              lines: ['# Example', 'hello from proof'],
            },
          },
          {
            callId: 'member-2',
            toolId: 'shell.exec',
            ok: false,
            summary: 'Deferred shell.exec; request it as an individual TOOL_CALL.',
            target: 'ls',
            policyDecision: 'unsafe_unknown',
            policySummary:
              'TOOL_BATCH only supports read-only repo/context work. Request this tool as an individual TOOL_CALL after the read batch finishes.',
            error:
              'TOOL_BATCH only supports read-only repo/context work. Request this tool as an individual TOOL_CALL after the read batch finishes.',
          },
        ],
      },
    ],
    artifactIds: [],
    outputSummary: '',
  };

  const activity = mapRunToActivity(run, []);
  const proofGroups = activity.items.filter((item) => item.kind === 'proof_group');

  assert.equal(proofGroups.length, 2);
  assert.deepEqual(proofGroups.map((item) => item.group), ['files_read', 'commands']);
  assert.equal(proofGroups[0].members[0].label, 'docs/tests/example.md');
  assert.equal(proofGroups[0].members[0].fullOutput, '# Example\nhello from proof');
  assert.equal(proofGroups[1].members[0].label, 'ls');
  assert.match(proofGroups[1].members[0].detail ?? '', /individual TOOL_CALL/);
});
