// The command field, sized for a market bar.
//
// The ticker and the workstation each have one 50px row of chrome, and the shell's command
// row was removed from both to give the chart its height back. This puts the search back
// inside the row that already exists rather than above it — same affordance, no extra band.
//
// It opens the same palette ⌘K does, which already searches symbols and routes to a ticker,
// so it is a real way into an asset and not a decorative box.

import { Command, Search } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

export function MarketSearchField({ placeholder = 'Jump to a ticker, sector, or ask CopeNet…' }: { placeholder?: string }) {
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);

  return (
    <button
      type="button"
      className="tw-search"
      onClick={() => setCommandPaletteOpen(true)}
      title="Search symbols, sessions and commands  (⌘K)"
      aria-label="Open the command palette"
    >
      <Search size={12} className="tw-search__glass" aria-hidden="true" />
      <span className="tw-search__hint">{placeholder}</span>
      <span className="tw-search__key" aria-hidden="true">
        <Command size={9} />K
      </span>
    </button>
  );
}
