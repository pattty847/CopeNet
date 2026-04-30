// ProfileChangelog — receipt-style timeline of profile mutations.
//
// Each entry shows what changed, when, why CopeNet changed it, and what triggered it.
// Honest empty state when the store has no changelog data.
//
// Backend contract: populated by profile:changelog:loaded + profile:changed push events.

import { Brain } from 'lucide-react';
import type { ProfileChangelogItem, ProfileChangelogChangeKind } from '../../runtime/types';
import { useProfileChangelog } from '../../runtime/adapter';

function timeLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function kindLabel(kind: ProfileChangelogChangeKind): string {
  switch (kind) {
    case 'priority_updated':    return 'Priority updated';
    case 'goal_added':          return 'Goal added';
    case 'goal_removed':        return 'Goal removed';
    case 'tone_updated':        return 'Tone adjusted';
    case 'noise_filter_added':  return 'Noise filter added';
    case 'noise_filter_removed':return 'Noise filter removed';
    case 'schedule_updated':    return 'Schedule updated';
    case 'constraint_updated':  return 'Constraint updated';
    default:                    return 'Profile updated';
  }
}

function kindDot(kind: ProfileChangelogChangeKind): string {
  switch (kind) {
    case 'priority_updated':    return 'bg-shell-accent';
    case 'goal_added':          return 'bg-shell-success';
    case 'goal_removed':        return 'bg-shell-error';
    case 'tone_updated':        return 'bg-[#a78bfa]';
    case 'noise_filter_added':
    case 'noise_filter_removed':return 'bg-shell-muted';
    default:                    return 'bg-shell-accent/50';
  }
}

function sourceLabel(source: ProfileChangelogItem['source']): string {
  switch (source) {
    case 'explicit':             return 'operator';
    case 'inferred':             return 'inferred';
    case 'session_observation':  return 'observed';
    default:                     return source;
  }
}

interface ChangelogEntryProps {
  item: ProfileChangelogItem;
  isLast: boolean;
}

function ChangelogEntry({ item, isLast }: ChangelogEntryProps) {
  return (
    <div className="relative flex gap-3">
      {/* Timeline spine */}
      <div className="flex flex-col items-center">
        <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${kindDot(item.kind)}`} />
        {!isLast && <div className="mt-1 w-px flex-1 bg-shell-border" />}
      </div>

      {/* Content */}
      <div className={`min-w-0 flex-1 pb-3 ${isLast ? 'pb-0' : ''}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium text-shell-text">{item.summary}</div>
            {item.detail && (
              <div className="mt-0.5 text-[11px] leading-snug text-shell-muted">{item.detail}</div>
            )}
          </div>
          <span className="shrink-0 rounded-full border border-shell-border bg-shell-bg px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-shell-muted">
            {sourceLabel(item.source)}
          </span>
        </div>
        {item.rationale && (
          <div className="mt-1 rounded-[8px] border border-shell-border bg-shell-bg px-2 py-1 text-[11px] italic leading-snug text-shell-muted">
            "{item.rationale}"
          </div>
        )}
        <div className="mt-1 flex items-center gap-2 text-[10px] text-shell-muted/70">
          <span>{kindLabel(item.kind)}</span>
          <span>·</span>
          <span>{timeLabel(item.changedAt)}</span>
        </div>
      </div>
    </div>
  );
}

interface ProfileChangelogProps {
  /** If provided, show only the most recent N entries. */
  limit?: number;
}

export function ProfileChangelog({ limit }: ProfileChangelogProps) {
  const changelog = useProfileChangelog();
  const entries = limit !== undefined ? changelog.slice(0, limit) : changelog;

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-6 text-center">
        <Brain className="h-5 w-5 text-shell-muted/40" />
        <div className="text-[12px] text-shell-muted">
          No profile changes yet. Changes will appear here when CopeNet updates your profile.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {entries.map((item, index) => (
        <ChangelogEntry key={item.id} item={item} isLast={index === entries.length - 1} />
      ))}
    </div>
  );
}
