import type { SectionPanelSpec } from './marketWorkstationState';

// Loading outlines and loaded panels resolve the same saved layout against these specs.
export const STRUCTURE_PANELS = {
  treasury: { id: 'treasury', title: 'Treasury curve', defaultWidth: 'full', canHalf: false },
  sectorRrg: { id: 'sectorRrg', title: 'Sector rotation', defaultWidth: 'full', canHalf: true },
  industryRrg: { id: 'industryRrg', title: 'Industry rotation', defaultWidth: 'full', canHalf: true },
} satisfies Record<string, SectionPanelSpec>;

export const SIGNAL_PANELS = {
  softBottoming: { id: 'softBottoming', title: 'Soft bottoming watch', defaultWidth: 'full', canHalf: true },
  accumulation: { id: 'accumulation', title: 'Accumulation watch', defaultWidth: 'half', canHalf: true },
  trend: { id: 'trend', title: 'Trend-change watch', defaultWidth: 'half', canHalf: true },
} satisfies Record<string, SectionPanelSpec>;

export const PORTFOLIO_PANELS = {
  positions: { id: 'positions', title: 'Positions · live P&L', defaultWidth: 'full', canHalf: false },
  speculative: { id: 'speculative', title: 'Speculative lane', defaultWidth: 'half', canHalf: true },
  allTimePnl: { id: 'allTimePnl', title: 'All-time P&L', defaultWidth: 'half', canHalf: true },
  tradeHistory: { id: 'tradeHistory', title: 'Trade history', defaultWidth: 'full', canHalf: false },
} satisfies Record<string, SectionPanelSpec>;
