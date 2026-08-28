import { Command, Search, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import type { WatchlistItem } from './types';

export function TickerAssetSwitcher({
  currentSymbol,
  items,
  onSearch,
  onSelect,
}: {
  currentSymbol: string;
  items: WatchlistItem[];
  onSearch: () => void;
  onSelect: (symbol: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLButtonElement>(null);
  const visibleItems = items.filter((item) => item.symbol !== currentSymbol).slice(0, 12);
  const close = (restoreFocus: boolean) => {
    setOpen(false);
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => searchRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  return (
    <div className="ticker-asset-switcher">
      <button ref={triggerRef} type="button" className="ticker-command-search" aria-haspopup="dialog" aria-expanded={open} onClick={() => open ? close(true) : setOpen(true)}>
        <Search size={13} aria-hidden="true" /><span>Switch</span><kbd>⌘K</kbd>
      </button>
      <MarketFloatingPopover anchorRef={triggerRef} open={open} onClose={() => close(true)} className="ticker-switcher-popover" width={340}>
        <div className="ticker-switcher-panel" role="dialog" aria-label="Switch asset">
          <header><div><strong>Switch asset</strong><span>{visibleItems.length ? 'Active watchlist' : 'Search the market universe'}</span></div><button type="button" aria-label="Close asset switcher" onClick={() => close(true)}><X size={14} /></button></header>
          <button ref={searchRef} type="button" className="ticker-switcher-search" onClick={() => { close(false); onSearch(); }}><Search size={14} /><span>Search ticker or company</span><kbd><Command size={11} />K</kbd></button>
          {visibleItems.length > 0 && <div className="ticker-switcher-list" aria-label="Watchlist symbols">{visibleItems.map((item) => <button key={item.symbol} type="button" onClick={() => { close(false); onSelect(item.symbol); }}><strong>{item.symbol}</strong><span>{item.name}</span><small>{item.change}</small></button>)}</div>}
        </div>
      </MarketFloatingPopover>
    </div>
  );
}
