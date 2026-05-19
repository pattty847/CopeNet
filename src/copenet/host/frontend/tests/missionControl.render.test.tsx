import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { MissionControlPanel } from '../src/components/home/MissionControlPanel';
import type { MissionControlItem } from '../src/lib/missionControl';

function item(overrides: Partial<MissionControlItem>): MissionControlItem {
  return {
    id: 'item-1',
    lane: 'needs_attention',
    kind: 'approval',
    title: 'Approval needed: files.write',
    detail: 'Review the pending action.',
    source: 'CopeNet Core',
    meta: '2m ago',
    sessionKey: 'session-1',
    runId: 'run-1',
    provider: 'codex-cli',
    model: 'gpt-5.4',
    at: '2026-05-15T15:40:00.000Z',
    ...overrides,
  };
}

test('MissionControlPanel renders the four operator lanes', () => {
  const html = renderToStaticMarkup(
    <MissionControlPanel
      items={[
        item({ id: 'attention', lane: 'needs_attention', kind: 'approval' }),
        item({ id: 'useful', lane: 'recently_useful', kind: 'useful_run', title: 'Finished repo pass' }),
        item({ id: 'resume', lane: 'ready_to_continue', kind: 'resume_session', title: 'Resume CopeNet Core' }),
        item({ id: 'workflow', lane: 'promote_to_workflow', kind: 'workflow_candidate', title: 'Promote Weekly probe' }),
      ]}
      loading={false}
      onOpenSession={() => {}}
      onOpenObservability={() => {}}
      onPromoteWorkflow={() => {}}
    />,
  );

  assert.match(html, /Needs Attention/);
  assert.match(html, /Recently Useful/);
  assert.match(html, /Ready To Continue/);
  assert.match(html, /Promote To Workflow/);
  assert.match(html, /Approval needed/);
  assert.match(html, /Open session/);
});

test('MissionControlPanel renders a calm empty state', () => {
  const html = renderToStaticMarkup(
    <MissionControlPanel
      items={[]}
      loading={false}
      onOpenSession={() => {}}
      onOpenObservability={() => {}}
      onPromoteWorkflow={() => {}}
    />,
  );

  assert.match(html, /No urgent work/);
  assert.match(html, /Mission Control/);
});
