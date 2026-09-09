// The Data & Tools shortcuts on Home.
//
// Every tile here goes somewhere that exists. The temptation on a page like this is to lay
// out a full grid of capabilities and let the empty ones read as "coming soon" — but a tile
// that navigates nowhere is worse than a gap, and the operator cannot tell the two apart
// until they click. When a capability lands, add it here.

import { CalendarClock, Database, FileSearch, FlaskConical, KeyRound, Radar } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { MarketSection } from '../../lib/appSectionRouting';
import type { AppSection } from '../../store/useAppStore';

export interface ToolShortcut {
  id: string;
  label: string;
  detail: string;
  icon: LucideIcon;
  destination: { kind: 'section'; section: AppSection } | { kind: 'market'; view: MarketSection };
}

export const TOOL_SHORTCUTS: ToolShortcut[] = [
  { id: 'sec', label: 'SEC Filings', detail: 'Insider & 8-K evidence', icon: FileSearch, destination: { kind: 'market', view: 'evidence' } },
  { id: 'calendar', label: 'Macro Calendar', detail: 'Economic events', icon: CalendarClock, destination: { kind: 'market', view: 'briefing' } },
  { id: 'screener', label: 'Scans', detail: 'Build & run screens', icon: Radar, destination: { kind: 'market', view: 'scans' } },
  { id: 'backtests', label: 'Backtests', detail: 'Strategy research', icon: FlaskConical, destination: { kind: 'market', view: 'backtest' } },
  { id: 'datasets', label: 'Data Sources', detail: 'Browse & ingest', icon: Database, destination: { kind: 'section', section: 'data-tools' } },
  { id: 'access', label: 'API Access', detail: 'Keys & integrations', icon: KeyRound, destination: { kind: 'section', section: 'data-tools' } },
];
