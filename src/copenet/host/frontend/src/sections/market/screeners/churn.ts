// Which names entered or left each screen since the previous complete observation. Runs
// store their full row sets, so this is a set difference and nothing more; it says
// nothing about why a name moved.
import type { ScreenerRun, ScreenerState } from './types';

export type ScreenChurn = { added: Set<string>; dropped: number };

export function screenChurn(latest: ScreenerRun, previous: ScreenerRun | null): Record<string, ScreenChurn> {
  const result: Record<string, ScreenChurn> = {};
  for (const screen of latest.screens) {
    const before = new Set(previous?.screens.find((item) => item.id === screen.id)?.rows.map((row) => row.symbol) ?? []);
    const now = new Set(screen.rows.map((row) => row.symbol));
    result[screen.id] = previous
      ? { added: new Set([...now].filter((symbol) => !before.has(symbol))), dropped: [...before].filter((symbol) => !now.has(symbol)).length }
      : { added: new Set(), dropped: 0 };
  }
  return result;
}

/** The complete run that precedes `run` in the saved history, if any. */
export function previousRunId(history: ScreenerState['history'], run: ScreenerRun): string | null {
  const ordered = [...history]
    .filter((item) => item.status === 'complete')
    .sort((a, b) => b.finishedAt.localeCompare(a.finishedAt));
  const index = ordered.findIndex((item) => item.id === run.id);
  if (index < 0) return null;
  return ordered[index + 1]?.id ?? null;
}
