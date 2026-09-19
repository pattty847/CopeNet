import React from 'react';
import { CircleDashed, GitBranch, GitMerge, Lock, MessageSquare } from 'lucide-react';
import type { SessionStandingState } from '../../types/backend';
import type { SessionPhase } from '../../runtime/sessionStanding';

/**
 * One icon per state, and the state is exclusive — a thread is in exactly one.
 *
 * "running" splits by phase: filled while a tool is still going, a hollow ring while
 * the model is composing. Everything else is a stopped thread, distinguished by what
 * the work needs next. "red" and "shares" are TAGS, not states, so they get no icon.
 */
export function SessionStateIcon({ state, phase }: { state: SessionStandingState; phase: SessionPhase }) {
  if (state === 'running') {
    return phase === 'acting' ? (
      <span
        className="mt-[3px] inline-block h-[7px] w-[7px] shrink-0 animate-pulse rounded-full bg-operator-accent"
        title="Running"
      />
    ) : (
      <span
        className="mt-[3px] inline-block h-[7px] w-[7px] shrink-0 rounded-full border border-operator-accent"
        title="Writing a reply"
      />
    );
  }
  if (state === 'blocked') {
    return <Lock className="mt-[2px] h-[13px] w-[13px] shrink-0 text-operator-accent" aria-label="Blocked" />;
  }
  if (state === 'unmerged') {
    return <GitBranch className="mt-[2px] h-[13px] w-[13px] shrink-0 text-operator-accent" aria-label="Done, not merged" />;
  }
  if (state === 'done') {
    return <GitMerge className="mt-[2px] h-[13px] w-[13px] shrink-0 text-operator-success/80" aria-label="Done, merged" />;
  }
  if (state === 'unknown') {
    // Standing has not arrived. Claim nothing: a faint mark, not a state.
    return <span className="mt-[5px] inline-block h-[5px] w-[5px] shrink-0 rounded-full bg-operator-muted/25" title="Loading…" />;
  }
  if (state === 'talk') {
    return <MessageSquare className="mt-[2px] h-[13px] w-[13px] shrink-0 text-operator-muted/50" aria-label="Talk only" />;
  }
  return <CircleDashed className="mt-[2px] h-[13px] w-[13px] shrink-0 text-operator-muted/70" aria-label="Idle" />;
}
