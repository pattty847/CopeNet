import { AlertTriangle, Bot, CheckCircle2, CircleDashed, Wrench } from 'lucide-react';
import type { DeskActivityEntry } from '../../../types/backend';
import { formatLatency, relativeAge } from '../deskModel';
import { Card, CardLink } from './Card';

/** What the agents did lately, across every session.
 *
 *  The rows come from one server-side query, not a per-session fan-out — Observability's
 *  fan-out is why this needed its own RPC at all. */
export function RecentActivity({
  activity,
  loading,
  onOpenRun,
  onOpenAll,
}: {
  activity: DeskActivityEntry[];
  loading: boolean;
  onOpenRun: (entry: DeskActivityEntry) => void;
  onOpenAll: () => void;
}) {
  return (
    <Card
      title="Recent agent activity"
      icon={Bot}
      span={3}
      head={
        <>
          <div className="hd-card__spacer" />
          <CardLink label="View all" onClick={onOpenAll} />
        </>
      }
    >
      {activity.length === 0 ? (
        <div className="hd-empty">{loading ? 'Loading…' : 'No runs recorded yet.'}</div>
      ) : (
        activity.map((entry) => {
          const StatusIcon = entry.errored ? AlertTriangle : entry.completedAt ? CheckCircle2 : CircleDashed;
          const statusColor = entry.errored
            ? 'var(--mkt-down)'
            : entry.completedAt
              ? 'var(--mkt-up)'
              : 'var(--mkt-accent)';
          return (
            <button key={entry.runId} type="button" className="hd-run" onClick={() => onOpenRun(entry)}>
              <span className="hd-run__icon">
                <Wrench size={12} />
              </span>
              <span className="hd-run__title">{entry.sessionTitle}</span>
              <span className="hd-run__meta">{relativeAge(entry.startedAt)}</span>
              <span className="hd-run__summary">
                {entry.toolCount > 0 && `${entry.toolCount} tool${entry.toolCount === 1 ? '' : 's'} · `}
                {entry.durationMs != null && `${formatLatency(entry.durationMs)} · `}
                {entry.summary}
              </span>
              <span className="hd-run__status" style={{ color: statusColor }}>
                <StatusIcon size={9} style={{ display: 'inline', verticalAlign: '-1px', marginRight: 3 }} />
                {entry.status}
              </span>
            </button>
          );
        })
      )}
    </Card>
  );
}
