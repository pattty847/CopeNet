import {
  Activity,
  Blocks,
  Bot,
  FlaskConical,
  Home,
  Layers3,
  Wrench,
} from 'lucide-react';
import { AppSection, useAppStore } from '../store/useAppStore';

const NAV_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Home }> = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'workflows', label: 'Workflows', icon: Layers3 },
  { id: 'data-tools', label: 'Data & Tools', icon: Wrench },
  { id: 'observability', label: 'Observability', icon: Activity },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
];

export function SidebarNav() {
  const currentSection = useAppStore((state) => state.currentSection);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const wsStatus = useAppStore((state) => state.wsStatus);

  const systemLabel =
    wsStatus === 'connected' ? 'All systems nominal' : wsStatus === 'connecting' ? 'Connecting to backend' : 'Needs attention';

  return (
    <aside className="flex w-[228px] shrink-0 flex-col rounded-[28px] border border-shell-border bg-shell-sidebar px-4 py-5 shadow-shell">
      <div className="flex items-center gap-3 px-2 pb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-shell-accent/25 bg-shell-panel-strong text-shell-accent">
          <Blocks className="h-5 w-5" />
        </div>
        <div>
          <div className="text-lg font-semibold tracking-tight text-shell-text">CopeNet</div>
          <div className="text-sm text-shell-muted">Agentic workspace</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = currentSection === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setCurrentSection(item.id)}
              className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-medium transition ${
                active
                  ? 'bg-shell-panel-strong text-shell-text shadow-sm'
                  : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
              }`}
            >
              <Icon className={`h-4 w-4 ${active ? 'text-shell-accent' : ''}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-auto space-y-4">
        <div className="rounded-3xl border border-shell-border bg-shell-panel-strong px-4 py-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">System Health</div>
          <div className="text-sm text-shell-text">{systemLabel}</div>
          <div className="mt-3 flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-shell-success'
                  : wsStatus === 'connecting'
                    ? 'bg-shell-accent'
                    : 'bg-shell-error'
              }`}
            />
            <span className="text-xs text-shell-muted">{wsStatus.replace('_', ' ')}</span>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-3xl border border-shell-border bg-shell-panel-strong px-3 py-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-shell-ink text-white">CP</div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-shell-text">Patrick Cope</div>
            <div className="truncate text-xs text-shell-muted">Owner</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
