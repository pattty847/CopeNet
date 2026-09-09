import { Activity } from 'lucide-react';
import type { DeskHealth } from '../../../types/backend';
import { formatCount, formatErrorRate, formatLatency } from '../deskModel';
import { Card, CardLink } from './Card';

/** One bar per five-minute bucket of the last hour.
 *
 *  Bars are drawn even when every bucket is zero: a row of floor ticks reads as "quiet",
 *  an empty box reads as "not loaded", and the operator must be able to tell those apart. */
function Bars({ series }: { series: number[] }) {
  const peak = Math.max(1, ...series);
  return (
    <div className="hd-bars" aria-hidden="true">
      {series.map((value, index) => (
        <span
          key={index}
          className="hd-bars__bar"
          data-filled={value > 0}
          style={{ height: `${Math.max(8, (value / peak) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function Metric({ label, value, note, series }: { label: string; value: string; note?: string; series?: number[] }) {
  return (
    <div className="hd-metric">
      <div className="hd-metric__label">{label}</div>
      <div className="hd-metric__value">{value}</div>
      {note && <div className="hd-metric__note">{note}</div>}
      {series && <Bars series={series} />}
    </div>
  );
}

/** Runtime health, counted from durable run records over the last hour.
 *
 *  Four metrics, all sourced. Host memory and a disk-queue depth were on the original
 *  sketch and are absent here rather than approximated: CopeNet runs no sampler, so the
 *  only honest version of either would be a number invented at render time. */
export function SystemHealth({ health, wsConnected, generatedAt, onOpenObservability }: {
  health: DeskHealth | null;
  wsConnected: boolean;
  generatedAt: string;
  onOpenObservability: () => void;
}) {
  const nominal = wsConnected && (health?.errorRate ?? 0) < 0.25;

  return (
    <Card
      title="System health"
      icon={Activity}
      span={3}
      head={
        <>
          <span
            className="hd-health-foot__dot"
            style={{ background: nominal ? 'var(--mkt-up)' : 'var(--mkt-down)' }}
          />
          <span style={{ color: nominal ? 'var(--mkt-up)' : 'var(--mkt-down)', letterSpacing: '0.1em' }}>
            {wsConnected ? (nominal ? 'nominal' : 'degraded') : 'offline'}
          </span>
          <div className="hd-card__spacer" />
          <CardLink label="Runs" onClick={onOpenObservability} />
        </>
      }
    >
      {health == null ? (
        <div className="hd-empty">Loading…</div>
      ) : (
        <>
          <div className="hd-health-grid">
            <Metric
              label="Active sessions"
              value={formatCount(health.activeSessions)}
              note={`${formatCount(health.totalSessions)} stored${health.inFlight ? ` · ${health.inFlight} in flight` : ''}`}
            />
            <Metric label={`Tool calls (${health.windowMinutes}m)`} value={formatCount(health.toolCalls)} series={health.toolCallSeries} />
            <Metric
              label="Avg latency"
              value={formatLatency(health.avgLatencyMs)}
              note={health.runs === 0 ? 'no runs this hour' : `over ${health.runs} run${health.runs === 1 ? '' : 's'}`}
            />
            <Metric
              label="Error rate"
              value={formatErrorRate(health.errorRate, health.runs)}
              series={health.errorSeries}
            />
          </div>
          <div className="hd-health-foot">
            <span className="hd-health-foot__dot" style={{ background: nominal ? 'var(--mkt-up)' : 'var(--mkt-down)' }} />
            {wsConnected ? 'Gateway connected' : 'Gateway unreachable'}
            <b>{generatedAt ? new Date(generatedAt).toLocaleTimeString() : ''}</b>
          </div>
        </>
      )}
    </Card>
  );
}
