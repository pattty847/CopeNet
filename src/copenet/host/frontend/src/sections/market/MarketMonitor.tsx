import { useEffect, useState } from 'react';
import {
  marketFormulaFromLocation,
  marketFormulaPath,
  marketSectionFromLocation,
  marketSectionPath,
  marketTickerFromPathname,
  marketTickerNavigationPath,
  type MarketSection,
} from '../../lib/appSectionRouting';
import { FormulaWorkspace } from './FormulaWorkspace';
import { MarketWorkstation } from './MarketWorkstation';
import { loadLastSection, saveLastSection } from './marketWorkstationState';
import { TickerWorkspace } from './TickerWorkspace';
import { useMarketWatchlist } from './useMarketMonitorData';

/** A workstation URL always wins, including the bare Briefing route. The remembered
 *  section is only the return destination when entering directly through an asset URL. */
function sectionFromLocation(): MarketSection {
  return marketSectionFromLocation(window.location.pathname, window.location.search) ?? loadLastSection();
}

export function MarketMonitor() {
  const watchlist = useMarketWatchlist();
  const [activeTicker, setActiveTicker] = useState(() => marketTickerFromPathname(window.location.pathname));
  const [activeFormula, setActiveFormula] = useState(() => marketFormulaFromLocation(window.location.pathname, window.location.search));
  const [activeSection, setActiveSection] = useState<MarketSection>(sectionFromLocation);

  useEffect(() => {
    if (!activeTicker && !activeFormula) saveLastSection(activeSection);
  }, [activeSection, activeTicker, activeFormula]);

  useEffect(() => {
    const syncFromLocation = () => {
      setActiveTicker(marketTickerFromPathname(window.location.pathname));
      setActiveFormula(marketFormulaFromLocation(window.location.pathname, window.location.search));
      setActiveSection(sectionFromLocation());
    };
    window.addEventListener('popstate', syncFromLocation);
    return () => window.removeEventListener('popstate', syncFromLocation);
  }, []);

  const pushPath = (nextPath: string) => {
    if (`${window.location.pathname}${window.location.search}` !== nextPath) window.history.pushState({}, '', nextPath);
  };

  const navigateMarket = (value: string | null, type: 'symbol' | 'formula' = 'symbol') => {
    const nextPath = value == null
      ? marketSectionPath(activeSection)
      : type === 'formula'
        ? marketFormulaPath(value)
        : marketTickerNavigationPath(value, window.location.pathname, window.location.search);
    pushPath(nextPath);
    setActiveTicker(type === 'symbol' ? value?.trim().toUpperCase() || null : null);
    setActiveFormula(type === 'formula' ? value?.trim() || null : null);
  };

  const selectSection = (section: MarketSection) => {
    saveLastSection(section);
    pushPath(marketSectionPath(section));
    setActiveSection(section);
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

  return (
    <MarketWorkstation
      section={activeSection}
      onSelectSection={selectSection}
      onOpenTicker={(symbol, type = 'symbol') => navigateMarket(symbol, type)}
      watchlist={watchlist}
    />
  );
}
