import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Bot,
  Database,
  FlaskConical,
  Home,
  Layers3,
  Plus,
  Search,
  TrendingUp,
  Video,
  Wrench,
} from 'lucide-react';
import {
  shouldAutoScrollCommandPalette,
  type CommandPaletteInteraction,
} from '../lib/commandPalette';
import { marketTickerNavigationPath } from '../lib/appSectionRouting';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import type { SymbolSearchResult } from '../sections/market/types';

interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  icon: typeof Home;
  action: () => void;
  group: string;
}

export function CommandPalette() {
  const open = useAppStore((state) => state.commandPaletteOpen);
  const setOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const currentSection = useAppStore((state) => state.currentSection);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const sessions = useAppStore((state) => state.sessions);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);

  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [interaction, setInteraction] = useState<CommandPaletteInteraction>('idle');
  const [marketResults, setMarketResults] = useState<SymbolSearchResult[]>([]);
  const [marketSearchLoading, setMarketSearchLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Global ⌘K listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === 'Escape' && open) {
        e.preventDefault();
        setOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, setOpen]);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      setInteraction('idle');
      requestAnimationFrame(() => {
        inputRef.current?.focus();
        if (listRef.current) listRef.current.scrollTop = 0;
      });
    }
  }, [open]);

  useEffect(() => {
    const trimmed = query.trim();
    if (!open || currentSection !== 'market' || trimmed.length < 2) {
      setMarketResults([]);
      setMarketSearchLoading(false);
      return;
    }

    let cancelled = false;
    setMarketSearchLoading(true);
    const timeout = window.setTimeout(() => {
      void wsClient.marketSymbolsSearch(trimmed, 8)
        .then((results) => {
          if (!cancelled) setMarketResults(results);
        })
        .catch(() => {
          if (!cancelled) setMarketResults([]);
        })
        .finally(() => {
          if (!cancelled) setMarketSearchLoading(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [currentSection, open, query]);

  const navItems: PaletteItem[] = useMemo(() => [
    { id: 'nav-home', label: 'Go to Home', icon: Home, action: () => { setCurrentSection('home'); setOpen(false); }, group: 'Navigation' },
    { id: 'nav-agents', label: 'Go to Agents', hint: 'Sessions & chat', icon: Bot, action: () => { setCurrentSection('agents'); setOpen(false); }, group: 'Navigation' },
    { id: 'nav-workflows', label: 'Go to Workflows', icon: Layers3, action: () => { setCurrentSection('workflows'); setOpen(false); }, group: 'Navigation' },
    { id: 'nav-data', label: 'Go to Data & Tools', icon: Wrench, action: () => { setCurrentSection('data-tools'); setOpen(false); }, group: 'Navigation' },
    { id: 'nav-observability', label: 'Go to Observability', icon: Activity, action: () => { setCurrentSection('observability'); setOpen(false); }, group: 'Navigation' },
    { id: 'nav-experiments', label: 'Go to Experiments', icon: FlaskConical, action: () => { setCurrentSection('experiments'); setOpen(false); }, group: 'Navigation' },
  ], [setCurrentSection, setOpen]);

  const actionItems: PaletteItem[] = useMemo(() => [
    {
      id: 'action-new-chat', label: 'New agent session', hint: 'Start a draft', icon: Plus,
      action: () => { wsClient.beginDraft(); setCurrentSection('agents'); setOpen(false); },
      group: 'Actions',
    },
    {
      id: 'action-import-media', label: 'Import media', hint: 'Paste a video URL', icon: Video,
      action: () => { setCurrentSection('data-tools'); setOpen(false); },
      group: 'Actions',
    },
  ], [setCurrentSection, setOpen]);

  const sessionItems: PaletteItem[] = useMemo(() =>
    sessions.filter((s) => !s.archived).slice(0, 8).map((session) => ({
      id: `session-${session.key}`,
      label: session.title || session.key || 'Untitled',
      hint: `${session.provider} · ${session.model || 'default'}`,
      icon: Bot,
      action: () => {
        setActiveSessionKey(session.key);
        setDraftOpen(false);
        setCurrentSection('agents');
        setOpen(false);
      },
      group: 'Recent Sessions',
    })),
  [sessions, setActiveSessionKey, setDraftOpen, setCurrentSection, setOpen]);

  const marketItems: PaletteItem[] = useMemo(() => marketResults.map((result) => ({
    id: `market-symbol-${result.symbol}`,
    label: result.symbol,
    hint: `${result.name}${result.exchange ? ` · ${result.exchange}` : ''}`,
    icon: TrendingUp,
    action: () => {
      window.history.pushState({}, '', marketTickerNavigationPath(result.symbol, window.location.pathname, window.location.search));
      window.dispatchEvent(new PopStateEvent('popstate'));
      setOpen(false);
    },
    group: 'Market symbols',
  })), [marketResults, setOpen]);

  const allItems = useMemo(() => [...marketItems, ...actionItems, ...navItems, ...sessionItems], [marketItems, actionItems, navItems, sessionItems]);

  const filtered = useMemo(() => {
    if (!query.trim()) return allItems;
    const q = query.toLowerCase();
    return allItems.filter((item) =>
      item.label.toLowerCase().includes(q) ||
      (item.hint && item.hint.toLowerCase().includes(q)) ||
      item.group.toLowerCase().includes(q)
    );
  }, [query, allItems]);

  // Keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setInteraction('keyboard');
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setInteraction('keyboard');
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filtered[selectedIndex]) {
      e.preventDefault();
      filtered[selectedIndex].action();
    }
  }, [filtered, selectedIndex]);

  // Keep selection in view
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    if (!shouldAutoScrollCommandPalette({ query, interaction })) {
      return;
    }
    const el = listRef.current?.children[selectedIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [interaction, query, selectedIndex]);

  if (!open) return null;

  // Group the filtered items
  const groups: Record<string, PaletteItem[]> = {};
  for (const item of filtered) {
    (groups[item.group] ??= []).push(item);
  }

  let flatIndex = 0;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-shell-ink/40 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Palette */}
      <div className="animate-scale-pop relative w-full max-w-[560px] rounded-2xl border border-shell-border bg-shell-panel shadow-shell-xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-shell-border px-4 py-3">
          <Search className="h-4 w-4 text-shell-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setInteraction('query');
              setQuery(e.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder={currentSection === 'market' ? 'Search a ticker, company, or command…' : 'Search commands, sessions, or navigate…'}
            className="flex-1 bg-transparent text-[14px] text-shell-text outline-none placeholder:text-shell-muted/60"
          />
          <kbd className="rounded-md border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px] font-semibold text-shell-muted">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[360px] overflow-auto py-2">
          {marketSearchLoading && currentSection === 'market' && query.trim().length >= 2 && (
            <div className="px-4 py-2 text-[11px] text-shell-muted">Searching market symbols…</div>
          )}
          {filtered.length === 0 && !marketSearchLoading ? (
            <div className="px-4 py-6 text-center text-[13px] text-shell-muted">
              No results for "{query}"
            </div>
          ) : (
            Object.entries(groups).map(([group, items]) => (
              <div key={group}>
                <div className="px-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-shell-muted">
                  {group}
                </div>
                {items.map((item) => {
                  const Icon = item.icon;
                  const thisIndex = flatIndex++;
                  const isSelected = thisIndex === selectedIndex;

                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={item.action}
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left transition-colors duration-75 ${
                        isSelected
                          ? 'bg-shell-accent-soft text-shell-text'
                          : 'text-shell-text hover:bg-shell-panel-strong'
                      }`}
                    >
                      <Icon className={`h-4 w-4 shrink-0 ${isSelected ? 'text-shell-accent' : 'text-shell-muted'}`} />
                      <div className="min-w-0 flex-1">
                        <span className="text-[13px] font-medium">{item.label}</span>
                        {item.hint && (
                          <span className="ml-2 text-[11px] text-shell-muted">{item.hint}</span>
                        )}
                      </div>
                      {isSelected && (
                        <kbd className="rounded-md border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px] font-semibold text-shell-muted">
                          ↵
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hints */}
        <div className="flex items-center gap-4 border-t border-shell-border px-4 py-2 text-[10px] text-shell-muted">
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1 py-px font-semibold">↑↓</kbd>
            Navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1 py-px font-semibold">↵</kbd>
            Select
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1 py-px font-semibold">esc</kbd>
            Close
          </span>
        </div>
      </div>
    </div>
  );
}
