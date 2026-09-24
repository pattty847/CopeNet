import { Copy, ExternalLink, LoaderCircle, MessagesSquare, PanelRightOpen, Sparkles, X } from 'lucide-react';
import { formatMediaDuration, formatRoundedRelativeAge } from '../lib/formatting';
import { MediaAssetDetail } from '../types/backend';
import { MobileSheet } from './mobile/MobileSheet';

/** One imported media asset: its transcript plus what to do with it. Discuss is
 *  the primary path (a new Agents chat with the full transcript attached). */
export function MediaAssetDrawer({
  detail,
  loading,
  error,
  onClose,
  onDiscuss,
  discussing,
  discussError,
  onUseInAgents,
  onOpenInMemeLab,
  mobile = false,
}: {
  detail: MediaAssetDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onDiscuss: (detail: MediaAssetDetail) => void;
  discussing: boolean;
  discussError: string | null;
  onUseInAgents: (detail: MediaAssetDetail) => void;
  onOpenInMemeLab: (detail: MediaAssetDetail) => void;
  mobile?: boolean;
}) {
  if (!detail && !loading && !error) return null;

  async function copyTranscript() {
    if (!detail?.transcriptContent) return;
    try {
      await navigator.clipboard.writeText(detail.transcriptContent);
    } catch {
      // best-effort
    }
  }

  const body = (
    <div className={`${mobile ? 'flex h-full flex-col overflow-hidden' : 'flex h-full flex-col overflow-hidden'}`}>
      <div className={`flex items-start justify-between gap-4 border-b border-shell-border ${mobile ? 'px-4 py-4' : 'px-6 py-5'}`}>
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Media Asset</div>
          <h2 className={`mt-2 font-semibold tracking-tight text-shell-text ${mobile ? 'text-xl' : 'text-2xl'}`}>{detail?.title || 'Loading transcript…'}</h2>
          {detail?.sourceUrl && (
            <a href={detail.sourceUrl} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-shell-text hover:text-shell-accent">
              <ExternalLink className="h-4 w-4" />
              Open source
            </a>
          )}
        </div>
        {!mobile && (
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-bg text-shell-text transition hover:border-shell-border-strong"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      <div className={`flex flex-wrap items-center gap-2 border-b border-shell-border text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted ${mobile ? 'px-4 py-3' : 'px-6 py-4'}`}>
        {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{detail.transcriptSource || 'Transcript'}</div>}
        {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatMediaDuration(detail.durationSeconds)}</div>}
        {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatRoundedRelativeAge(detail.createdAt)}</div>}
      </div>

      <div className={`flex flex-wrap items-center gap-3 border-b border-shell-border ${mobile ? 'px-4 py-3' : 'px-6 py-4'}`}>
        <button
          type="button"
          onClick={() => detail && onDiscuss(detail)}
          disabled={!detail?.transcriptContent || discussing}
          title="Open a new Agents chat with the full transcript attached"
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl bg-shell-ink px-5 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          {discussing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <MessagesSquare className="h-4 w-4" />}
          Discuss
        </button>
        <button
          type="button"
          onClick={() => void copyTranscript()}
          disabled={!detail?.transcriptContent}
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-5 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          <Copy className="h-4 w-4" />
          Copy transcript
        </button>
        <button
          type="button"
          onClick={() => detail && onUseInAgents(detail)}
          disabled={!detail}
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-5 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          <PanelRightOpen className="h-4 w-4" />
          Meme brief in Agents
        </button>
        <button
          type="button"
          onClick={() => detail && onOpenInMemeLab(detail)}
          disabled={!detail}
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-5 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          <Sparkles className="h-4 w-4" />
          Open in Meme Lab
        </button>
        {discussError && <div className="w-full text-sm text-shell-muted">{discussError}</div>}
      </div>

      <div className={`min-h-0 flex-1 overflow-auto ${mobile ? 'px-4 py-4' : 'px-6 py-5'}`}>
        {loading ? (
          <div className="flex items-center gap-3 rounded-xl border border-shell-border bg-shell-bg px-5 py-5 text-shell-muted">
            <LoaderCircle className="h-5 w-5 animate-spin text-shell-accent" />
            Loading transcript…
          </div>
        ) : error ? (
          <div className="rounded-xl border border-shell-border bg-shell-bg px-5 py-5 text-sm leading-6 text-shell-muted">{error}</div>
        ) : (
          <pre className="whitespace-pre-wrap rounded-xl border border-shell-border bg-shell-bg px-5 py-5 font-sans text-sm leading-7 text-shell-text">
            {detail?.transcriptContent || 'No transcript text was saved for this asset.'}
          </pre>
        )}
      </div>
    </div>
  );

  if (mobile) {
    return (
      <MobileSheet open={Boolean(detail || loading || error)} onClose={onClose} title="Media Asset" fullHeight>
        {body}
      </MobileSheet>
    );
  }

  return (
    <div className="animate-slide-in-right fixed inset-y-4 right-4 z-40 w-[min(520px,calc(100vw-2rem))] shell-page-utility-tile rounded-xl border border-shell-border bg-shell-panel shadow-shell-xl">
      {body}
    </div>
  );
}
