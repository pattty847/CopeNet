import { useEffect, useRef, useState } from 'react';
import { Bell, BookOpen, Command, Search, Sparkles, UserCircle2 } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { marketClock } from './home/deskModel';
import { ThemeToggle } from './ThemeToggle';
import { AccountMenu } from './AccountMenu';

const SECTION_HINTS = {
  home: 'Jump to a ticker, sector, or ask CopeNet…',
  agents: 'Search sessions, pinned agents, or a run you want to resume…',
  market: 'Jump to a ticker, sector, or the daily market read…',
  workflows: 'Find a workflow, runbook, or recurring operation…',
  'data-tools': 'Search data feeds, knowledge bases, or tool integrations…',
  observability: 'Search traces, run logs, or blocked tool events…',
  experiments: 'Search comparisons, prompts, or benchmark runs…',
} as const;

const iconBtn =
  'shell-icon-btn inline-flex h-9 w-9 items-center justify-center rounded-xl border border-shell-border bg-shell-panel text-shell-muted transition-all duration-150 hover:border-shell-border-strong hover:text-shell-text hover:shadow-shell';

/** The exchange clock belongs in the chrome, not on one page: whether the market is open
 *  changes how every number in the app should be read, and it is the first thing the
 *  operator checks. It ticks on its own — a clock rendered once and left is a wrong clock. */
function MarketStatus() {
  const [clock, setClock] = useState(() => marketClock());

  useEffect(() => {
    const timer = window.setInterval(() => setClock(marketClock()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const open = clock.phase === 'open';
  const tone = open ? 'text-shell-success' : clock.phase === 'closed' ? 'text-shell-muted' : 'text-shell-accent';

  return (
    <div className="flex shrink-0 items-center gap-3">
      <div className="text-right leading-tight">
        <div className="text-[11px] text-shell-muted">
          {new Date().toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
        </div>
        <div className="font-mono text-[12px] font-medium tabular-nums text-shell-text">{clock.time}</div>
      </div>
      <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-[11px] font-medium ${tone}`}>
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
        {clock.label}
      </span>
    </div>
  );
}

export function TopCommandBar() {
  const currentSection = useAppStore((state) => state.currentSection);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);

  const [accountOpen, setAccountOpen] = useState(false);
  const accountButtonRef = useRef<HTMLButtonElement | null>(null);

  return (
    <div className="shell-top-command-bar relative flex w-full items-center justify-center">
      <button
        type="button"
        onClick={() => setCommandPaletteOpen(true)}
        className="shell-command-field relative w-full text-left"
      >
          <Search className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-shell-muted" />
          <div
            className="flex h-10 w-full items-center rounded-xl border border-shell-border bg-shell-panel pl-10 pr-22 text-[13px] text-shell-muted/70 transition-all duration-150 hover:border-shell-border-strong hover:shadow-shell"
          >
            {SECTION_HINTS[currentSection]}
          </div>
          <div className="shell-command-key pointer-events-none absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1.5 rounded-lg border border-shell-border bg-shell-panel-strong px-2 py-0.5 text-[10px] font-semibold text-shell-muted">
            <Command className="h-2.5 w-2.5" />
            <span>K</span>
          </div>
      </button>

      <div className="shell-command-actions absolute right-0 top-1/2 flex -translate-y-1/2 items-center justify-end gap-1.5">
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
        <button
          ref={accountButtonRef}
          type="button"
          className={iconBtn}
          title="Account & gateway token"
          aria-expanded={accountOpen}
          onClick={() => setAccountOpen((value) => !value)}
        >
          <UserCircle2 className="h-5 w-5" />
        </button>
        <AccountMenu anchorRef={accountButtonRef} open={accountOpen} onClose={() => setAccountOpen(false)} />
        <span className="mx-1 h-6 w-px bg-shell-border" />
        <MarketStatus />
      </div>
    </div>
  );
}
