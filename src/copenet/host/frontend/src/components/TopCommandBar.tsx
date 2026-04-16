import { Bell, BookOpen, Command, Search, Sparkles, UserCircle2 } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { ThemeToggle } from './ThemeToggle';

const SECTION_HINTS = {
  home: 'Ask CopeNet to surface a workspace, run a playbook, or jump back into a session…',
  agents: 'Search sessions, pinned agents, or a run you want to resume…',
  workflows: 'Find a workflow, runbook, or recurring operation…',
  'data-tools': 'Search data feeds, knowledge bases, or tool integrations…',
  observability: 'Search traces, run logs, or blocked tool events…',
  experiments: 'Search comparisons, prompts, or benchmark runs…',
} as const;

const iconBtn =
  'inline-flex h-9 w-9 items-center justify-center rounded-xl border border-shell-border bg-shell-panel text-shell-muted transition-all duration-150 hover:border-shell-border-strong hover:text-shell-text hover:shadow-shell';

export function TopCommandBar() {
  const currentSection = useAppStore((state) => state.currentSection);
  const activeRunId = useAppStore((state) => state.activeRunId);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);

  return (
    <div className="relative flex w-full items-center justify-center">
      <button
        type="button"
        onClick={() => setCommandPaletteOpen(true)}
        className="relative w-full max-w-[720px] text-left"
      >
          <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-shell-muted" />
          <div
            className="flex h-10 w-full items-center rounded-xl border border-shell-border bg-shell-panel pl-10 pr-22 text-[13px] text-shell-muted/70 transition-all duration-150 hover:border-shell-border-strong hover:shadow-shell"
          >
            {SECTION_HINTS[currentSection]}
          </div>
          <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 rounded-lg border border-shell-border bg-shell-panel-strong px-2 py-0.5 text-[10px] font-semibold text-shell-muted">
            <Command className="h-2.5 w-2.5" />
            <span>K</span>
          </div>
      </button>

      <div className="absolute right-0 top-1/2 flex -translate-y-1/2 items-center justify-end gap-1.5">
        <button type="button" className={iconBtn} title="Alerts">
          <Bell className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={iconBtn} title="Notebook">
          <BookOpen className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={iconBtn} title="Inspiration">
          <Sparkles className="h-3.5 w-3.5 text-shell-accent" />
        </button>
        <ThemeToggle />
        <button type="button" className={iconBtn} title="Profile">
          <UserCircle2 className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
