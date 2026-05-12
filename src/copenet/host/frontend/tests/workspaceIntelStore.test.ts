import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

test('runtime context stores workspace intelligence summary', () => {
  useAppStore.getState().setRuntimeContext({
    workspaceRoot: '/Users/copeharder/Programming/CopeNet',
    fileToolScope: 'workspace_home_visible_roaming',
    shellToolScope: 'cwd_default',
    shellAllowlist: ['python3'],
    note: 'runtime note',
    workspaceIntel: {
      workspaceRoot: '/Users/copeharder/Programming/CopeNet',
      cacheStatus: 'cached',
      languages: ['python', 'typescript'],
      packageManagers: ['npm', 'uv'],
      recommendedDefaultChecks: ['uv run --extra dev pytest -q', 'npm run lint'],
    },
  } as any);

  const runtimeContext = useAppStore.getState().runtimeContext;

  assert.equal(runtimeContext?.workspaceIntel?.languages[0], 'python');
  assert.equal(runtimeContext?.workspaceIntel?.packageManagers.includes('uv'), true);
  assert.equal(runtimeContext?.workspaceIntel?.recommendedDefaultChecks[1], 'npm run lint');
});
