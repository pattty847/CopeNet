import { Clock, Sparkles } from 'lucide-react';
import { useLastTurnState, useRunActivity } from '../../runtime/adapter';
import type { RunActivity } from '../../runtime/types';
import { EmptyState, ErrorState, LoadingState } from './ResourceStates';
import { TurnSummaryStrip } from './LiveToolFeed';
import { renderToolActivityItem } from './ToolActivityProof';

interface RunActivityPanelProps {
  sessionKey: string | null;
  isDraft: boolean;
}

function ActivityTimeline({ activity }: { activity: RunActivity }) {
  return (
    <div className="relative space-y-2 pl-3 stagger-children">
      <div className="absolute bottom-1 left-[5px] top-1 w-px bg-operator-border" />
      {activity.items.map((item) => (
        <div key={item.id} className="relative">
          <span className="absolute -left-[9px] top-3 h-1.5 w-1.5 rounded-full bg-operator-accent" />
          {renderToolActivityItem(item)}
        </div>
      ))}
    </div>
  );
}

export function RunActivityPanel({ sessionKey, isDraft }: RunActivityPanelProps) {
  const resource = useRunActivity(isDraft ? null : sessionKey);
  const turnState = useLastTurnState();

  if (isDraft) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No run activity yet"
        body="Grouped proof receipts will land here once the agent starts using tools, reading files, editing code, or producing artifacts."
      />
    );
  }

  if (resource.status === 'loading') return <LoadingState label="Loading run activity…" />;
  if (resource.status === 'error') {
    return <ErrorState title="Could not load run activity" message={resource.error ?? 'Unknown error'} />;
  }
  if (resource.status === 'empty' || !resource.data) {
    return (
      <EmptyState
        icon={Clock}
        title="No activity recorded"
        body="This session has not produced any tool activity yet. Grouped proof receipts will appear here as the run progresses."
      />
    );
  }

  const activity = resource.data;

  return (
    <div className="space-y-2 px-3 py-2.5">
      <div className="mb-0.5 flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
          Tool Activity
        </div>
        <span className="font-mono text-[10px] text-operator-muted/70">{activity.runId}</span>
      </div>

      {turnState && turnState.toolCallCount > 0 ? (
        <div className="rounded-xl border border-operator-accent/20 bg-operator-accent/6 px-3 py-2">
          <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-accent">Working now</div>
          <TurnSummaryStrip callCount={turnState.toolCallCount} failedCount={turnState.failedActions.length} />
          {turnState.terminalReason && turnState.terminalReason !== 'completed' ? (
            <div className="mt-1 font-mono text-[10px] text-operator-muted">terminal: {turnState.terminalReason}</div>
          ) : null}
        </div>
      ) : null}

      <ActivityTimeline activity={activity} />
    </div>
  );
}
