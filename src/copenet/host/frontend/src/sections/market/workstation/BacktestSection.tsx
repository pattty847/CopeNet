// Backtest — a lab. It gets the whole bench: parameters, results and the session runs
// ledger at full workspace width, loaded only when opened.

import { lazy, Suspense } from 'react';
import { SectionHeader } from './SectionGrid';

const BacktestLab = lazy(() => import('../BacktestLab').then((module) => ({ default: module.BacktestLab })));

export function BacktestSection() {
  return (
    <>
      <SectionHeader label="Backtest" meta="portfolio backtests and stress scenarios" />
      <Suspense fallback={<div className="mw-empty" role="status">Loading the scenario lab…</div>}>
        <BacktestLab />
      </Suspense>
    </>
  );
}
