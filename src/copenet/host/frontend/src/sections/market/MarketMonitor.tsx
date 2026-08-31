import { useEffect, useState } from 'react';
import {
  marketFormulaFromLocation,
  marketFormulaPath,
  marketTickerFromPathname,
  marketTickerNavigationPath,
} from '../../lib/appSectionRouting';
import { FormulaWorkspace } from './FormulaWorkspace';
import { MarketCockpit } from './MarketCockpit';
import { TickerWorkspace } from './TickerWorkspace';
import { useMarketWatchlist } from './useMarketMonitorData';

export function MarketMonitor() {
  const watchlist = useMarketWatchlist();
  const [activeTicker, setActiveTicker] = useState(() => marketTickerFromPathname(window.location.pathname));
  const [activeFormula, setActiveFormula] = useState(() => marketFormulaFromLocation(window.location.pathname, window.location.search));

  useEffect(() => {
    const syncFromLocation = () => {
      setActiveTicker(marketTickerFromPathname(window.location.pathname));
      setActiveFormula(marketFormulaFromLocation(window.location.pathname, window.location.search));
    };
    window.addEventListener('popstate', syncFromLocation);
    return () => window.removeEventListener('popstate', syncFromLocation);
  }, []);

  const navigateMarket = (value: string | null, type: 'symbol' | 'formula' = 'symbol') => {
    const nextPath = value == null
      ? '/market'
      : type === 'formula'
        ? marketFormulaPath(value)
        : marketTickerNavigationPath(value, window.location.pathname, window.location.search);
    if (`${window.location.pathname}${window.location.search}` !== nextPath) window.history.pushState({}, '', nextPath);
    setActiveTicker(type === 'symbol' ? value?.trim().toUpperCase() || null : null);
    setActiveFormula(type === 'formula' ? value?.trim() || null : null);
  };

  if (activeFormula) {
    return (
      <FormulaWorkspace
        expression={activeFormula}
        onClose={() => navigateMarket(null)}
        onNavigate={(next, type = 'symbol') => navigateMarket(next, type)}
      />
    );
  }

  if (activeTicker) {
    return (
      <TickerWorkspace
        symbol={activeTicker}
        onClose={() => navigateMarket(null)}
        onNavigate={(next, type = 'symbol') => navigateMarket(next, type)}
        watchlist={watchlist}
      />
    );
  }

  return <MarketCockpit onOpenTicker={(symbol, type = 'symbol') => navigateMarket(symbol, type)} watchlist={watchlist} />;
}
