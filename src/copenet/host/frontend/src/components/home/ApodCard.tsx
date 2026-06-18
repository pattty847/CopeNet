import { useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { ApodRecord, ApodResult } from '../../types/backend';

/**
 * NASA Astronomy Picture of the Day — ambient Home surface.
 *
 * Honest states only: loading skeleton, missing-key / error empty state, and the
 * real picture. `media_type: "video"` is linked, never forced into an <img>.
 */
export function ApodCard({ isMobile }: { isMobile: boolean }) {
  const [result, setResult] = useState<ApodResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    wsClient
      .fetchApod()
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch(() => {
        if (!cancelled) setResult({ configured: true, apod: null, error: 'Could not reach the picture-of-the-day service.' });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="overflow-hidden rounded-[12px] border border-shell-border bg-shell-panel">
      <header className="flex items-center justify-between border-b border-shell-border px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-shell-muted">
            Picture of the Day
          </span>
          <span className="text-[10px] text-shell-muted/60">NASA APOD</span>
        </div>
        {result?.apod?.date && <span className="text-[10px] tabular-nums text-shell-muted/70">{result.apod.date}</span>}
      </header>

      {loading ? (
        <div className="animate-pulse">
          <div className="aspect-[16/9] w-full bg-shell-bg" />
          <div className="space-y-2 px-3.5 py-3">
            <div className="h-3 w-2/3 rounded bg-shell-bg" />
            <div className="h-2.5 w-full rounded bg-shell-bg" />
            <div className="h-2.5 w-5/6 rounded bg-shell-bg" />
          </div>
        </div>
      ) : result?.apod ? (
        <ApodBody apod={result.apod} isMobile={isMobile} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
      ) : (
        <ApodEmpty configured={result?.configured ?? true} error={result?.error ?? null} />
      )}
    </section>
  );
}

function ApodBody({
  apod,
  isMobile,
  expanded,
  onToggle,
}: {
  apod: ApodRecord;
  isMobile: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const isVideo = apod.mediaType === 'video';
  // Prefer our cached copy (resilient to apod.nasa.gov outages); fall back to NASA on miss.
  const poster = apod.cachedUrl || apod.thumbnailUrl || (isVideo ? null : apod.url);
  // On mobile, collapse a very long explanation behind a toggle to keep the card scannable.
  const blurb = !expanded && isMobile && apod.explanation.length > 220 ? `${apod.explanation.slice(0, 220).trimEnd()}…` : apod.explanation;

  return (
    <div>
      <a
        href={apod.hdUrl || apod.url}
        target="_blank"
        rel="noreferrer"
        className="group block bg-black"
        title={isVideo ? 'Open video' : 'Open full-resolution image'}
      >
        {poster ? (
          <img
            src={poster}
            alt={apod.title}
            loading="lazy"
            onError={(e) => {
              // Cache miss / our route 404'd — fall back to hotlinking NASA directly.
              const img = e.currentTarget;
              if (apod.url && img.src !== apod.url) img.src = apod.url;
            }}
            className="aspect-[16/9] w-full object-cover transition-opacity duration-200 group-hover:opacity-90"
          />
        ) : (
          <div className="flex aspect-[16/9] w-full items-center justify-center bg-shell-bg text-[11px] text-shell-muted">
            Video — tap to watch
          </div>
        )}
      </a>

      <div className="space-y-1.5 px-3.5 py-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-[13px] font-semibold leading-snug text-shell-text">{apod.title}</h3>
          {isVideo && (
            <span className="shrink-0 rounded-full border border-shell-border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-shell-muted">
              Video
            </span>
          )}
        </div>
        <p className="text-[11.5px] leading-relaxed text-shell-muted">{blurb}</p>
        <div className="flex items-center gap-3 pt-0.5 text-[10px] text-shell-muted/70">
          {isMobile && apod.explanation.length > 220 && (
            <button type="button" onClick={onToggle} className="font-medium text-shell-accent hover:underline">
              {expanded ? 'Show less' : 'Read more'}
            </button>
          )}
          {apod.copyright && <span className="truncate">© {apod.copyright}</span>}
        </div>
      </div>
    </div>
  );
}

function ApodEmpty({ configured, error }: { configured: boolean; error: string | null }) {
  const message = !configured
    ? 'Set NASA_API_KEY in your .env to see the daily picture.'
    : error || 'No picture available right now.';
  return (
    <div className="flex aspect-[16/9] w-full flex-col items-center justify-center gap-1.5 px-4 text-center">
      <span className="text-[20px]" aria-hidden>
        🛰️
      </span>
      <p className="text-[11.5px] text-shell-muted">{message}</p>
    </div>
  );
}
