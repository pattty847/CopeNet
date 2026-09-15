import { useCallback, useState } from 'react';
import { RunExplorer } from './observability/RunExplorer';
import { UsageView } from './observability/usage/UsageView';

/** Observability has two views over the same durable run records: the run
 *  inspector answers "what happened in THIS run", Usage answers "what has all of
 *  it added up to". The section is a route (`/observability?view=usage`) so a
 *  reload and a shared link land where the operator was.
 *
 *  This file is the switch only — each view owns its own `SectionHead`, because
 *  the header actions differ (trace capture on one, range and bench filter on the
 *  other) and a shared header would have to know about both. */
const VIEWS = [
  { id: 'runs', label: 'Runs' },
  { id: 'usage', label: 'Usage' },
] as const;

type ObservabilityView = (typeof VIEWS)[number]['id'];

function viewFromUrl(): ObservabilityView {
  return new URLSearchParams(window.location.search).get('view') === 'usage' ? 'usage' : 'runs';
}

export function ObservabilityPage() {
  const [view, setView] = useState<ObservabilityView>(viewFromUrl);

  const selectView = useCallback((next: ObservabilityView) => {
    setView(next);
    const url = new URL(window.location.href);
    if (next === 'runs') url.searchParams.delete('view');
    else url.searchParams.set('view', next);
    window.history.replaceState({}, '', url);
  }, []);

  const tabs = (
    <div className="flex items-center gap-0.5 rounded-lg border border-shell-border bg-shell-panel p-0.5">
      {VIEWS.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => selectView(option.id)}
          aria-pressed={view === option.id}
          className={`focus-ring rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
            view === option.id ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted hover:text-shell-text'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );

  return view === 'usage' ? <UsageView tabs={tabs} /> : <RunExplorer tabs={tabs} />;
}
