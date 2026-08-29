import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts';
import { formatFinancialDate } from './financialOverlay';
import { formatFinancialStoryValue, type FinancialChartRow, type FinancialStory } from './financialExplorer';

export function FinancialExplorerChart({
  rows,
  story,
  visibleMetrics,
}: {
  rows: FinancialChartRow[];
  story: FinancialStory;
  visibleMetrics: Set<string>;
}) {
  const common = (
    <>
      <CartesianGrid vertical={false} stroke="rgba(254,252,244,.08)" />
      <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#777168', fontSize: 10 }} minTickGap={14} />
      <YAxis axisLine={false} tickLine={false} width={64} tick={{ fill: '#777168', fontSize: 9.5 }} tickFormatter={(value: number) => formatFinancialStoryValue(value, story.valueKind, true)} />
      <Tooltip cursor={{ fill: 'rgba(254,252,244,.035)', stroke: 'rgba(254,252,244,.08)' }} content={(props) => <FinancialChartTooltip {...props} story={story} />} />
      <ReferenceLine y={0} stroke="rgba(254,252,244,.18)" />
    </>
  );

  if (story.chart === 'bar') {
    return (
      <div className="financial-explorer-chart" aria-label={`${story.label} financial history chart`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={260} minHeight={280}>
          <BarChart data={rows} margin={{ top: 10, right: 12, left: 2, bottom: 0 }} barGap={2} barCategoryGap="18%" accessibilityLayer>
            {common}
            {story.metrics.map((metric) => visibleMetrics.has(metric.id) ? <Bar key={metric.id} dataKey={metric.id} name={metric.shortLabel} fill={metric.color} radius={[2, 2, 0, 0]} maxBarSize={28} isAnimationActive={false} /> : null)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="financial-explorer-chart" aria-label={`${story.label} financial history chart`}>
      <ResponsiveContainer width="100%" height="100%" minWidth={260} minHeight={280}>
        <LineChart data={rows} margin={{ top: 10, right: 18, left: 2, bottom: 0 }} accessibilityLayer>
          {common}
          {story.metrics.map((metric) => visibleMetrics.has(metric.id) ? (
            <Line key={metric.id} dataKey={metric.id} name={metric.shortLabel} type="monotone" stroke={metric.color} strokeWidth={2} dot={{ r: 2.5, fill: '#080809', strokeWidth: 1.5 }} activeDot={{ r: 4, fill: metric.color, stroke: '#080809', strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
          ) : null)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FinancialChartTooltip({ active, label, payload, story }: TooltipContentProps<number, string> & { story: FinancialStory }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as FinancialChartRow | undefined;
  return (
    <div className="financial-chart-tooltip">
      <strong>{label}</strong>
      {payload.map((entry) => {
        const metric = story.metrics.find((candidate) => candidate.id === entry.dataKey);
        const value = typeof entry.value === 'number' ? entry.value : null;
        const meta = metric && row ? row._meta[metric.id] : null;
        if (!metric || value == null) return null;
        return (
          <div key={metric.id}>
            <span><i style={{ background: metric.color }} />{metric.shortLabel}</span>
            <b>{formatFinancialStoryValue(value, story.valueKind)}</b>
            {meta?.availableAt ? <small>Known {formatFinancialDate(meta.availableAt)} · {meta.derived ? 'derived' : 'reported'}</small> : null}
          </div>
        );
      })}
    </div>
  );
}
