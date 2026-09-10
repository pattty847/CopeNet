// What this ticker IS.
//
// A scanner surfaces names nobody recognises — "SLI" says nothing about whether it is a
// lithium miner or a shell. This is the answer, and it sits at the top of Overview because
// it is the question asked first.
//
// Coverage differs by asset type and the card says so rather than pretending: an equity has
// a sector and a headcount, a fund has a category and a family, a crypto pair has a website,
// and an index has none of it.

import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import type { CompanyProfile } from '../../types/backend';

const COLLAPSED_CHARS = 320;

export function CompanyProfileCard({ symbol }: { symbol: string }) {
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setProfile(null);
    setExpanded(false);
    void wsClient
      .marketTickerProfile(symbol)
      .then((next) => { if (!cancelled) setProfile(next); })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  if (loading) {
    return (
      <section className="tw-profile" aria-busy="true">
        <span className="tw-profile__loading"><RefreshCw size={11} className="tw-spin" /> Loading profile…</span>
      </section>
    );
  }
  // An index genuinely has no business behind it. Saying nothing is more honest than an
  // empty card that looks like it failed to load.
  if (!profile || profile.isEmpty) return null;

  const facts = [
    profile.sector && { label: 'Sector', value: profile.sector },
    profile.industry && { label: 'Industry', value: profile.industry },
    profile.category && { label: 'Category', value: profile.category },
    profile.fundFamily && { label: 'Family', value: profile.fundFamily },
    profile.country && { label: 'Country', value: profile.country },
    profile.employees && { label: 'Employees', value: profile.employees.toLocaleString() },
  ].filter(Boolean) as { label: string; value: string }[];

  const long = profile.summary.length > COLLAPSED_CHARS;
  const shown = long && !expanded ? `${profile.summary.slice(0, COLLAPSED_CHARS).trimEnd()}…` : profile.summary;

  return (
    <section className="tw-profile">
      <header className="tw-profile__head">
        <span className="tw-profile__name">{profile.name || symbol}</span>
        {profile.website && (
          <a className="tw-profile__link" href={profile.website} target="_blank" rel="noreferrer">
            {profile.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
            <ExternalLink size={9} />
          </a>
        )}
      </header>

      {facts.length > 0 && (
        <div className="tw-profile__facts">
          {facts.map((fact) => (
            <span key={fact.label} className="tw-profile__fact">
              <b>{fact.label}</b>{fact.value}
            </span>
          ))}
        </div>
      )}

      {profile.summary && (
        <p className="tw-profile__summary">
          {shown}
          {long && (
            <button type="button" className="tw-profile__more" onClick={() => setExpanded((value) => !value)}>
              {expanded ? 'less' : 'more'}
            </button>
          )}
        </p>
      )}

      {profile.warnings.map((warning) => (
        <div key={warning} className="tw-profile__warning" role="status">{warning}</div>
      ))}
    </section>
  );
}
