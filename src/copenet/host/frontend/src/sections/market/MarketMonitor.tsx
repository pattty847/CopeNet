import { useEffect, useState } from 'react';
import { marketTickerFromPathname, marketTickerPath } from '../../lib/appSectionRouting';
import { MarketDashboard } from './MarketDashboard';
import { TickerDetailPage } from './TickerDetailPage';
import { useMarketWatchlist } from './useMarketMonitorData';

export function MarketMonitor() {
  const watchlist = useMarketWatchlist();
  const [activeTicker, setActiveTicker] = useState(() => marketTickerFromPathname(window.location.pathname));

  useEffect(() => {
    const syncFromLocation = () => setActiveTicker(marketTickerFromPathname(window.location.pathname));
    window.addEventListener('popstate', syncFromLocation);
    return () => window.removeEventListener('popstate', syncFromLocation);
  }, []);

  const navigateTicker = (symbol: string | null) => {
    const nextPath = marketTickerPath(symbol);
    if (window.location.pathname !== nextPath) window.history.pushState({}, '', nextPath);
    setActiveTicker(symbol?.trim().toUpperCase() || null);
  };

  if (activeTicker) {
    return (
      <TickerDetailPage
        symbol={activeTicker}
        onClose={() => navigateTicker(null)}
        onOpenTicker={(symbol) => navigateTicker(symbol)}
        watchlist={watchlist}
      />
    );
  }

  return <MarketDashboard onOpenTicker={(symbol) => navigateTicker(symbol)} watchlist={watchlist} />;
}
