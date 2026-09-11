import type { ScreenerConfig, ScreenerPreview, ScreenerRun, ScreenerState, SetupBars } from '../sections/market/screeners/types';
type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;
export function createMarketScreenerApi(request: Request) {
  const call = async <T>(method: string, params: Record<string, unknown> = {}) =>
    (await request(method, params)) as unknown as T;
  return {
    state: () => call<ScreenerState>('market.screeners.get'),
    preview: (config: ScreenerConfig) => call<ScreenerPreview>('market.screeners.preview', config),
    run: (config: ScreenerConfig, scopeToken: string) =>
      call<{ running: boolean }>('market.screeners.run', {
        config,
        scopeToken,
      }),
    getRun: (runId: string) => call<{ run: ScreenerRun }>('market.screeners.run.get', { runId }),
    handoff: (runId: string, symbols: string[], name: string) =>
      call<{ watchlist: string; symbols: string[] }>('market.screeners.handoff', { runId, symbols, name }),
    /** Cache-only daily history for one symbol; never fetches from a vendor. */
    setup: (symbol: string) => call<SetupBars>('market.screeners.setup.get', { symbol }),
  };
}
