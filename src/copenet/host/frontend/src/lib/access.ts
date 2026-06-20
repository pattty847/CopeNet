// Access is CopeNet's permission axis — what a runtime is allowed to touch. It is
// distinct from Profile (how the agent behaves). For backwards-compat it rides on the
// session `taskPromptId` field, but only two values change tool policy:
//   - `none`        → Read-only (reads + safe shell allowlist)
//   - `full-access` → Full Access (writes + unrestricted shell)
// Behavioral presets (planning/debug/code-review/refactor) are Profile concerns now.
//
// Full Access is granted only to frontier providers. This list MUST match
// FULL_ACCESS_PROVIDERS in src/copenet/core/tools/policy.py, which enforces the gate
// server-side regardless of what the UI offers.

export interface AccessOption {
  id: string;
  label: string;
  hint?: string;
}

export const FULL_ACCESS_PROVIDERS = new Set(['claude-cli', 'openai-codex']);

export const ACCESS_OPTIONS: AccessOption[] = [
  { id: 'none', label: 'Read-only', hint: 'Reads + safe shell commands' },
  { id: 'full-access', label: 'Full Access', hint: 'Writes + unrestricted shell' },
];

export function providerAllowsFullAccess(providerId: string | null | undefined): boolean {
  return FULL_ACCESS_PROVIDERS.has((providerId || '').trim().toLowerCase());
}

/** Access options offered for a given provider (Full Access hidden when not allowed). */
export function accessOptionsFor(providerId: string | null | undefined): AccessOption[] {
  const fullAllowed = providerAllowsFullAccess(providerId);
  return ACCESS_OPTIONS.filter((option) => option.id !== 'full-access' || fullAllowed);
}

/** Human label for a stored taskPromptId, from the Access perspective. */
export function accessLabel(taskPromptId: string | null | undefined): string {
  return (taskPromptId || '').trim().toLowerCase() === 'full-access' ? 'Full Access' : 'Read-only';
}
