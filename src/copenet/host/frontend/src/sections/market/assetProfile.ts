// What kind of thing is this, and which parts of the workspace can honestly serve it?
//
// The discriminator is already in the payload: an issuer that files with the SEC gets
// fundamentals and insider evidence; a fund gets holdings and sector weights and will never
// have either. `intelligence.exposure` carries the fund's own content, so routing on it both
// identifies the asset AND supplies the replacement — hiding tabs without replacing them
// would just leave an emptier workspace.

import type { ResearchTab } from './tickerWorkspaceState';
import type { TickerDetailPayload } from './types';

export type AssetKind = 'fund' | 'issuer';

export interface AssetProfile {
  kind: AssetKind;
  label: string;
  /** Tabs that can show something real for this asset. */
  tabs: ResearchTab[];
}

export function assetProfile(detail: TickerDetailPayload | null): AssetProfile {
  const exposure = detail?.intelligence?.exposure;
  const isFund = Boolean(exposure && (exposure.topHoldings?.length || Object.keys(exposure.sectorWeightPct ?? {}).length));
  if (isFund) {
    return {
      kind: 'fund',
      label: 'Fund',
      // No issuer files behind a fund, so Fundamentals and SEC evidence have nothing to
      // draw. Overview absorbs the holdings and sector weights, which is what a fund IS.
      tabs: ['overview', 'synthesis'],
    };
  }
  return { kind: 'issuer', label: 'Equity', tabs: ['overview', 'fundamentals', 'evidence', 'synthesis'] };
}
