import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { ChartTimeframe } from '../chartRanges';
import type { Ohlcv } from '../types';
import { useViewResource } from '../viewState/resources';
import { loadPositionPreferences } from './model';
import type { PositionPreferences } from './types';
import type { usePosition } from './usePosition';

type State = ReturnType<typeof usePosition>;
interface Context {
  state: State; preferences: PositionPreferences; update: (change: Partial<PositionPreferences>) => void;
  bars: Ohlcv[]; timeframe: ChartTimeframe; hidden: boolean; open: () => void;
}
const PositionContext = createContext<Context | null>(null);
export const usePositionContext = () => useContext(PositionContext);
export function PositionProvider({ state, bars, timeframe, hidden, open, children }: Omit<Context, 'preferences' | 'update'> & { children: ReactNode }) {
  const [preferences, setPreferences] = useState(loadPositionPreferences);
  useEffect(() => { try { localStorage.setItem('mm-position-display', JSON.stringify(preferences)); } catch { /* optional preference */ } }, [preferences]);
  const resource = useMemo(() => ({ key: 'account:position', kind: 'panel' as const, label: 'Your position',
    status: state.error ? 'error' as const : state.data?.position ? 'loaded' as const : 'not-loaded' as const,
    observedAt: state.data?.syncedAt, rows: state.data?.position ? [{ ...state.data.position }] : [],
    metadata: { accountContext: true, preferences, overlayHidden: hidden, source: 'Webull snapshot',
      fills: state.data?.fills ?? [], fillsSyncedAt: state.data?.fillsSyncedAt, historyNote: state.data?.historyNote, error: state.error },
  }), [state.data, state.error, preferences, hidden]);
  useViewResource(state.data?.symbol ?? '', resource);
  return <PositionContext.Provider value={{ state, bars, timeframe, hidden, preferences, update: (change) => setPreferences((old) => ({ ...old, ...change })), open }}>{children}</PositionContext.Provider>;
}
