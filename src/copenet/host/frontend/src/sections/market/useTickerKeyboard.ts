import { useEffect, useRef } from 'react';
import { stepRail } from './symbolRailModel';
import { CHART_RANGES, CHART_TIMEFRAMES, type ChartTimeframe } from './chartRanges';
import type { useTickerViewModel } from './useTickerViewModel';

export function useTickerKeyboard(view: ReturnType<typeof useTickerViewModel>, onNavigate: (symbol: string) => void) {
  const { jumpOpen, setTimeframe, setRange, setLogScale, cycleDrawerSnap, railCursor,
    normalized, railEntries, setRailCursor, setJumpSeed, setJumpOpen } = view;
  // ------------------------------------------------------------------ keyboard
  const jumpOpenRef = useRef(jumpOpen);
  jumpOpenRef.current = jumpOpen;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // A focused control owns its own keys: Enter activates a button, a letter jumps a
      // <select>'s options. Only INPUT/TEXTAREA/contentEditable were excluded before, so
      // after any j/k the drawer's own buttons stopped responding to Enter.
      const owned = Boolean(
        target
          && (target.tagName === 'INPUT'
            || target.tagName === 'TEXTAREA'
            || target.tagName === 'SELECT'
            || target.tagName === 'BUTTON'
            || target.tagName === 'A'
            || target.isContentEditable
            || target.closest('[role="dialog"]')),
      );
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (owned || jumpOpenRef.current) return;

      const key = event.key;
      if (key === 'Escape') return;

      // Interval and range are pure client-side filters over bars already in memory, so
      // there is no excuse for them being pointer-only.
      if (key === 'd' || key === 'w' || key === 'm') {
        const value = key.toUpperCase() as ChartTimeframe;
        if (CHART_TIMEFRAMES.includes(value)) { setTimeframe(value); event.preventDefault(); }
        return;
      }
      if (key >= '1' && key <= '5') { setRange(CHART_RANGES[Number(key) - 1]); event.preventDefault(); return; }
      if (key === '0') { setRange('MAX'); event.preventDefault(); return; }
      if (key === 'l') { setLogScale((value) => !value); event.preventDefault(); return; }
      if (key === '\\') { cycleDrawerSnap(); event.preventDefault(); return; }
      if (key === 'j' || key === 'k') {
        const from = railCursor ?? normalized;
        const next = stepRail(railEntries, from, key === 'j' ? 1 : -1);
        if (next) { setRailCursor(next); event.preventDefault(); }
        return;
      }
      if (key === 'Enter' && railCursor && railCursor !== normalized) {
        onNavigate(railCursor);
        event.preventDefault();
        return;
      }
      // Symbol entry is `/`, never a bare letter. Bare-type-to-switch is the nicer reflex
      // right up until you type DIS, WMT or LLY and silently get a different interval
      // instead of a different asset — a wrong action that gives no feedback is worse than
      // one extra keystroke, so the letters belong to the chart and `/` opens the symbol.
      if (key === '/') {
        setJumpSeed('');
        setJumpOpen(true);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [cycleDrawerSnap, normalized, onNavigate, railCursor, railEntries]);

}
