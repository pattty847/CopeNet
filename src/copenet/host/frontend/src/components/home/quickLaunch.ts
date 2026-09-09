// Quick Launch: the six places the operator actually goes.
//
// A registry rather than markup, because the tiles are reorderable and the saved order is
// a list of ids. An id the operator saved that no longer exists is dropped on read rather
// than rendered as a dead tile, and a tile added later appears for anyone who never
// customised — which is what makes an empty saved list mean "the default set".

import {
  Activity,
  Bot,
  CandlestickChart,
  FileSearch,
  LineChart,
  ListChecks,
  Radar,
  Search,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { MarketSection } from '../../lib/appSectionRouting';
import type { AppSection } from '../../store/useAppStore';

export type LaunchDestination =
  | { kind: 'section'; section: AppSection }
  | { kind: 'market'; view: MarketSection }
  | { kind: 'newSession' };

export interface LaunchTile {
  id: string;
  label: string;
  detail: string;
  icon: LucideIcon;
  destination: LaunchDestination;
}

export const LAUNCH_TILES: LaunchTile[] = [
  { id: 'market_radar', label: 'Open', detail: 'Market Radar', icon: Radar, destination: { kind: 'market', view: 'briefing' } },
  { id: 'new_session', label: 'Start', detail: 'Agent Session', icon: Bot, destination: { kind: 'newSession' } },
  { id: 'signals', label: 'Check', detail: 'Signals', icon: LineChart, destination: { kind: 'market', view: 'signals' } },
  { id: 'watchlists', label: 'Open', detail: 'Watchlists', icon: ListChecks, destination: { kind: 'market', view: 'watchlist' } },
  { id: 'scans', label: 'Run', detail: 'Sweep', icon: Search, destination: { kind: 'market', view: 'scans' } },
  { id: 'evidence', label: 'Review', detail: 'SEC Evidence', icon: FileSearch, destination: { kind: 'market', view: 'evidence' } },
  { id: 'portfolio', label: 'Open', detail: 'Portfolio', icon: CandlestickChart, destination: { kind: 'market', view: 'portfolio' } },
  { id: 'runs', label: 'Inspect', detail: 'Recent Runs', icon: Activity, destination: { kind: 'section', section: 'observability' } },
];

export const DEFAULT_LAUNCH_IDS = ['market_radar', 'new_session', 'signals', 'watchlists', 'scans', 'evidence'];

export const LAUNCH_SLOTS = 6;

const BY_ID = new Map(LAUNCH_TILES.map((tile) => [tile.id, tile]));

/** The operator's chosen tiles. An empty saved list means "the default set" rather than
 *  "no tiles", so a fresh workspace and a deliberately-emptied one are distinguishable —
 *  the picker refuses to save an empty selection. */
export function resolveLaunchTiles(saved: readonly string[]): LaunchTile[] {
  const ids = saved.length > 0 ? saved : DEFAULT_LAUNCH_IDS;
  const tiles: LaunchTile[] = [];
  for (const id of ids) {
    const tile = BY_ID.get(id);
    if (tile && !tiles.includes(tile)) tiles.push(tile);
  }
  return tiles.slice(0, LAUNCH_SLOTS);
}
