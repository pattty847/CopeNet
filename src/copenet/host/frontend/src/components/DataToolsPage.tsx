import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Cable,
  Copy,
  Database,
  ExternalLink,
  Globe,
  LibraryBig,
  Link2,
  LoaderCircle,
  PanelRightOpen,
  PlayCircle,
  RadioTower,
  Sparkles,
  X,
  Video,
  Wrench,
} from 'lucide-react';
import { getMediaAssetDetail, importMediaFromUrl, listMediaAssets } from '../lib/appApi';
import { useAppStore } from '../store/useAppStore';
import { DataToolsRoute, MediaAsset, MediaAssetDetail } from '../types/backend';

function formatRelative(timestamp: string): string {
  const then = new Date(timestamp).getTime();
  if (!Number.isFinite(then)) return 'Recently';
  const seconds = Math.max(1, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return 'Just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return 'Unknown duration';
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins <= 0) return `${secs}s`;
  return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

function SectionBreadcrumb({ route, onBack }: { route: DataToolsRoute; onBack: () => void }) {
  const labels: Record<DataToolsRoute, string[]> = {
    hub: ['Data & Tools'],
    sources: ['Data & Tools', 'Data Sources'],
    media: ['Data & Tools', 'Data Sources', 'Media Imports'],
  };

  return (
    <div className="mb-5 flex items-center gap-3 text-sm text-shell-muted">
      {route !== 'hub' && (
        <button
          type="button"
          onClick={onBack}
          className="inline-flex h-10 items-center gap-2 rounded-full border border-shell-border bg-shell-panel px-4 font-medium text-shell-text transition hover:border-shell-border-strong"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
      )}
      <div className="inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em]">
        {labels[route].map((label, index) => (
          <span key={label} className="inline-flex items-center gap-2">
            <span className={index === labels[route].length - 1 ? 'text-shell-text' : 'text-shell-muted'}>{label}</span>
            {index < labels[route].length - 1 && <ArrowRight className="h-3 w-3 text-shell-muted" />}
          </span>
        ))}
      </div>
    </div>
  );
}

function HubCard({
  eyebrow,
  title,
  body,
  accent,
  onClick,
}: {
  eyebrow: string;
  title: string;
  body: string;
  accent: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-[28px] border border-shell-border bg-shell-panel px-5 py-5 text-left shadow-shell transition hover:-translate-y-0.5 hover:border-shell-border-strong"
    >
      <div className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-shell-muted">{eyebrow}</div>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-shell-text">{title}</h2>
          <p className="mt-3 text-sm leading-6 text-shell-muted">{body}</p>
        </div>
        <ArrowRight className={`mt-1 h-4 w-4 shrink-0 transition group-hover:translate-x-0.5 ${accent}`} />
      </div>
      <div className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-shell-text">
        <span>Open section</span>
        <ArrowRight className="h-4 w-4 text-shell-muted" />
      </div>
    </button>
  );
}

function DataToolsHub({ openSources }: { openSources: () => void }) {
  return (
    <div className="space-y-6">
      <section className="rounded-[34px] border border-shell-border bg-shell-panel px-7 py-7 shadow-shell">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <Wrench className="h-3.5 w-3.5 text-shell-accent" />
          Data &amp; Tools
        </div>
        <h1 className="max-w-4xl font-display text-5xl leading-[0.98] tracking-tight text-shell-text">
          Connect knowledge, feeds, and tools into one living context.
        </h1>
        <p className="mt-5 max-w-3xl text-base leading-7 text-shell-muted">
          This is where files, datasets, knowledge bases, and operator tools become part of the workspace. The point is not just to store them. It is to make them useful.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <HubCard eyebrow="Ground" title="Knowledge Bases" body="Curated context that can refresh, evolve, and stay anchored to the workspace." accent="text-shell-accent" />
        <HubCard eyebrow="Ingest" title="Data Sources" body="Feed media, web pages, APIs, and local files into the workbench." accent="text-shell-accent" onClick={openSources} />
        <HubCard eyebrow="Operate" title="Tool Catalog" body="Inspectable tool surfaces with safety rules and visible execution history." accent="text-shell-accent" />
        <HubCard eyebrow="Shape" title="Workspace Context" body="Preset combinations of data, prompts, and runtimes for the jobs you repeat." accent="text-shell-accent" />
      </section>

      <section className="rounded-[34px] border border-dashed border-shell-border bg-shell-panel px-8 py-10 text-center shadow-shell">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-3xl font-semibold tracking-tight text-shell-text">Ground the workspace in real sources, not floating context.</h2>
          <p className="mt-4 text-sm leading-7 text-shell-muted">
            Start with media imports today, then layer in web pages, documents, feeds, and knowledge destinations as CopeNet grows into a proper ingestion workspace.
          </p>
        </div>
      </section>
    </div>
  );
}

function SourceTypeCard({
  icon: Icon,
  title,
  body,
  eyebrow,
  action,
  onClick,
}: {
  icon: typeof Video;
  title: string;
  body: string;
  eyebrow: string;
  action: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 text-left shadow-shell transition hover:-translate-y-0.5 hover:border-shell-border-strong"
    >
      <div className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
        <Icon className="h-5 w-5" />
      </div>
      <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">{eyebrow}</div>
      <h2 className="mt-3 text-xl font-semibold text-shell-text">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-shell-muted">{body}</p>
      <div className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-shell-text">
        <span>{action}</span>
        <ArrowRight className="h-4 w-4 text-shell-muted transition group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

function DataSourcesPage({ openMedia }: { openMedia: () => void }) {
  return (
    <div className="space-y-6">
      <section className="rounded-[34px] border border-shell-border bg-shell-panel px-7 py-7 shadow-shell">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <Database className="h-3.5 w-3.5 text-shell-accent" />
          Data Sources
        </div>
        <h1 className="max-w-3xl font-display text-5xl leading-[0.98] tracking-tight text-shell-text">
          Bring raw outside material into CopeNet as working context.
        </h1>
        <p className="mt-5 max-w-3xl text-base leading-7 text-shell-muted">
          Source types become workspace assets first. Then agents, workflows, and knowledge features can actually build on something real.
        </p>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <div className="grid gap-4 md:grid-cols-2">
          <SourceTypeCard
            icon={Video}
            eyebrow="Ready now"
            title="Media Imports"
            body="Paste a video URL, capture captions or transcribe the audio, and turn it into a transcript-backed workspace asset."
            action="Open media imports"
            onClick={openMedia}
          />
          <SourceTypeCard
            icon={Globe}
            eyebrow="Next source"
            title="Web Pages"
            body="Cleanly scrape articles and pages into markdown-like content for later knowledge base and workspace use."
            action="Jina-style ingest next"
          />
          <SourceTypeCard
            icon={LibraryBig}
            eyebrow="Soon"
            title="Documents"
            body="Bring PDFs, notes, and local reports into CopeNet as grounded source material instead of temporary prompt attachments."
            action="Coming after web ingest"
          />
          <SourceTypeCard
            icon={RadioTower}
            eyebrow="Future"
            title="Feeds & APIs"
            body="Connect live or recurring data streams so workflows can operate on fresh sources instead of static context windows."
            action="Designing next"
          />
        </div>

        <div className="space-y-4">
          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Why this matters</div>
            <h2 className="text-xl font-semibold text-shell-text">CopeNet gets stronger when source material becomes reusable.</h2>
            <p className="mt-4 text-sm leading-6 text-shell-muted">
              Imported sources are the bridge between one-off chat and real work. Once something is ingested, it can be queried, summarized, filed into knowledge, or turned into a workflow.
            </p>
          </div>
          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Quick starts</div>
            <div className="space-y-3">
              {[
                'Import a YouTube clip and summarize the claims.',
                'Capture a livestream segment into your workspace.',
                'Bring an article in next and compare model summaries.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl border border-shell-border bg-shell-bg px-4 py-3 text-sm text-shell-text">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-shell-accent" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function MediaAssetRow({ asset, onOpen }: { asset: MediaAsset; onOpen: (asset: MediaAsset) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(asset)}
      className="w-full rounded-[24px] border border-shell-border bg-shell-bg px-5 py-4 text-left transition hover:-translate-y-0.5 hover:border-shell-border-strong"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
              <Video className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-base font-semibold text-shell-text">{asset.title}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-shell-muted">
                <span>{asset.transcriptSource || 'Transcript'}</span>
                <span>•</span>
                <span>{formatRelative(asset.createdAt)}</span>
                <span>•</span>
                <span>{formatDuration(asset.durationSeconds)}</span>
              </div>
            </div>
          </div>
          <p className="mt-4 text-sm leading-6 text-shell-muted">{asset.transcriptExcerpt || 'Transcript imported and ready to use.'}</p>
          {asset.sourceUrl && (
            <a
              href={asset.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-shell-text transition hover:text-shell-accent"
            >
              <Link2 className="h-4 w-4" />
              <span className="truncate">{asset.sourceUrl}</span>
            </a>
          )}
        </div>
        <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
          Open
        </div>
      </div>
    </button>
  );
}

function MediaAssetDrawer({
  detail,
  loading,
  error,
  onClose,
  onUseInAgents,
}: {
  detail: MediaAssetDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onUseInAgents: (detail: MediaAssetDetail) => void;
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

  return (
    <div className="fixed inset-y-6 right-6 z-40 w-[min(560px,calc(100vw-2rem))] rounded-[30px] border border-shell-border bg-shell-panel shadow-shell-xl">
      <div className="flex h-full flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-shell-border px-6 py-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Media Asset</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-shell-text">{detail?.title || 'Loading transcript…'}</h2>
            {detail?.sourceUrl && (
              <a href={detail.sourceUrl} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-shell-text hover:text-shell-accent">
                <ExternalLink className="h-4 w-4" />
                Open source
              </a>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-bg text-shell-text transition hover:border-shell-border-strong"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-shell-border px-6 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
          {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{detail.transcriptSource || 'Transcript'}</div>}
          {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatDuration(detail.durationSeconds)}</div>}
          {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatRelative(detail.createdAt)}</div>}
        </div>

        <div className="flex items-center gap-3 border-b border-shell-border px-6 py-4">
          <button
            type="button"
            onClick={() => detail && onUseInAgents(detail)}
            disabled={!detail}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl bg-shell-ink px-5 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PanelRightOpen className="h-4 w-4" />
            Use in Agents
          </button>
          <button
            type="button"
            onClick={() => void copyTranscript()}
            disabled={!detail?.transcriptContent}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-5 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Copy className="h-4 w-4" />
            Copy transcript
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
          {loading ? (
            <div className="flex items-center gap-3 rounded-[24px] border border-shell-border bg-shell-bg px-5 py-5 text-shell-muted">
              <LoaderCircle className="h-5 w-5 animate-spin text-shell-accent" />
              Loading transcript…
            </div>
          ) : error ? (
            <div className="rounded-[24px] border border-shell-border bg-shell-bg px-5 py-5 text-sm leading-6 text-shell-muted">{error}</div>
          ) : (
            <pre className="whitespace-pre-wrap rounded-[24px] border border-shell-border bg-shell-bg px-5 py-5 font-sans text-sm leading-7 text-shell-text">
              {detail?.transcriptContent || 'No transcript text was saved for this asset.'}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function MediaImportsPage() {
  const mediaAssets = useAppStore((state) => state.mediaAssets);
  const mediaAssetsLoaded = useAppStore((state) => state.mediaAssetsLoaded);
  const mediaImporting = useAppStore((state) => state.mediaImporting);
  const mediaImportError = useAppStore((state) => state.mediaImportError);
  const mediaImportStatus = useAppStore((state) => state.mediaImportStatus);
  const mediaImportProgress = useAppStore((state) => state.mediaImportProgress);
  const setMediaAssets = useAppStore((state) => state.setMediaAssets);
  const prependMediaAsset = useAppStore((state) => state.prependMediaAsset);
  const setMediaAssetsLoaded = useAppStore((state) => state.setMediaAssetsLoaded);
  const setMediaImporting = useAppStore((state) => state.setMediaImporting);
  const setMediaImportError = useAppStore((state) => state.setMediaImportError);
  const setMediaImportStatus = useAppStore((state) => state.setMediaImportStatus);
  const setMediaImportProgress = useAppStore((state) => state.setMediaImportProgress);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);
  const [url, setUrl] = useState('');
  const [capturedChunks, setCapturedChunks] = useState<string[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<MediaAsset | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<MediaAssetDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (mediaAssetsLoaded) return;
    void (async () => {
      try {
        const assets = await listMediaAssets();
        setMediaAssets(assets);
        setMediaAssetsLoaded(true);
      } catch (error) {
        setMediaImportError(error instanceof Error ? error.message : 'Failed to load media assets.');
      }
    })();
  }, [mediaAssetsLoaded, setMediaAssets, setMediaAssetsLoaded, setMediaImportError]);

  async function openAsset(asset: MediaAsset) {
    setSelectedAsset(asset);
    setSelectedDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await getMediaAssetDetail(asset.assetId);
      setSelectedDetail(detail);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : 'Failed to load transcript.');
    } finally {
      setDetailLoading(false);
    }
  }

  function useInAgents(detail: MediaAssetDetail) {
    const seed = `Use the imported media asset "${detail.title}" as context.\n\nSource URL: ${detail.sourceUrl || 'Unknown'}\nTranscript source: ${detail.transcriptSource || 'transcript'}\n\nPlease summarize the main points, extract the strongest claims, and note anything worth fact-checking.\n\nTranscript:\n${detail.transcriptContent}`;
    setDraftComposerSeed(seed);
    setDraftOpen(true);
    setCurrentSection('agents');
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextUrl = url.trim();
    if (!nextUrl || mediaImporting) return;
    setCapturedChunks([]);
    setMediaImporting(true);
    setMediaImportError(null);
    setMediaImportStatus('Preparing media import…');
    setMediaImportProgress(2);
    try {
      const asset = await importMediaFromUrl(nextUrl, {
        onProgress: (message, percent) => {
          setMediaImportStatus(message || 'Importing media…');
          setMediaImportProgress(percent);
        },
        onChunk: (text) => {
          setCapturedChunks((current) => [...current.slice(-5), text]);
        },
      });
      prependMediaAsset(asset);
      setMediaAssetsLoaded(true);
      setMediaImportStatus('Media imported into CopeNet.');
      setMediaImportProgress(100);
      setUrl('');
    } catch (error) {
      setMediaImportError(error instanceof Error ? error.message : 'Media import failed.');
      setMediaImportStatus(null);
      setMediaImportProgress(null);
    } finally {
      setMediaImporting(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_360px]">
        <div className="rounded-[34px] border border-shell-border bg-shell-panel px-7 py-7 shadow-shell">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <PlayCircle className="h-3.5 w-3.5 text-shell-accent" />
            Media Imports
          </div>
          <h1 className="max-w-3xl font-display text-5xl leading-[0.98] tracking-tight text-shell-text">
            Paste a video link and turn it into a transcript-backed workspace asset.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 text-shell-muted">
            CopeNet can pull captions when they exist, fall back to Whisper when they do not, and keep the result as a reusable source for later chat, knowledge, and workflow use.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div className="rounded-[28px] border border-shell-border bg-shell-bg p-3 shadow-shell">
              <div className="flex flex-col gap-3 md:flex-row md:items-center">
                <input
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="Paste a YouTube or media URL to import into CopeNet…"
                  className="h-14 flex-1 rounded-2xl border border-shell-border bg-shell-panel px-5 text-sm text-shell-text outline-none transition placeholder:text-shell-muted hover:border-shell-border-strong focus:border-shell-border-strong"
                />
                <button
                  type="submit"
                  disabled={!url.trim() || mediaImporting}
                  className="inline-flex h-14 items-center justify-center gap-2 rounded-2xl bg-shell-ink px-6 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-55"
                >
                  {mediaImporting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />}
                  Import media
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Captions first when available</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Whisper fallback when needed</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Saved as workspace asset</div>
            </div>
          </form>
        </div>

        <div className="space-y-4">
          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Import status</div>
            <div className="flex items-start gap-3">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
                {mediaImporting ? <LoaderCircle className="h-5 w-5 animate-spin" /> : <Cable className="h-5 w-5" />}
              </div>
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-shell-text">{mediaImporting ? 'Import running' : 'Ready for a new source'}</h2>
                <p className="mt-2 text-sm leading-6 text-shell-muted">
                  {mediaImportError || mediaImportStatus || 'Paste a link to bring a transcript-backed asset into CopeNet.'}
                </p>
              </div>
            </div>
            <div className="mt-5 h-2 overflow-hidden rounded-full bg-shell-bg">
              <div
                className="h-full rounded-full bg-shell-accent transition-[width] duration-300"
                style={{ width: `${mediaImportProgress ?? 0}%` }}
              />
            </div>
          </div>

          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">What this unlocks</div>
            <div className="space-y-3">
              {[
                'Chat with a transcript after import.',
                'Attach clips to future knowledge bases.',
                'Turn repeated imports into a workflow.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl border border-shell-border bg-shell-bg px-4 py-3 text-sm text-shell-text">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-shell-accent" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_320px]">
        <div className="rounded-[34px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Imported Assets</div>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-shell-text">Recent media ready for the workspace</h2>
            </div>
            <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
              {mediaAssets.length} assets
            </div>
          </div>

          <div className="space-y-3">
            {mediaAssets.length > 0 ? (
              mediaAssets.map((asset) => <MediaAssetRow key={asset.assetId} asset={asset} onOpen={openAsset} />)
            ) : (
              <div className="rounded-[24px] border border-dashed border-shell-border bg-shell-bg px-6 py-10 text-center">
                <h3 className="text-lg font-semibold text-shell-text">No media assets yet</h3>
                <p className="mt-3 text-sm leading-6 text-shell-muted">
                  Paste a video link above and CopeNet will turn it into the first reusable transcript source in this workspace.
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Incoming transcript</div>
            {capturedChunks.length > 0 ? (
              <div className="space-y-3">
                {capturedChunks.map((chunk, index) => (
                  <div key={`${chunk}-${index}`} className="rounded-2xl border border-shell-border bg-shell-bg px-4 py-3 text-sm leading-6 text-shell-muted">
                    {chunk}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-shell-muted">
                When a transcription is running, recent transcript chunks will appear here so the import feels alive instead of opaque.
              </p>
            )}
          </div>

          <div className="rounded-[28px] border border-shell-border bg-shell-panel px-6 py-6 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Next source</div>
            <h3 className="text-lg font-semibold text-shell-text">Web page ingest</h3>
            <p className="mt-3 text-sm leading-6 text-shell-muted">
              The next source after media should be clean webpage import, likely through a Jina-style fetch path so articles can land in CopeNet as readable source assets too.
            </p>
          </div>
        </div>
      </section>

      <MediaAssetDrawer
        detail={selectedDetail}
        loading={detailLoading}
        error={detailError}
        onClose={() => {
          setSelectedAsset(null);
          setSelectedDetail(null);
          setDetailError(null);
          setDetailLoading(false);
        }}
        onUseInAgents={useInAgents}
      />
    </div>
  );
}

export function DataToolsPage() {
  const route = useAppStore((state) => state.dataToolsRoute);
  const setRoute = useAppStore((state) => state.setDataToolsRoute);

  function handleBack() {
    if (route === 'media') {
      setRoute('sources');
      return;
    }
    setRoute('hub');
  }

  return (
    <div className="space-y-5">
      <SectionBreadcrumb route={route} onBack={handleBack} />
      {route === 'hub' && <DataToolsHub openSources={() => setRoute('sources')} />}
      {route === 'sources' && <DataSourcesPage openMedia={() => setRoute('media')} />}
      {route === 'media' && <MediaImportsPage />}
    </div>
  );
}
