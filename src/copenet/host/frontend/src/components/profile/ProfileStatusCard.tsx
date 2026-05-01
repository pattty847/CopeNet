// ProfileStatusCard — compact operator surface for Pat Profile status.
//
// Lives in the Home right rail. Shows profile active state, last updated,
// top priority summary, and recent changelog count.
//
// Backend contract: profile populated by profile:loaded RPC push.
// Until then, renders an honest "No profile overlay yet" empty state.

import { ArrowRight, Brain, Clock } from 'lucide-react';
import { usePatProfile, useProfileChangelog } from '../../runtime/adapter';

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface ProfileStatusCardProps {
  onViewChangelog?: () => void;
}

export function ProfileStatusCard({ onViewChangelog }: ProfileStatusCardProps) {
  const profile = usePatProfile();
  const changelog = useProfileChangelog();
  const recentChanges = changelog.slice(0, 3);

  if (!profile) {
    return (
      <div className="shell-home-panel rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
              Pat Profile
            </div>
            <p className="mt-1 text-[12px] leading-5 text-shell-muted">
              No profile overlay yet. Wires up when the backend profile RPC ships.
            </p>
          </div>
          <Brain className="mt-0.5 h-3.5 w-3.5 shrink-0 text-shell-muted/40" />
        </div>
        <div className="mt-3 rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2.5 text-[11px] text-shell-muted">
          Profile · not yet wired
        </div>
      </div>
    );
  }

  const topPriority = profile.priorities[0] ?? null;

  return (
    <div className="shell-home-panel rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
              Pat Profile
            </div>
            {profile.active && (
              <span className="rounded-full bg-shell-success-soft px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-shell-success">
                Active
              </span>
            )}
          </div>
          <div className="mt-0.5 truncate text-[13px] font-medium text-shell-text">
            {profile.displayName}
          </div>
        </div>
        <Brain className="mt-0.5 h-3.5 w-3.5 shrink-0 text-shell-accent/60" />
      </div>

      {/* Top priority */}
      {topPriority && (
        <div className="mt-3 rounded-[12px] border border-shell-border bg-shell-panel-strong px-3 py-2">
          <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-shell-muted">
            Top Priority
          </div>
          <div className="mt-0.5 text-[12px] font-medium text-shell-text">
            {topPriority.label}
          </div>
          {profile.priorities.length > 1 && (
            <div className="mt-0.5 text-[11px] text-shell-muted">
              +{profile.priorities.length - 1} more
            </div>
          )}
        </div>
      )}

      {/* Recent changes */}
      {recentChanges.length > 0 && (
        <div className="mt-3 space-y-1">
          <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-shell-muted">
            Recent Changes
          </div>
          {recentChanges.map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-2 rounded-[10px] border border-shell-border bg-shell-bg px-2.5 py-1.5"
            >
              <div className="mt-px h-1.5 w-1.5 shrink-0 rounded-full bg-shell-accent/50" />
              <span className="min-w-0 flex-1 text-[11px] leading-snug text-shell-muted">
                {item.summary}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-1 text-[10px] text-shell-muted">
          <Clock className="h-3 w-3" />
          Updated {timeAgo(profile.lastUpdatedAt)}
        </div>
        {onViewChangelog && (
          <button
            type="button"
            onClick={onViewChangelog}
            className="flex items-center gap-1 text-[11px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
          >
            {profile.changelogCount > 0 && (
              <span className="rounded-full bg-shell-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-shell-accent">
                {profile.changelogCount}
              </span>
            )}
            History
            <ArrowRight className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
