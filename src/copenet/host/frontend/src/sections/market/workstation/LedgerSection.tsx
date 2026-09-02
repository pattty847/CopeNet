// Ledger — the forward ledger only: every model call, price-stamped and scored later.
// Fills and P&L are the book's business and live in Portfolio.

import { ForwardLedger } from '../ForwardLedger';
import { SectionHeader } from './SectionGrid';
import type { LedgerReport } from '../types';

export function LedgerSection({ report, loading, onOpen }: { report: LedgerReport | null; loading: boolean; onOpen: (symbol: string) => void }) {
  const meta = report ? `${report.totalClaims} claims · ${report.pendingHorizons} horizons pending · rules ${report.rulesVersion}` : loading ? 'loading…' : 'no claims yet';
  return (
    <>
      <SectionHeader label="Ledger" meta={meta} />
      <ForwardLedger report={report} loading={loading} onOpen={onOpen} />
    </>
  );
}
