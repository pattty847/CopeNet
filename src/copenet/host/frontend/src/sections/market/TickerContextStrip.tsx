import { Database, FileText, Gauge, WalletCards } from 'lucide-react';
import { evidenceDate } from './marketUi';
import { latestMaterialEvidence } from './TickerOverviewPanel';
import type { EvidenceItem, TickerDetailPayload } from './types';

export type TickerResearchTab = 'overview' | 'evidence' | 'synthesis';

export function TickerContextStrip({
  detail,
  evidence,
  onOpenTab,
}: {
  detail: TickerDetailPayload;
  evidence: EvidenceItem[];
  onOpenTab: (tab: TickerResearchTab) => void;
}) {
  const intelligence = detail.intelligence;
  const latestEvidence = latestMaterialEvidence(evidence);
  const position = intelligence?.portfolio;
  const drawdown = intelligence?.drawdown.drawdown52wPct;
  const priceRegime = intelligence
    ? `${intelligence.trend.longTrend} · ${drawdown == null ? 'drawdown unavailable' : `${Math.abs(drawdown).toFixed(1)}% off 52w high`}`
    : 'Market state unavailable';
  const dataWarning = intelligence?.dataQuality.thinHistory || intelligence?.dataQuality.hasVolume === false;

  return (
    <div className="ticker-context-strip" aria-label="Asset context summary">
      {latestEvidence && (
        <button type="button" className="ticker-context-item ticker-context-item--evidence" onClick={() => onOpenTab('evidence')}>
          <FileText size={14} aria-hidden="true" />
          <span><small>Latest material evidence · {evidenceDate(latestEvidence.t) || 'date unavailable'}</small><strong>{latestEvidence.type} · {latestEvidence.headline}</strong></span>
        </button>
      )}
      <button type="button" className="ticker-context-item" onClick={() => onOpenTab('overview')}>
        <Gauge size={14} aria-hidden="true" />
        <span><small>Price regime</small><strong>{priceRegime}</strong></span>
      </button>
      {position && (
        <button type="button" className="ticker-context-item" onClick={() => onOpenTab('overview')}>
          <WalletCards size={14} aria-hidden="true" />
          <span><small>Position</small><strong>{position.shares == null ? 'Held' : `${position.shares.toLocaleString()} shares`} · {position.pnlPct == null ? 'P&L unavailable' : `${position.pnlPct > 0 ? '+' : ''}${position.pnlPct.toFixed(1)}%`}</strong></span>
        </button>
      )}
      <button type="button" className={dataWarning ? 'ticker-context-item has-warning' : 'ticker-context-item'} onClick={() => onOpenTab('overview')}>
        <Database size={14} aria-hidden="true" />
        <span><small>Data status</small><strong>{dataWarning ? 'Review quality warnings' : 'Price, SEC, and fundamentals current'}</strong></span>
      </button>
    </div>
  );
}
