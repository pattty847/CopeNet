// Home: the operator's desk.
//
// Four questions, answered above and just below the fold: what is the market doing, what is
// on my tape, what did my agents just do, and what did I tell myself to do today. Every
// panel here reads a store that already exists — the page owns no data of its own except
// the focus list.
//
// Two rules this page must keep:
//   1. Landing on Home never *acquires* market data. Both market reads go through
//      `useStoredMarketResource`; Scans owns acquisition, and a page load is not a scan.
//   2. Runtime facts come from one `home.snapshot` call, never a per-session fan-out.
//      Observability fans out one `sessions.runs` per session and this workspace has
//      hundreds — that is not a page load, it is a self-inflicted stampede.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';
import { useMarketWatchlist } from '../../sections/market/useMarketMonitorData';
import { useMarketDashboard, useMorningBrief } from '../../sections/market/useMarketSweepData';
import type { DeskSnapshot, FocusState } from '../../types/backend';
import type { MarketSection } from '../../lib/appSectionRouting';
import { marketClock } from './deskModel';
import { DEFAULT_LAUNCH_IDS, type LaunchDestination } from './quickLaunch';
import { ApodPanel } from './panels/ApodPanel';
import { BriefingCard } from './panels/BriefingCard';
import { Card } from './panels/Card';
import { LaunchPicker } from './panels/LaunchPicker';
import { MarketPulse } from './panels/MarketPulse';
import { MyFocus } from './panels/MyFocus';
import { QuickLaunch } from './panels/QuickLaunch';
import { RecentActivity } from './panels/RecentActivity';
import { SystemHealth } from './panels/SystemHealth';
import { ToolShortcuts } from './panels/ToolShortcuts';
import '../../sections/market/tickerWorkspace.css';
import './home.css';

/** The desk refreshes on a slow clock: run records change when a run ends, not per second,
 *  and a Home that repolls aggressively is a background load on the host for no new fact. */
const SNAPSHOT_REFRESH_MS = 60_000;

/** Six rows sits at about the height of the three panels beside it, so the bottom band
 *  reads as one row rather than one tall card and three short ones. */
const ACTIVITY_ROWS = 6;

function useDeskSnapshot() {
  const [snapshot, setSnapshot] = useState<DeskSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setSnapshot(await wsClient.homeSnapshot(ACTIVITY_ROWS));
    } catch {
      // A failed refresh keeps the last real snapshot rather than blanking the panels:
      // stale-and-labelled beats empty-and-ambiguous.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), SNAPSHOT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  return { snapshot, loading, reload: load };
}

function useMarketClock() {
  const [clock, setClock] = useState(() => marketClock());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(marketClock()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return clock;
}

export function HomeDesk() {
  const wsStatus = useAppStore((state) => state.wsStatus);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const openMarketTicker = useAppStore((state) => state.openMarketTicker);
  const openMarketSection = useAppStore((state) => state.openMarketSection);

  const clock = useMarketClock();
  const watchlist = useMarketWatchlist();
  const { dashboard } = useMarketDashboard();
  const { brief } = useMorningBrief();
  const { snapshot, loading } = useDeskSnapshot();

  const [focus, setFocus] = useState<FocusState | null>(null);
  const [customizing, setCustomizing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void wsClient
      .getFocus()
      .then((state) => {
        if (!cancelled) setFocus(state);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const macro = useMemo(() => dashboard?.macro.data ?? [], [dashboard?.macro.data]);

  const launch = useCallback(
    (destination: LaunchDestination) => {
      if (destination.kind === 'market') {
        openMarketSection(destination.view);
        return;
      }
      if (destination.kind === 'newSession') {
        setActiveSessionKey(null);
        setDraftOpen(true);
        setCurrentSection('agents');
        return;
      }
      setCurrentSection(destination.section);
    },
    [openMarketSection, setActiveSessionKey, setCurrentSection, setDraftOpen],
  );

  const toggleTile = useCallback(
    (id: string) => {
      const current = focus?.quickLaunch?.length ? focus.quickLaunch : DEFAULT_LAUNCH_IDS;
      const next = current.includes(id) ? current.filter((tile) => tile !== id) : [...current, id];
      // An empty stored list means "use the defaults", so refuse to save one — otherwise
      // deselecting everything would silently restore the tiles the operator just removed.
      if (next.length === 0) return;
      void wsClient.updateFocus({ op: 'quickLaunch', tiles: next }).then(setFocus).catch(() => undefined);
    },
    [focus],
  );

  return (
    <div className="hd">
      <BriefingCard
        dashboard={dashboard ?? null}
        brief={brief ?? null}
        clock={clock}
        quote={snapshot?.quote ?? null}
        onOpenMarket={(view) => openMarketSection(view as MarketSection)}
      />

      <ApodPanel />

      {customizing ? (
        <Card
          title="Quick launch · choose six"
          span={5}
          head={
            <>
              <div className="hd-card__spacer" />
              <button type="button" className="hd-link" onClick={() => setCustomizing(false)}>
                Done
              </button>
            </>
          }
        >
          <LaunchPicker
            selected={focus?.quickLaunch ?? []}
            onToggle={toggleTile}
            onClose={() => setCustomizing(false)}
          />
        </Card>
      ) : (
        <QuickLaunch
          savedIds={focus?.quickLaunch ?? []}
          onLaunch={launch}
          onCustomize={() => setCustomizing(true)}
        />
      )}

      <MarketPulse watchlist={watchlist} macro={macro} onOpenTicker={openMarketTicker} />

      <RecentActivity
        activity={snapshot?.activity ?? []}
        loading={loading}
        onOpenRun={(entry) => {
          setActiveSessionKey(entry.sessionKey);
          setDraftOpen(false);
          setCurrentSection(entry.errored ? 'observability' : 'agents');
        }}
        onOpenAll={() => setCurrentSection('observability')}
      />

      <SystemHealth
        health={snapshot?.health ?? null}
        wsConnected={wsStatus === 'connected'}
        generatedAt={snapshot?.generatedAt ?? ''}
        onOpenObservability={() => setCurrentSection('observability')}
      />

      <ToolShortcuts
        onOpen={(destination) =>
          destination.kind === 'market' ? openMarketSection(destination.view) : setCurrentSection(destination.section)
        }
        onOpenAll={() => setCurrentSection('data-tools')}
      />

      <MyFocus focus={focus} onChange={setFocus} />
    </div>
  );
}
