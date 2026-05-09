import {
  Activity,
  Blocks,
  Bot,
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
      className={`shell-sidebar flex shrink-0 flex-col rounded-[24px] border border-shell-border bg-shell-sidebar py-4 shadow-shell transition-[width,padding] duration-200 ${
        primaryNavCollapsed ? 'w-[78px] px-2.5' : 'w-[216px] px-3'
      }`}
    >
      {/* Brand */}
      <div className={`flex items-center px-2 pb-5 ${primaryNavCollapsed ? 'justify-center' : 'justify-between gap-2.5'}`}>
        <div className={`flex items-center ${primaryNavCollapsed ? 'justify-center' : 'gap-2.5'}`}>
          <button
            type="button"
            onClick={() => {
              if (primaryNavCollapsed) setPrimaryNavCollapsed(false);
            }}
            disabled={!primaryNavCollapsed}
            className={`flex h-9 w-9 items-center justify-center rounded-xl border border-shell-accent/20 bg-shell-accent-soft text-shell-accent ${
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
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-shell-accent/20 bg-shell-accent-soft text-shell-accent">
            <button
              type="button"
              onClick={() => setPrimaryNavCollapsed(true)}
              className="flex h-full w-full items-center justify-center rounded-xl transition-colors hover:bg-shell-accent/10"
              title="Collapse navigation"
              aria-label="Collapse navigation"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        )}
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
              title={primaryNavCollapsed ? item.label : undefined}
              className={`group relative flex rounded-xl py-2 text-left text-[13px] font-medium transition-all duration-150 ${
                primaryNavCollapsed ? 'justify-center px-2.5' : 'items-center gap-2.5 px-3'
              } ${
                active
                  ? 'bg-shell-accent-soft text-shell-text'
                  : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
              }`}
            >
              {active && (
                <>
                  <span className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r-full bg-shell-accent shadow-[0_0_10px_var(--color-shell-accent)]" />
                  <span className="pointer-events-none absolute inset-y-1 right-2 w-1/3 rounded-xl bg-shell-accent-glow blur-md" />
                </>
              )}
              <Icon className={`h-[15px] w-[15px] transition-colors duration-150 ${active ? 'text-shell-accent' : 'group-hover:text-shell-accent/60'}`} />
              {!primaryNavCollapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {currentSection === 'agents' && (
        <div className="pt-3">
          <button
            type="button"
            onClick={() => setSessionDrawerOpen(!sessionDrawerOpen)}
            title="Open Resume Session"
            aria-label="Open Resume Session"
            className={`group relative flex w-full rounded-xl py-2 text-left text-[13px] font-medium transition-all duration-150 ${
              primaryNavCollapsed ? 'justify-center px-2.5' : 'items-center gap-2.5 px-3'
            } ${
              sessionDrawerOpen
                ? 'bg-shell-accent-soft text-shell-text'
                : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
            }`}
          >
            {sessionDrawerOpen && (
              <>
                <span className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r-full bg-shell-accent shadow-[0_0_10px_var(--color-shell-accent)]" />
                <span className="pointer-events-none absolute inset-y-1 right-2 w-1/3 rounded-xl bg-shell-accent-glow blur-md" />
              </>
            )}
            <PanelLeft className={`h-[15px] w-[15px] transition-colors duration-150 ${sessionDrawerOpen ? 'text-shell-accent' : 'group-hover:text-shell-accent/60'}`} />
            {!primaryNavCollapsed && <span>Resume Session</span>}
          </button>
        </div>
      )}

      {/* Footer */}
      <div className="mt-auto space-y-3 pt-4">
        <div className={`rounded-2xl border border-shell-border bg-shell-panel ${primaryNavCollapsed ? 'px-2 py-2.5' : 'px-3 py-3'}`}>
          {!primaryNavCollapsed && (
            <>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">System Health</div>
              <div className="text-[13px] text-shell-text">{systemLabel}</div>
            </>
          )}
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
            {!primaryNavCollapsed && <span className="text-[11px] text-shell-muted">{wsStatus.replace('_', ' ')}</span>}
          </div>
        </div>

        <div
          className={`flex rounded-2xl border border-shell-border bg-shell-panel ${primaryNavCollapsed ? 'justify-center px-2 py-2.5' : 'items-center gap-2.5 px-3 py-2.5'}`}
          title={primaryNavCollapsed ? 'Patrick Cope · Owner' : undefined}
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-shell-ink text-[11px] font-semibold text-white">CP</div>
          {!primaryNavCollapsed && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-shell-text">Patrick Cope</div>
              <div className="truncate text-[11px] text-shell-muted">Owner</div>
            </div>
          )}
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
