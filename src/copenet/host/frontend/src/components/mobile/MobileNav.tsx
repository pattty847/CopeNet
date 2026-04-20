import { Activity, Bot, FlaskConical, Home, Layers3, MoreHorizontal, Wrench } from 'lucide-react';
import { useAppStore, type AppSection } from '../../store/useAppStore';
import { MobileSheet } from './MobileSheet';

const PRIMARY_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Home }> = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'agents', label: 'Agents', icon: Bot },
  { id: 'workflows', label: 'Workflows', icon: Layers3 },
  { id: 'data-tools', label: 'Media', icon: Wrench },
];

const MORE_ITEMS: Array<{ id: AppSection; label: string; icon: typeof Activity }> = [
  { id: 'observability', label: 'Observability', icon: Activity },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical },
];

const SECTION_TITLES: Record<AppSection, string> = {
  home: 'Home',
  agents: 'Agents',
  workflows: 'Workflows',
  'data-tools': 'Data & Tools',
  observability: 'Observability',
  experiments: 'Experiments',
};

export function MobileTopBar() {
  const currentSection = useAppStore((state) => state.currentSection);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const setMobileOverflowOpen = useAppStore((state) => state.setMobileOverflowOpen);

  return (
    <div className="flex items-center justify-between gap-3 border-b border-shell-border px-4 py-3 lg:hidden">
      <div className="min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">CopeNet</div>
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[17px] font-semibold text-shell-text">{SECTION_TITLES[currentSection]}</h1>
          <span className="inline-flex items-center gap-1 rounded-full bg-shell-panel-strong px-2 py-0.5 text-[10px] font-medium text-shell-muted">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-shell-success'
                  : wsStatus === 'connecting'
                  ? 'bg-shell-accent'
                  : 'bg-shell-error'
              }`}
            />
            {wsStatus === 'connected' ? 'live' : wsStatus === 'connecting' ? 'linking' : 'retrying'}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setCommandPaletteOpen(true)}
          className="inline-flex h-10 items-center rounded-xl border border-shell-border bg-shell-panel px-3 text-[12px] font-medium text-shell-muted"
        >
          Search
        </button>
        <button
          type="button"
          onClick={() => setMobileOverflowOpen(true)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-shell-border bg-shell-panel text-shell-text"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function MobileBottomNav() {
  const currentSection = useAppStore((state) => state.currentSection);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const mobileOverflowOpen = useAppStore((state) => state.mobileOverflowOpen);
  const setMobileOverflowOpen = useAppStore((state) => state.setMobileOverflowOpen);

  return (
    <>
      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-shell-border bg-shell-panel/95 px-2 pb-[calc(env(safe-area-inset-bottom)+0.55rem)] pt-2 shadow-shell-xl backdrop-blur lg:hidden">
        <div className="grid grid-cols-5 gap-1">
          {PRIMARY_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = currentSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setCurrentSection(item.id)}
                aria-label={item.label}
                title={item.label}
                className={`flex items-center justify-center rounded-2xl px-2 py-2.5 ${
                  active ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setMobileOverflowOpen(true)}
            aria-label="More"
            title="More"
            className={`flex items-center justify-center rounded-2xl px-2 py-2.5 ${
              currentSection === 'observability' || currentSection === 'experiments' ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted'
            }`}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </nav>

      <MobileSheet open={mobileOverflowOpen} onClose={() => setMobileOverflowOpen(false)} title="More">
        <div className="space-y-2 px-3 py-3">
          {MORE_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = currentSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setCurrentSection(item.id);
                  setMobileOverflowOpen(false);
                }}
                className={`flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left ${
                  active ? 'border-shell-accent/40 bg-shell-accent-soft text-shell-text' : 'border-shell-border bg-shell-bg text-shell-text'
                }`}
              >
                <Icon className="h-4 w-4 text-shell-accent" />
                <span className="text-[14px] font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>
      </MobileSheet>
    </>
  );
}
