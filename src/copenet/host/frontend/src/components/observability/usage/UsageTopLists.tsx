import { formatCount, formatRate, formatTokens } from '../../../runtime/usageModel';
import type { UsageModelRow, UsageProviderRow, UsageToolRow } from '../../../types/backend';
import { UsageEmpty, UsagePanel } from './usageChrome';

/** Top models, providers and tools. Each row carries its own proportion bar so the
 *  ranking is readable without reading every number. */
export function UsageTopLists({
  models,
  providers,
  tools,
}: {
  models: UsageModelRow[];
  providers: UsageProviderRow[];
  tools: UsageToolRow[];
}) {
  const modelPeak = models[0]?.totalTokens ?? 0;
  const providerPeak = providers[0]?.totalTokens ?? 0;
  const toolPeak = tools[0]?.calls ?? 0;

  return (
    <div className="grid gap-2 lg:grid-cols-3">
      <UsagePanel title="Top models" subtitle="By tokens">
        {models.length === 0 ? (
          <UsageEmpty>No runs in this window.</UsageEmpty>
        ) : (
          <ol className="space-y-1.5">
            {models.map((row) => (
              <RankedRow
                key={`${row.provider}/${row.model}`}
                name={row.model}
                note={row.provider}
                value={formatTokens(row.totalTokens)}
                detail={`${formatCount(row.runs)} runs · ${formatRate(row.cacheHitRate)} cached`}
                share={modelPeak > 0 ? row.totalTokens / modelPeak : 0}
              />
            ))}
          </ol>
        )}
      </UsagePanel>

      <UsagePanel title="Top providers" subtitle="By tokens">
        {providers.length === 0 ? (
          <UsageEmpty>No runs in this window.</UsageEmpty>
        ) : (
          <ol className="space-y-1.5">
            {providers.map((row) => (
              <RankedRow
                key={row.provider}
                name={row.provider}
                note={`${formatCount(row.modelCalls)} model calls`}
                value={formatTokens(row.totalTokens)}
                detail={
                  row.runsWithUsage < row.runs
                    ? `${formatCount(row.runsWithUsage)} of ${formatCount(row.runs)} runs reported usage`
                    : `${formatCount(row.runs)} runs · ${formatRate(row.errorRate, 1)} errors`
                }
                share={providerPeak > 0 ? row.totalTokens / providerPeak : 0}
              />
            ))}
          </ol>
        )}
      </UsagePanel>

      <UsagePanel title="Top tools" subtitle="By calls">
        {tools.length === 0 ? (
          <UsageEmpty>No tool calls in this window.</UsageEmpty>
        ) : (
          <ol className="space-y-1.5">
            {tools.map((row) => (
              <RankedRow
                key={row.toolId}
                name={row.toolId}
                note={`${formatCount(row.runs)} runs`}
                value={formatCount(row.calls)}
                detail={
                  row.failures + row.blocked > 0
                    ? `${formatCount(row.failures)} failed · ${formatCount(row.blocked)} blocked`
                    : 'No failures'
                }
                share={toolPeak > 0 ? row.calls / toolPeak : 0}
                tone={row.failures + row.blocked > 0 ? 'warning' : 'default'}
              />
            ))}
          </ol>
        )}
      </UsagePanel>
    </div>
  );
}

function RankedRow({
  name,
  note,
  value,
  detail,
  share,
  tone = 'default',
}: {
  name: string;
  note: string;
  value: string;
  detail: string;
  share: number;
  tone?: 'default' | 'warning';
}) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-mono text-[11px] text-shell-text" title={name}>
          {name}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-shell-text">{value}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-[2px] bg-shell-bg">
        <div
          className="h-full rounded-[2px]"
          style={{ width: `${Math.max(share * 100, 1.5)}%`, background: 'var(--usage-series-output)' }}
        />
      </div>
      <p className={`mt-0.5 text-[9.5px] ${tone === 'warning' ? 'text-shell-error' : 'text-shell-muted'}`}>
        {note} · {detail}
      </p>
    </li>
  );
}
