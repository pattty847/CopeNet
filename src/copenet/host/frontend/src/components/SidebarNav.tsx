import {
  Activity,
  Blocks,
  Bot,
  CandlestickChart,
  ChevronLeft,
  FlaskConical,
  Home,
  Layers3,
  PanelLeft,
  Wrench,
} from 'lucide-react';
import { AppSection, useAppStore } from '../store/useAppStore';
import { ThemeToggle } from './ThemeToggle';

const NAV_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Home }> = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'market', label: 'Market', icon: CandlestickChart },
  { id: 'workflows', label: 'Workflows', icon: Layers3 },
  { id: 'data-tools', label: 'Data & Tools', icon: Wrench },
  { id: 'observability', label: 'Observability', icon: Activity },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
];

export function SidebarNav() {
  const currentSection = useAppStore((state) => state.currentSection);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const primaryNavCollapsed = useAppStore((state) => state.primaryNavCollapsed);
  const setPrimaryNavCollapsed = useAppStore((state) => state.setPrimaryNavCollapsed);
  const sessionDrawerOpen = useAppStore((state) => state.sessionDrawerOpen);
  const setSessionDrawerOpen = useAppStore((state) => state.setSessionDrawerOpen);

  const systemLabel =
    wsStatus === 'connected' ? 'All systems nominal' : wsStatus === 'connecting' ? 'Connecting…' : 'Needs attention';

  return (
    <aside
      className={`shell-sidebar flex shrink-0 flex-col border-r border-shell-border bg-shell-sidebar transition-[width] duration-200 ${
        primaryNavCollapsed ? 'w-16' : 'w-[216px]'
      }`}
    >
      {/* Brand */}
      <div className={`flex h-[57px] shrink-0 items-center border-b border-shell-border px-3 ${primaryNavCollapsed ? 'justify-center' : 'justify-between gap-2.5'}`}>
        <div className={`flex items-center ${primaryNavCollapsed ? 'justify-center' : 'gap-2.5'}`}>
          <button
            type="button"
            onClick={() => {
              if (primaryNavCollapsed) setPrimaryNavCollapsed(false);
            }}
            disabled={!primaryNavCollapsed}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-shell-accent/20 bg-shell-accent-soft text-shell-accent ${
              primaryNavCollapsed ? 'transition-colors hover:bg-shell-accent/10' : ''
            }`}
            title={primaryNavCollapsed ? 'Expand navigation' : undefined}
            aria-label={primaryNavCollapsed ? 'Expand navigation' : undefined}
          >
            <Blocks className="h-4.5 w-4.5" />
          </button>
          {!primaryNavCollapsed && (
            <div>
              <div className="text-[15px] font-semibold tracking-tight text-shell-text">CopeNet</div>
              <div className="text-[11px] text-shell-muted">Agentic workspace</div>
            </div>
          )}
        </div>
        {!primaryNavCollapsed && (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-shell-accent/20 bg-shell-accent-soft text-shell-accent">
            <button
              type="button"
              onClick={() => setPrimaryNavCollapsed(true)}
              className="flex h-full w-full items-center justify-center rounded-sm transition-colors hover:bg-shell-accent/10"
              title="Collapse navigation"
              aria-label="Collapse navigation"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex flex-col py-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = currentSection === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setCurrentSection(item.id)}
              title={primaryNavCollapsed ? item.label : undefined}
              className={`group relative flex min-h-10 items-center py-2 text-left text-[13px] font-medium transition-colors duration-150 ${
                primaryNavCollapsed ? 'justify-center' : 'gap-2.5 px-3'
              } ${
                active
                  ? 'bg-shell-accent-soft text-shell-text'
                  : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
              }`}
            >
              {active && (
                <span className="absolute inset-y-0 left-0 w-0.5 bg-shell-accent" />
              )}
              <Icon className={`h-[15px] w-[15px] transition-colors duration-150 ${active ? 'text-shell-accent' : 'group-hover:text-shell-accent/60'}`} />
              {!primaryNavCollapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {currentSection === 'agents' && (
        <div className="border-t border-shell-border py-2">
          <button
            type="button"
            onClick={() => setSessionDrawerOpen(!sessionDrawerOpen)}
            title="Open Resume Session"
            aria-label="Open Resume Session"
            className={`group relative flex min-h-10 w-full items-center py-2 text-left text-[13px] font-medium transition-colors duration-150 ${
              primaryNavCollapsed ? 'justify-center' : 'gap-2.5 px-3'
            } ${
              sessionDrawerOpen
                ? 'bg-shell-accent-soft text-shell-text'
                : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
            }`}
          >
            {sessionDrawerOpen && (
              <span className="absolute inset-y-0 left-0 w-0.5 bg-shell-accent" />
            )}
            <PanelLeft className={`h-[15px] w-[15px] transition-colors duration-150 ${sessionDrawerOpen ? 'text-shell-accent' : 'group-hover:text-shell-accent/60'}`} />
            {!primaryNavCollapsed && <span>Resume Session</span>}
          </button>
        </div>
      )}

      {/* Footer */}
      <div className="mt-auto">
        <div className="border-t border-shell-border px-3 py-3" title={primaryNavCollapsed ? systemLabel : undefined}>
          {!primaryNavCollapsed && (
            <>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">System Health</div>
              <div className="text-[13px] text-shell-text">{systemLabel}</div>
            </>
          )}
          <div className={`flex items-center gap-2 ${primaryNavCollapsed ? 'justify-center' : 'mt-2'}`}>
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
            {!primaryNavCollapsed && <span className="text-[11px] text-shell-muted">{wsStatus.replace('_', ' ')}</span>}
          </div>
        </div>

        <div
          className={`flex items-center border-t border-shell-border px-3 py-2.5 ${primaryNavCollapsed ? 'flex-col gap-2' : 'gap-2.5'}`}
          title={primaryNavCollapsed ? 'Local Operator' : undefined}
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-shell-ink text-[11px] font-semibold text-white">LO</div>
          {!primaryNavCollapsed && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-shell-text">Local Operator</div>
              <div className="truncate text-[11px] text-shell-muted">Private workspace</div>
            </div>
          )}
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
