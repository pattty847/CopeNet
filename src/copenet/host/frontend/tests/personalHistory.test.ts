import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PERSONAL_STARTER_PRESETS,
  describeSessionReturnCue,
  shouldRenderResumeSnapshot,
} from '../src/lib/personalHistory.ts';

test('personal starter presets stay stable and operator-friendly', () => {
  assert.equal(PERSONAL_STARTER_PRESETS.length, 3);
  assert.deepEqual(
    PERSONAL_STARTER_PRESETS.map((item) => item.id),
    ['think_through_something', 'plan_my_next_steps', 'reflect_and_organize'],
  );
});

test('personal sessions prefer task summary as the fleet return cue', () => {
  const cue = describeSessionReturnCue({
    providerLabel: 'Codex',
    modelLabel: 'gpt-5.4',
    taskSummary: 'Figure out the launch sequence for next week',
    starterIntent: 'plan_my_next_steps',
    topicalTags: ['planning'],
  });

  assert.equal(cue.kind, 'personal');
  assert.match(cue.primary, /^planning · Figure out the launch sequence/);
});

test('coding sessions keep provider and model cues', () => {
  const cue = describeSessionReturnCue({
    providerLabel: 'OpenAI Codex',
    modelLabel: 'gpt-5.4',
    taskSummary: null,
    starterIntent: null,
    topicalTags: [],
  });

  assert.equal(cue.kind, 'runtime');
  assert.equal(cue.primary, 'OpenAI Codex · gpt-5.4');
});

test('resume snapshot only shows when there is meaningful saved state', () => {
  assert.equal(
    shouldRenderResumeSnapshot({
      taskSummary: 'Figure out what to say to the team',
      unresolvedQuestions: [],
      priorDecisions: [],
      starterIntent: 'reflect_and_organize',
    }),
    true,
  );
  assert.equal(
    shouldRenderResumeSnapshot({
      taskSummary: null,
      unresolvedQuestions: [],
      priorDecisions: [],
      starterIntent: null,
    }),
    false,
  );
});
