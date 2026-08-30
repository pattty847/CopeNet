import { useEffect, useState } from 'react';
import { marketTickerFromPathname, marketTickerNavigationPath } from '../../lib/appSectionRouting';
import { MarketDashboard } from './MarketDashboard';
import { TickerWorkspace } from './TickerWorkspace';
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
    const nextPath = marketTickerNavigationPath(symbol, window.location.pathname, window.location.search);
    if (`${window.location.pathname}${window.location.search}` !== nextPath) window.history.pushState({}, '', nextPath);
    setActiveTicker(symbol?.trim().toUpperCase() || null);
  };

  if (activeTicker) {
    return (
      <TickerWorkspace
        symbol={activeTicker}
        onClose={() => navigateTicker(null)}
        onNavigate={(next) => navigateTicker(next)}
        watchlist={watchlist}
      />
    );
  }

  return <MarketDashboard onOpenTicker={(symbol) => navigateTicker(symbol)} watchlist={watchlist} />;
}
