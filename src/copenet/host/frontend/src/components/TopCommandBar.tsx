import { Bell, BookOpen, Search, Sparkles, UserCircle2 } from 'lucide-react';
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

export function TopCommandBar() {
  const currentSection = useAppStore((state) => state.currentSection);
  const activeRunId = useAppStore((state) => state.activeRunId);

  return (
    <div className="relative flex w-full items-center justify-center">
      <div className="relative w-full max-w-[760px]">
          <Search className="pointer-events-none absolute left-5 top-1/2 h-4 w-4 -translate-y-1/2 text-shell-muted" />
          <input
            type="text"
            readOnly
            value=""
            placeholder={SECTION_HINTS[currentSection]}
            className="h-12 w-full rounded-full border border-shell-border bg-shell-panel-strong pl-12 pr-24 text-sm text-shell-text outline-none transition placeholder:text-shell-muted/90 hover:border-shell-border-strong"
          />
          <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 rounded-full border border-shell-border bg-shell-panel px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">
            {activeRunId ? 'Live' : 'Quick Find'}
          </div>
      </div>

      <div className="absolute right-0 top-1/2 flex -translate-y-1/2 items-center justify-end gap-3">
        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-panel-strong text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
          title="Alerts"
        >
          <Bell className="h-4 w-4" />
        </button>

        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-panel-strong text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
          title="Notebook"
        >
          <BookOpen className="h-4 w-4" />
        </button>

        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-panel-strong text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
          title="Inspiration"
        >
          <Sparkles className="h-4 w-4 text-shell-accent" />
        </button>

        <ThemeToggle />

        <button
          type="button"
          className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-panel-strong text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
          title="Profile"
        >
          <UserCircle2 className="h-6 w-6" />
        </button>
      </div>
    </div>
  );
}
