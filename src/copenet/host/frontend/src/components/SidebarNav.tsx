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
    wsStatus === 'connected' ? 'All systems nominal' : wsStatus === 'connecting' ? 'Connecting…' : 'Needs attention';

  return (
    <aside className="flex w-[216px] shrink-0 flex-col rounded-[24px] border border-shell-border bg-shell-sidebar px-3 py-4 shadow-shell">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-shell-accent/20 bg-shell-accent-soft text-shell-accent">
          <Blocks className="h-4.5 w-4.5" />
        </div>
        <div>
          <div className="text-[15px] font-semibold tracking-tight text-shell-text">CopeNet</div>
          <div className="text-[11px] text-shell-muted">Agentic workspace</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = currentSection === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setCurrentSection(item.id)}
              className={`group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[13px] font-medium transition-all duration-150 ${
                active
                  ? 'bg-shell-accent-soft text-shell-text'
                  : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
              }`}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-shell-accent" />
              )}
              <Icon className={`h-[15px] w-[15px] transition-colors duration-150 ${active ? 'text-shell-accent' : 'group-hover:text-shell-accent/60'}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="mt-auto space-y-3 pt-4">
        <div className="rounded-2xl border border-shell-border bg-shell-panel px-3 py-3">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">System Health</div>
          <div className="text-[13px] text-shell-text">{systemLabel}</div>
          <div className="mt-2 flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              {wsStatus === 'connected' && (
                <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-shell-success opacity-60" />
              )}
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  wsStatus === 'connected'
                    ? 'bg-shell-success'
                    : wsStatus === 'connecting'
                      ? 'bg-shell-accent'
                      : 'bg-shell-error'
                }`}
              />
            </span>
            <span className="text-[11px] text-shell-muted">{wsStatus.replace('_', ' ')}</span>
          </div>
        </div>

        <div className="flex items-center gap-2.5 rounded-2xl border border-shell-border bg-shell-panel px-3 py-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-shell-ink text-[11px] font-semibold text-white">CP</div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-shell-text">Patrick Cope</div>
            <div className="truncate text-[11px] text-shell-muted">Owner</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
