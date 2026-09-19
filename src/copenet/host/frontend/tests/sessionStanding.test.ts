import assert from 'node:assert/strict';
import test from 'node:test';

import { NO_CHANGE_AREA, UNKNOWN_AREA, buildFilters, buildSessionRow, groupRowsByArea, matchesFilter } from '../src/runtime/sessionStanding';
import type { LiveToolCall, Session, SessionStanding } from '../src/types/backend';

function session(overrides: Partial<Session> = {}): Session {
  return {
    key: 's1',
    title: 'Chart agent token efficiency',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    archived: false,
    inFlightRunId: null,
    updatedAt: '2026-09-17T00:00:00Z',
    ...overrides,
  } as unknown as Session;
}

function standing(overrides: Partial<SessionStanding> = {}): SessionStanding {
  return {
    sessionKey: 's1',
    state: 'idle',
    standingNote: null,
    standingDone: false,
    ledger: { linesAdded: 0, linesRemoved: 0, fileCount: 0, recentFiles: [], area: null },
    branch: { branch: null, commitsAhead: 0, trunk: null },
    toolCalls: 0,
    verificationFailed: false,
    approvalCommand: null,
    sharesWith: [],
    ...overrides,
  };
}

function call(overrides: Partial<LiveToolCall> = {}): LiveToolCall {
  return {
    id: 'c1',
    toolId: 'files.read',
    state: 'success',
    summary: '',
    startedAt: '2026-09-17T00:00:00Z',
    completedAt: null,
    ...overrides,
  } as LiveToolCall;
}

// -- the title across one turn --------------------------------------------------

test('acting: the title is the model’s live tool phrase, which we already pay for', () => {
  const row = buildSessionRow(
    session({ inFlightRunId: 'run-1' }),
    standing({ state: 'running', standingNote: 'rounding covers every model-facing path' }),
    [
      call({ id: 'a', activityTitle: 'Planning repository inspection' }),
      call({ id: 'b', state: 'running', activityTitle: 'Inspecting market core and app APIs' }),
    ],
  );
  assert.equal(row.phase, 'acting');
  assert.equal(row.title, 'Inspecting market core and app APIs');
  assert.equal(row.line, '1 tool call so far');
});

test('writing: the phrase stops, so the title falls back to the last standing line', () => {
  const row = buildSessionRow(
    session({ inFlightRunId: 'run-1' }),
    standing({ state: 'running', standingNote: 'rounding covers every model-facing path' }),
    [call({ activityTitle: 'Inspecting market core and app APIs' })],
  );
  assert.equal(row.phase, 'writing');
  assert.equal(row.title, 'rounding covers every model-facing path');
  assert.equal(row.line, 'writing…');
});

test('settled: the title is the standing line the model left', () => {
  const row = buildSessionRow(
    session(),
    standing({
      state: 'unmerged',
      standingNote: 'rule windows ship; only the custom editor is left',
      ledger: { linesAdded: 510, linesRemoved: 96, fileCount: 11, recentFiles: ['ruleWindows.ts', 'evaluate.py'], area: 'src/copenet' },
      branch: { branch: 'claude/screener-windows', commitsAhead: 4, trunk: 'main' },
    }),
    [],
  );
  assert.equal(row.phase, 'settled');
  assert.equal(row.title, 'rule windows ship; only the custom editor is left');
  assert.equal(row.titleIsStanding, true);
  assert.equal(row.line, 'done, not merged · 4 commits on claude/screener-windows');
  assert.deepEqual(row.ledger, { added: 510, removed: 96, files: ['ruleWindows.ts', 'evaluate.py'], moreFiles: 9 });
});

test('a turn that left no standing line falls back to the plain title, never a stale one', () => {
  const row = buildSessionRow(session(), standing(), []);
  assert.equal(row.title, 'Chart agent token efficiency');
  assert.equal(row.titleIsStanding, false);
});

// -- line 2 is a sentence, never a bare number ----------------------------------

test('blocked names the command the operator has to approve', () => {
  const row = buildSessionRow(
    session(),
    standing({ state: 'blocked', approvalCommand: 'git clean -fd' }),
    [],
  );
  assert.equal(row.line, 'blocked · approval needed for git clean -fd');
});

test('a thread that changed nothing says so', () => {
  const row = buildSessionRow(session(), standing({ state: 'talk', toolCalls: 22 }), []);
  assert.equal(row.line, 'talk only · 22 tool calls, nothing changed');
  assert.equal(row.ledger, null);
  assert.equal(row.area, NO_CHANGE_AREA);
});

test('a run that stopped with the suite red reads differently from an ordinary idle one', () => {
  const ledger = { linesAdded: 31, linesRemoved: 12, fileCount: 2, recentFiles: ['fakeChart.ts'], area: 'src/copenet' };
  const red = buildSessionRow(session(), standing({ state: 'idle', verificationFailed: true, ledger }), []);
  const calm = buildSessionRow(session(), standing({ state: 'idle', ledger }), []);
  assert.equal(red.line, 'stopped with the suite red · 2 files changed');
  assert.equal(calm.line, 'idle · 2 files changed, nothing running');
  assert.deepEqual(red.tags, [{ label: 'red', tone: 'alert' }]);
});

