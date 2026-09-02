// Evidence — filings and news, full width, newest first, with source, date and the outbound
// filing. Filters are the section's own controls; the briefing only ever shows the flagged
// subset the sweep ranked into Matters.

import { useMemo, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { sortEvidenceNewestFirst } from '../marketEvidence';
import { EvidenceFlagBadge, EvidenceToneGlyph, PreviewBadge, evidenceDate, evidenceTypeBg, evidenceTypeColor } from '../marketUi';
import { SectionHeader } from './SectionGrid';
import type { DashboardPayload, EvidenceItem } from '../types';

type TypeFilter = 'all' | EvidenceItem['type'];

const TYPE_FILTERS: { id: TypeFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'Insider', label: 'Insider' },
  { id: '8-K', label: '8-K' },
  { id: 'Form 144', label: 'Form 144' },
  { id: 'News', label: 'News' },
];

export function EvidenceSection({
  dashboard,
  watched,
  onOpen,
}: {
  dashboard: DashboardPayload;
  watched: Set<string>;
  onOpen: (symbol: string) => void;
}) {
  const [type, setType] = useState<TypeFilter>('all');
  const [watchedOnly, setWatchedOnly] = useState(false);
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const all = useMemo(() => sortEvidenceNewestFirst(dashboard.evidence.data), [dashboard.evidence.data]);
  const rows = all.filter((item) => (type === 'all' || item.type === type) && (!watchedOnly || watched.has(item.symbol)) && (!flaggedOnly || item.flag));

  return (
    <>
      <SectionHeader label="Evidence" meta={`${all.length} cited item${all.length === 1 ? '' : 's'} · newest first`}>
        <PreviewBadge status={dashboard.evidence.status} />
      </SectionHeader>

      <div className="mw-filters" style={{ marginBottom: 'var(--mkt-s2)' }}>
        {TYPE_FILTERS.map((filter) => (
          <button key={filter.id} type="button" className="mw-chip" aria-pressed={type === filter.id} onClick={() => setType(filter.id)}>{filter.label}</button>
        ))}
        <span className="tw-sep" style={{ margin: '0 4px' }} />
        <button type="button" className="mw-chip" aria-pressed={flaggedOnly} onClick={() => setFlaggedOnly((value) => !value)} title="Cluster buys and high-signal 8-Ks only">Flagged</button>
        <button type="button" className="mw-chip" aria-pressed={watchedOnly} onClick={() => setWatchedOnly((value) => !value)} title="Only symbols on the active watchlist">Watched</button>
        {rows.length !== all.length && <span className="mw-sect__meta" style={{ marginLeft: 6 }}>{rows.length} of {all.length}</span>}
      </div>

      <div className="mw-evidence" role="table" aria-label="Evidence and news">
        {rows.length === 0 && <div className="mw-empty">{all.length === 0 ? 'No filings or news in the window.' : 'Nothing matches these filters.'}</div>}
        {rows.map((item, index) => (
          <div key={`${item.symbol}-${item.t ?? index}-${index}`} className="mw-evrow" role="row" onClick={() => onOpen(item.symbol)}>
            <span className="mw-evrow__type" style={{ background: evidenceTypeBg(item.type), color: evidenceTypeColor(item.type) }}>{item.type}</span>
            <span className="mw-evrow__sym">{item.symbol}</span>
            <span className="mw-evrow__text">
              <EvidenceToneGlyph tone={item.tone} />
              {item.headline}
              <EvidenceFlagBadge flag={item.flag} />
            </span>
            <span className="mw-evrow__source">
              {item.source}
              {evidenceDate(item.t) && <small>{evidenceDate(item.t)}</small>}
            </span>
            {item.url ? (
              <a className="mw-matter__link" href={item.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} aria-label={`Open the source for ${item.symbol}`} title="Open the source">
                <ArrowUpRight size={12} />
              </a>
            ) : (
              <span />
            )}
          </div>
        ))}
      </div>
    </>
  );
}
