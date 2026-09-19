import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PERSONAL_STARTER_PRESETS,
  shouldRenderResumeSnapshot,
} from '../src/lib/personalHistory.ts';

test('personal starter presets stay stable and operator-friendly', () => {
  assert.equal(PERSONAL_STARTER_PRESETS.length, 3);
  assert.deepEqual(
    PERSONAL_STARTER_PRESETS.map((item) => item.id),
    ['think_through_something', 'plan_my_next_steps', 'reflect_and_organize'],
  );
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
