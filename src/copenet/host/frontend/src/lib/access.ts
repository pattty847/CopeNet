// Access is CopeNet's permission axis — what a runtime is allowed to touch. It is
// distinct from Profile (how the agent behaves). For backwards-compat it rides on the
// session `taskPromptId` field, but only three values change tool policy:
//   - `none`        → Read-only (reads + safe shell allowlist)
//   - `ask`         → Read-only, but prompts the operator before anything off-allowlist
//   - `full-access` → Full Access (writes + unrestricted shell)
// Behavioral presets (planning/debug/code-review/refactor) are Profile concerns now.
//
// Every registered provider may be granted Full Access (the local runtimes that were
// denied it were removed 2026-09-13); the server enforces Access in
// src/copenet/core/tools/policy.py regardless of what the UI offers.

export interface AccessOption {
  id: string;
  label: string;
  hint?: string;
}

export const ACCESS_OPTIONS: AccessOption[] = [
  { id: 'none', label: 'Read-only', hint: 'Reads + safe shell commands' },
  { id: 'ask', label: 'Ask', hint: 'Prompts you before anything off-allowlist' },
  { id: 'full-access', label: 'Full Access', hint: 'Writes + unrestricted shell' },
];

/** Access options offered for a session. */
export function accessOptionsFor(): AccessOption[] {
  return ACCESS_OPTIONS;
}

/** Human label for a stored taskPromptId, from the Access perspective. */
export function accessLabel(taskPromptId: string | null | undefined): string {
  const id = (taskPromptId || '').trim().toLowerCase();
  if (id === 'full-access') return 'Full Access';
  if (id === 'ask') return 'Ask';
  return 'Read-only';
}
