// NASA Astronomy Picture of the Day — the one thing on the desk that is not about money.
//
// Honest states only: a skeleton while loading, a stated reason when there is no picture
// (usually a missing NASA_API_KEY), and the real thing otherwise. `media_type: "video"` is
// linked rather than forced into an <img>, and its poster slot says so instead of rendering
// a black rectangle the operator would read as a broken image.

import { useEffect, useState } from 'react';
import { ExternalLink, Telescope } from 'lucide-react';
import { wsClient } from '../../../lib/wsClient';
import type { ApodRecord, ApodResult } from '../../../types/backend';
import { Card } from './Card';

export function ApodPanel() {
  const [result, setResult] = useState<ApodResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    wsClient
      .fetchApod()
      .then((next) => {
        if (!cancelled) setResult(next);
      })
      .catch(() => {
        if (!cancelled) {
          setResult({ configured: true, apod: null, error: 'Could not reach the picture-of-the-day service.' });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const apod = result?.apod ?? null;

  return (
    <Card
      title="Picture of the day"
      icon={Telescope}
      span={4}
      head={
        <>
          <div className="hd-card__spacer" />
          {apod?.date && <span className="hd-saved">{apod.date}</span>}
        </>
      }
    >
      {loading ? (
        <div className="hd-apod__media" style={{ background: 'var(--mkt-raise)' }} />
      ) : apod ? (
        <ApodBody apod={apod} />
      ) : (
        <div className="hd-empty">
          {result?.configured === false
            ? 'Set NASA_API_KEY in your .env to see the daily picture.'
            : result?.error || 'No picture available right now.'}
        </div>
      )}
    </Card>
  );
}

function ApodBody({ apod }: { apod: ApodRecord }) {
  const isVideo = apod.mediaType === 'video';
  // Prefer the cached copy — resilient to apod.nasa.gov outages — and fall back to NASA.
  const poster = apod.cachedUrl || apod.thumbnailUrl || (isVideo ? null : apod.url);

  return (
    <div className="hd-apod">
      <a
        className="hd-apod__media"
        href={apod.hdUrl || apod.url}
        target="_blank"
        rel="noreferrer"
        title={isVideo ? 'Open the video on NASA' : 'Open the full-resolution image'}
      >
        {poster ? (
          <img
            src={poster}
            alt={apod.title}
            loading="lazy"
            onError={(event) => {
              const img = event.currentTarget;
              if (apod.url && img.src !== apod.url) img.src = apod.url;
            }}
          />
        ) : (
          <span className="hd-apod__placeholder">Video — open on NASA</span>
        )}
      </a>

      <div className="hd-apod__text">
        <h3 className="hd-apod__title">
          {apod.title}
          {isVideo && <span className="hd-apod__badge">video</span>}
        </h3>
        <p className="hd-apod__blurb">{apod.explanation}</p>
      </div>

      <a className="hd-apod__link" href={apod.hdUrl || apod.url} target="_blank" rel="noreferrer">
        View on NASA <ExternalLink size={10} />
      </a>
    </div>
  );
}