// -- tags -----------------------------------------------------------------------

test('the branch quietly holding two features names the shared file', () => {
  const row = buildSessionRow(
    session(),
    standing({
      state: 'idle',
      ledger: { linesAdded: 301, linesRemoved: 0, fileCount: 7, recentFiles: ['HomePage.tsx'], area: 'src/copenet' },
      sharesWith: [{ sessionKey: 's2', path: 'HomePage.tsx' }],
    }),
    [],
  );
  assert.deepEqual(row.tags, [{ label: 'shares HomePage.tsx', tone: 'alert' }]);
});

test('close is offered only when the model said done and nothing is unmerged', () => {
  const done = buildSessionRow(session(), standing({ state: 'done', standingDone: true }), []);
  const unmerged = buildSessionRow(session(), standing({ state: 'unmerged', standingDone: true }), []);
  assert.equal(done.offerClose, true);
  assert.equal(unmerged.offerClose, false);
});

// -- grouping -------------------------------------------------------------------

test('rows group by the area their work lives in, with talk-only threads last', () => {
  const rows = [
    buildSessionRow(session({ key: 'a' }), standing({ sessionKey: 'a', state: 'talk' }), []),
    buildSessionRow(
      session({ key: 'b' }),
      standing({
        sessionKey: 'b',
        ledger: { linesAdded: 4, linesRemoved: 0, fileCount: 1, recentFiles: ['x.py'], area: 'core/market' },
      }),
      [],
    ),
    buildSessionRow(
      session({ key: 'c' }),
      standing({
        sessionKey: 'c',
        ledger: { linesAdded: 9, linesRemoved: 1, fileCount: 1, recentFiles: ['y.py'], area: 'core/market' },
      }),
      [],
    ),
  ];
  const groups = groupRowsByArea(rows);
  assert.deepEqual(
    groups.map((group) => [group.area, group.rows.length]),
    [['core/market', 2], [NO_CHANGE_AREA, 1]],
  );
});

// -- the filter chips over the list --------------------------------------------

test('chips count what the operator is hunting for, and hide what has no matches', () => {
  const rows = [
    buildSessionRow(session({ key: 'a', inFlightRunId: 'r' }), standing({ sessionKey: 'a', state: 'running' }), []),
    buildSessionRow(session({ key: 'b' }), standing({ sessionKey: 'b', state: 'unmerged' }), []),
    buildSessionRow(session({ key: 'c' }), standing({ sessionKey: 'c', state: 'talk' }), []),
  ];
  assert.deepEqual(
    buildFilters(rows, { pinned: 0, archived: 0 }).map((chip) => [chip.id, chip.count]),
    [['all', 3], ['live', 1], ['unmerged', 1]],
  );
});

test('all is always offered even when nothing matches anything else', () => {
  assert.deepEqual(
    buildFilters([buildSessionRow(session(), standing({ state: 'talk' }), [])], { pinned: 0, archived: 0 }).map((chip) => chip.id),
    ['all'],
  );
});

test('a filter keeps only its own state, and all keeps everything', () => {
  const unmerged = buildSessionRow(session(), standing({ state: 'unmerged' }), []);
  assert.equal(matchesFilter(unmerged, 'unmerged'), true);
  assert.equal(matchesFilter(unmerged, 'idle'), false);
  assert.equal(matchesFilter(unmerged, 'all'), true);
});

test('pinned and archived ride the chip row with their own counts', () => {
  const rows = [buildSessionRow(session(), standing({ state: 'idle' }), [])];
  assert.deepEqual(
    buildFilters(rows, { pinned: 2, archived: 7 }).map((chip) => [chip.id, chip.count]),
    [['all', 1], ['idle', 1], ['pinned', 2], ['archived', 7]],
  );
});

test('a shelf with nothing on it is not offered', () => {
  const rows = [buildSessionRow(session(), standing({ state: 'idle' }), [])];
  const ids = buildFilters(rows, { pinned: 0, archived: 0 }).map((chip) => chip.id);
  assert.equal(ids.includes('pinned'), false);
  assert.equal(ids.includes('archived'), false);
});

// -- not loaded is not "nothing changed" ----------------------------------------

test('a row with no standing yet claims nothing at all', () => {
  const row = buildSessionRow(session(), undefined, []);
  assert.equal(row.state, 'unknown');
  assert.equal(row.line, '');
  assert.equal(row.ledger, null);
  assert.equal(row.area, UNKNOWN_AREA);
  assert.notEqual(row.area, NO_CHANGE_AREA);
});

test('a loaded thread that genuinely changed nothing is distinct from an unloaded one', () => {
  const loaded = buildSessionRow(session(), standing({ state: 'talk', toolCalls: 3 }), []);
  assert.equal(loaded.state, 'talk');
  assert.equal(loaded.area, NO_CHANGE_AREA);
  assert.notEqual(loaded.line, '');
});

test('loading is never offered as a chip to filter to', () => {
  const ids = buildFilters([buildSessionRow(session(), undefined, [])], { pinned: 0, archived: 0 }).map((c) => c.id);
  assert.deepEqual(ids, ['all']);
});
