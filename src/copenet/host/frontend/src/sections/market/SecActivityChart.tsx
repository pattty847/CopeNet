import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts';
import { buildSecActivityRows, formatSecActivityValue, type SecActivityRow, type SecActivityUnit } from './secActivity';
import type { EvidenceItem } from './types';

export function SecActivityChart({
  evidence,
  selectedDay,
  onSelectDay,
}: {
  evidence: EvidenceItem[];
  selectedDay: string | null;
  onSelectDay: (day: string | null) => void;
}) {
  const [unit, setUnit] = useState<SecActivityUnit>('money');
  const rows = useMemo(() => buildSecActivityRows(evidence, unit), [evidence, unit]);
  const selectedRow = rows.find((row) => row.day === selectedDay) ?? null;

  return (
    <section className="sec-activity-visual" aria-label="SEC transaction activity">
      <header>
        <div><h3>Insider activity magnitude</h3><p>Executed Form 4 trades and planned Form 144 sales, kept analytically separate.</p></div>
        <div role="group" aria-label="SEC transaction chart unit">
          <button type="button" aria-pressed={unit === 'money'} onClick={() => setUnit('money')}>Dollar value</button>
          <button type="button" aria-pressed={unit === 'shares'} onClick={() => setUnit('shares')}>Shares</button>
        </div>
      </header>
      {rows.length ? (
        <>
          <div className="sec-activity-chart">
            <ResponsiveContainer width="100%" height="100%" minWidth={260} minHeight={220}>
              <BarChart
                data={rows}
                margin={{ top: 10, right: 12, left: 2, bottom: 0 }}
                barCategoryGap="24%"
                accessibilityLayer
                onClick={(state) => {
                  const day = typeof state?.activeLabel === 'string' ? state.activeLabel : null;
                  if (day) onSelectDay(selectedDay === day ? null : day);
                }}
              >
                <CartesianGrid vertical={false} stroke="rgba(254,252,244,.07)" />
                <XAxis dataKey="day" tickFormatter={(day: string) => rows.find((row) => row.day === day)?.label ?? day} axisLine={false} tickLine={false} minTickGap={16} tick={{ fill: '#777168', fontSize: 9.5 }} />
                <YAxis axisLine={false} tickLine={false} width={64} tick={{ fill: '#777168', fontSize: 9.5 }} tickFormatter={(value: number) => formatSecActivityValue(value, unit)} />
                <Tooltip cursor={{ fill: 'rgba(254,252,244,.035)' }} content={(props) => <SecActivityTooltip {...props} unit={unit} />} />
                <ReferenceLine y={0} stroke="rgba(254,252,244,.22)" />
                <Bar dataKey="executedValue" name={unit === 'money' ? 'Executed Form 4' : 'Executed Form 4 shares'} radius={[2, 2, 2, 2]} maxBarSize={28} isAnimationActive={false}>
                  {rows.map((row) => <Cell key={row.day} fill={row.executedValue >= 0 ? '#69c589' : '#d96d5f'} fillOpacity={selectedDay && selectedDay !== row.day ? 0.24 : 0.88} stroke={selectedDay === row.day ? '#fefcf4' : 'transparent'} strokeWidth={selectedDay === row.day ? 1 : 0} />)}
                </Bar>
                <Bar dataKey="plannedValue" name={unit === 'money' ? 'Planned Form 144' : 'Planned Form 144 shares'} radius={[2, 2, 2, 2]} maxBarSize={28} isAnimationActive={false}>
                  {rows.map((row) => <Cell key={row.day} fill="#c6924e" fillOpacity={selectedDay && selectedDay !== row.day ? 0.24 : 0.82} stroke={selectedDay === row.day ? '#fefcf4' : 'transparent'} strokeWidth={selectedDay === row.day ? 1 : 0} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <footer>
            <span>Green/red = executed Form 4 net · amber = planned Form 144 sale</span>
            <span>{selectedRow ? selectedActivitySummary(selectedRow, unit) : `${rows.length} active dates in the selected SEC window`}</span>
          </footer>
        </>
      ) : <div className="sec-activity-empty">No priced or share-sized Form 4 / Form 144 activity is available in this window.</div>}
    </section>
  );
}

function SecActivityTooltip({ active, payload, unit }: TooltipContentProps<number, string> & { unit: SecActivityUnit }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as SecActivityRow | undefined;
  if (!row) return null;
  return (
    <div className="sec-activity-tooltip">
      <strong>{new Intl.DateTimeFormat(undefined, { month: 'long', day: 'numeric', year: 'numeric' }).format(new Date(`${row.day}T00:00:00Z`))}</strong>
      {row.executedValue ? <><b data-tone={row.executedValue > 0 ? 'up' : 'down'}>{formatSecActivityValue(row.executedValue, unit)} executed</b><small>{row.executedPercentile}th percentile Form 4 magnitude in this window</small></> : null}
      {row.plannedValue ? <><b data-tone="planned">{formatSecActivityValue(row.plannedValue, unit)} planned</b><small>{row.plannedPercentile}th percentile Form 144 magnitude in this window</small></> : null}
      <span>{row.buys} acquisitions · {row.sells} dispositions · {row.plannedSales} planned sales</span>
    </div>
  );
}

function selectedActivitySummary(row: SecActivityRow, unit: SecActivityUnit): string {
  const parts = [];
  if (row.executedValue) parts.push(`${formatSecActivityValue(row.executedValue, unit)} executed · ${row.executedPercentile}th pct`);
  if (row.plannedValue) parts.push(`${formatSecActivityValue(row.plannedValue, unit)} planned · ${row.plannedPercentile}th pct`);
  return `${row.label}: ${parts.join(' · ')}`;
}
