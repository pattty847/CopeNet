import { useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useIsMobile } from '../../lib/responsive';
import { loadDrawerSizes, loadRailCollapsed, loadSnaps, loadTab } from './tickerWorkspaceState';
import { SkeletonLines, SkeletonPanel, WorkspaceLoading, WorkspaceLoadError } from './loading/WorkspaceLoading';

export function TickerLoadState({
  symbol,
  error,
  onClose,
  onRetry,
}: {
  symbol: string;
  error: string | null;
  onClose: () => void;
  onRetry: () => Promise<void>;
}) {
  const [collapsed] = useState(loadRailCollapsed);
  const [tab] = useState(loadTab);
  const [snap] = useState(() => loadSnaps()[tab]);
  const [size] = useState(() => loadDrawerSizes()[tab]);
  const isMobile = useIsMobile();
  const outlines = (
    <>
      <SkeletonPanel kind="chart" />
      {snap !== 'collapsed' && (
        <div className="workspace-loading__ticker-research" style={{ flexBasis: `${size ?? (snap === 'full' ? 68 : isMobile ? 52 : 40)}%` }}>
          <SkeletonPanel />
        </div>
      )}
    </>
  );
  return (
    <div className="tw">
      <header className="tw-assetbar">
        <button type="button" className="tw-iconbtn" onClick={onClose} aria-label="Back to Market">
          <ArrowLeft size={14} />
        </button>
        <h1 className="tw-assetbar__symbol">{symbol}</h1>
      </header>
      <div className="tw-body">
        <div className="tw-rail" data-collapsed={collapsed} aria-hidden="true">
          <div className="workspace-loading workspace-loading__rail">
            <SkeletonLines rows={10} />
          </div>
        </div>
        <div className="tw-main workspace-loading__ticker">
          {error ? (
            <>
              <WorkspaceLoadError title={`Could not load ${symbol}`} error={error} onRetry={() => void onRetry()} />
              <div className="workspace-loading__outlines workspace-loading--failed" aria-hidden="true">
                {outlines}
              </div>
            </>
          ) : (
            <WorkspaceLoading label={`Loading ${symbol} workspace…`}>{outlines}</WorkspaceLoading>
          )}
        </div>
      </div>
    </div>
  );
}
