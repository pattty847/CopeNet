import { useEffect, useRef, useState } from 'react';
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
  Upload,
  X,
  Video,
  Wrench,
} from 'lucide-react';
import { downloadMediaFromUrl, getMediaAssetDetail, importMediaFromUrl, listMediaAssets, uploadMediaFile } from '../lib/appApi';
import { buildAttachedMedia, buildMemeAgentsDraftSeed } from '../lib/mediaMemeBridge';
import { clampMediaAssetTitle, getMediaAssetCardBadgeLabel } from '../lib/mobileCopy';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { DataToolsRoute, MediaAsset, MediaAssetDetail } from '../types/backend';
import { MessagingSettingsPanel } from './MessagingSettingsPanel';
import { MobileSheet } from './mobile/MobileSheet';

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
    messaging: ['Data & Tools', 'Messaging'],
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2.5 text-sm text-shell-muted">
      {route !== 'hub' && (
        <button
          type="button"
          onClick={onBack}
          className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-shell-border bg-shell-panel px-3 text-[13px] font-medium text-shell-text transition-all duration-150 hover:border-shell-border-strong hover:shadow-shell"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
      )}
      <div className="inline-flex items-center gap-2 rounded-xl border border-shell-border bg-shell-panel px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.2em]">
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
      className="shell-page-utility-tile lift-sm group rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 text-left shadow-shell"
    >
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">{eyebrow}</div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-shell-text">{title}</h2>
          <p className="mt-2 text-[13px] leading-5 text-shell-muted">{body}</p>
        </div>
        <ArrowRight className={`mt-0.5 h-3.5 w-3.5 shrink-0 transition-transform duration-150 group-hover:translate-x-0.5 ${accent}`} />
      </div>
      <div className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 group-hover:text-shell-accent">
        <span>Open section</span>
        <ArrowRight className="h-3 w-3" />
      </div>
    </button>
  );
}

function DataToolsHub({ openSources, openMessaging }: { openSources: () => void; openMessaging: () => void }) {
  return (
    <div className="animate-fade-in-up space-y-3">
      <section className="shell-page-utility-hero rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-6 sm:py-5">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <Wrench className="h-3.5 w-3.5 text-shell-accent" />
          Data &amp; Tools
        </div>
        <h1 className="max-w-4xl font-display text-[2rem] leading-[1.02] tracking-tight text-shell-text sm:text-[2.6rem]">
          Connect knowledge, feeds, and tools into one living context.
        </h1>
        <p className="mt-4 max-w-3xl text-[14px] leading-6 text-shell-muted sm:mt-5 sm:text-base sm:leading-7">
          This is where files, datasets, knowledge bases, and operator tools become part of the workspace. The point is not just to store them. It is to make them useful.
        </p>
      </section>

      <section className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
        <HubCard eyebrow="Ground" title="Knowledge Bases" body="Curated context that can refresh, evolve, and stay anchored to the workspace." accent="text-shell-accent" />
        <HubCard eyebrow="Ingest" title="Data Sources" body="Feed media, web pages, APIs, and local files into the workbench." accent="text-shell-accent" onClick={openSources} />
        <HubCard eyebrow="Operate" title="Tool Catalog" body="Inspectable tool surfaces with safety rules and visible execution history." accent="text-shell-accent" />
        <HubCard eyebrow="Route" title="Messaging" body="Configure Telegram reachability, default runtimes, and chat-to-session routes." accent="text-shell-accent" onClick={openMessaging} />
      </section>

      <section className="shell-page-utility-tile rounded-[24px] border border-dashed border-shell-border bg-shell-panel px-6 py-8 text-center">
        <div className="mx-auto max-w-3xl">
          <h2 className="font-display text-2xl tracking-tight text-shell-text">Ground the workspace in real sources, not floating context.</h2>
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
      className="shell-page-utility-tile lift-sm group rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 text-left shadow-shell"
    >
      <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-shell-accent-soft text-shell-accent">
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">{eyebrow}</div>
      <h2 className="mt-2 text-[15px] font-semibold text-shell-text">{title}</h2>
      <p className="mt-2 text-[13px] leading-5 text-shell-muted">{body}</p>
      <div className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 group-hover:text-shell-accent">
        <span>{action}</span>
        <ArrowRight className="h-3 w-3 transition-transform duration-150 group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

function DataSourcesPage({ openMedia }: { openMedia: () => void }) {
  return (
    <div className="animate-fade-in-up space-y-3">
      <section className="shell-page-utility-hero rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-6 sm:py-5">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <Database className="h-3.5 w-3.5 text-shell-accent" />
          Data Sources
        </div>
        <h1 className="max-w-3xl font-display text-[2rem] leading-[1.02] tracking-tight text-shell-text sm:text-[2.6rem]">
          Bring raw outside material into CopeNet as working context.
        </h1>
        <p className="mt-4 max-w-3xl text-[14px] leading-6 text-shell-muted sm:mt-5 sm:text-base sm:leading-7">
          Source types become workspace assets first. Then agents, workflows, and knowledge features can actually build on something real.
        </p>
      </section>

      <section className="grid gap-2.5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
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

        <div className="space-y-2.5">
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Why this matters</div>
            <h2 className="text-xl font-semibold text-shell-text">CopeNet gets stronger when source material becomes reusable.</h2>
            <p className="mt-4 text-sm leading-6 text-shell-muted">
              Imported sources are the bridge between one-off chat and real work. Once something is ingested, it can be queried, summarized, filed into knowledge, or turned into a workflow.
            </p>
          </div>
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
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

function MessagingSettingsPage() {
  return (
    <div className="animate-fade-in-up space-y-3">
      <section className="shell-page-utility-hero rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-6 sm:py-5">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <RadioTower className="h-3.5 w-3.5 text-shell-accent" />
          Messaging
        </div>
        <h1 className="max-w-3xl font-display text-[2rem] leading-[1.02] tracking-tight text-shell-text sm:text-[2.6rem]">
          Wire Telegram into CopeNet without losing session truth.
        </h1>
        <p className="mt-4 max-w-3xl text-[14px] leading-6 text-shell-muted sm:mt-5 sm:text-base sm:leading-7">
          Set the runtime defaults, configure real destinations, and map Telegram chats or threads to specific CopeNet sessions before inbound routing goes fully live.
        </p>
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_320px]">
        <div className="shell-page-utility-tile rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-5 sm:py-5">
          <MessagingSettingsPanel />
        </div>
        <div className="space-y-3">
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">How it works</div>
            <div className="space-y-2 text-sm leading-6 text-shell-muted">
              <p>One Telegram chat or thread can map to one CopeNet session.</p>
              <p>Telegram runtime defaults seed new chat-anywhere sessions before slash-command overrides arrive.</p>
              <p>Destinations stay honest so approval-backed sends have a real local address book.</p>
            </div>
          </div>
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Next</div>
            <div className="space-y-2 text-sm leading-6 text-shell-muted">
              <p>Inbound Telegram messages can use these routes to continue the right session automatically.</p>
              <p>Model selection via settings is already here; slash-command model switching can layer on top later.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function MediaAssetRow({ asset, onOpen }: { asset: MediaAsset; onOpen: (asset: MediaAsset) => void }) {
  const isMobile = useIsMobile();
  const openLabel = getMediaAssetCardBadgeLabel(isMobile);

  return (
    <button
      type="button"
      onClick={() => onOpen(asset)}
      className="w-full rounded-[24px] border border-shell-border bg-shell-bg px-4 py-4 text-left transition hover:-translate-y-0.5 hover:border-shell-border-strong sm:px-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
              <Video className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h3
                className="overflow-hidden text-base font-semibold text-shell-text"
                style={
                  isMobile
                    ? {
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }
                    : undefined
                }
                title={asset.title}
              >
                {clampMediaAssetTitle(asset.title, isMobile)}
              </h3>
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
        {openLabel ? (
          <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
            {openLabel}
          </div>
        ) : null}
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
  onOpenInMemeLab,
  mobile = false,
}: {
  detail: MediaAssetDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
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
        {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatDuration(detail.durationSeconds)}</div>}
        {detail && <div className="rounded-full border border-shell-border bg-shell-bg px-3 py-1">{formatRelative(detail.createdAt)}</div>}
      </div>

      <div className={`flex flex-wrap items-center gap-3 border-b border-shell-border ${mobile ? 'px-4 py-3' : 'px-6 py-4'}`}>
        <button
          type="button"
          onClick={() => detail && onOpenInMemeLab(detail)}
          disabled={!detail}
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl bg-shell-ink px-5 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          <Sparkles className="h-4 w-4" />
          Open in Meme Lab
        </button>
        <button
          type="button"
          onClick={() => detail && onUseInAgents(detail)}
          disabled={!detail}
          className={`inline-flex h-11 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-5 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-50 ${mobile ? 'w-full' : ''}`}
        >
          <PanelRightOpen className="h-4 w-4" />
          Use in Agents
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
      </div>

      <div className={`min-h-0 flex-1 overflow-auto ${mobile ? 'px-4 py-4' : 'px-6 py-5'}`}>
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
  );

  if (mobile) {
    return (
      <MobileSheet open={Boolean(detail || loading || error)} onClose={onClose} title="Media Asset" fullHeight>
        {body}
      </MobileSheet>
    );
  }

  return (
    <div className="animate-slide-in-right fixed inset-y-4 right-4 z-40 w-[min(520px,calc(100vw-2rem))] shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel shadow-shell-xl">
      {body}
    </div>
  );
}

function MediaImportsPage() {
  const isMobile = useIsMobile();
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
  const setWorkflowsRoute = useAppStore((state) => state.setWorkflowsRoute);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);
  const setMemeLabSeedAsset = useAppStore((state) => state.setMemeLabSeedAsset);
  const [url, setUrl] = useState('');
  const [capturedChunks, setCapturedChunks] = useState<string[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<MediaAsset | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<MediaAssetDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mediaAction, setMediaAction] = useState<'transcribe' | 'download' | 'both' | 'upload' | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
    const seed = buildMemeAgentsDraftSeed({ attachedMedia: buildAttachedMedia(detail) });
    setDraftComposerSeed(seed);
    setDraftOpen(true);
    setCurrentSection('agents');
  }

  function openInMemeLab(detail: MediaAssetDetail) {
    setMemeLabSeedAsset(detail);
    setCurrentSection('workflows');
    setWorkflowsRoute('meme-lab');
  }

  async function handleTranscribe(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextUrl = url.trim();
    if (!nextUrl || mediaImporting) return;
    setCapturedChunks([]);
    setMediaAction('transcribe');
    setMediaImporting(true);
    setMediaImportError(null);
    setMediaImportStatus('Preparing transcription…');
    setMediaImportProgress(2);
    try {
      const asset = await importMediaFromUrl(nextUrl, {
        onProgress: (message, percent) => {
          setMediaImportStatus(message || 'Transcribing media…');
          setMediaImportProgress(percent);
        },
        onChunk: (text) => {
          setCapturedChunks((current) => [...current.slice(-5), text]);
        },
      });
      prependMediaAsset(asset);
      setMediaAssetsLoaded(true);
      setMediaImportStatus('Transcript added to CopeNet.');
      setMediaImportProgress(100);
      await openAsset(asset);
      setUrl('');
    } catch (error) {
      setMediaImportError(error instanceof Error ? error.message : 'Media transcription failed.');
      setMediaImportStatus(null);
      setMediaImportProgress(null);
    } finally {
      setMediaImporting(false);
      setMediaAction(null);
    }
  }

  async function handleDownload() {
    const nextUrl = url.trim();
    if (!nextUrl || mediaImporting) return;
    setCapturedChunks([]);
    setMediaAction('download');
    setMediaImporting(true);
    setMediaImportError(null);
    setMediaImportStatus('Preparing download…');
    setMediaImportProgress(15);
    try {
      await downloadMediaFromUrl(nextUrl);
      setMediaImportStatus('Download sent to your browser.');
      setMediaImportProgress(100);
    } catch (error) {
      setMediaImportError(error instanceof Error ? error.message : 'Media download failed.');
      setMediaImportStatus(null);
      setMediaImportProgress(null);
    } finally {
      setMediaImporting(false);
      setMediaAction(null);
    }
  }

  async function handleDoBoth() {
    const nextUrl = url.trim();
    if (!nextUrl || mediaImporting) return;
    setCapturedChunks([]);
    setMediaAction('both');
    setMediaImporting(true);
    setMediaImportError(null);
    setMediaImportStatus('Preparing download…');
    setMediaImportProgress(5);
    try {
      await downloadMediaFromUrl(nextUrl);
      setMediaImportStatus('Download sent to your browser. Transcribing into CopeNet…');
      setMediaImportProgress(24);
      const asset = await importMediaFromUrl(nextUrl, {
        onProgress: (message, percent) => {
          setMediaImportStatus(message || 'Transcribing media…');
          setMediaImportProgress(percent != null ? Math.max(percent, 24) : percent);
        },
        onChunk: (text) => {
          setCapturedChunks((current) => [...current.slice(-5), text]);
        },
      });
      prependMediaAsset(asset);
      setMediaAssetsLoaded(true);
      setMediaImportStatus('Downloaded and added to Meme-ready assets.');
      setMediaImportProgress(100);
      await openAsset(asset);
      setUrl('');
    } catch (error) {
      setMediaImportError(error instanceof Error ? error.message : 'Media download/transcription failed.');
      setMediaImportStatus(null);
      setMediaImportProgress(null);
    } finally {
      setMediaImporting(false);
      setMediaAction(null);
    }
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || mediaImporting) return;
    setCapturedChunks([]);
    setMediaAction('upload');
    setMediaImporting(true);
    setMediaImportError(null);
    setMediaImportStatus(`Uploading ${file.name}…`);
    setMediaImportProgress(12);
    try {
      const asset = await uploadMediaFile(file);
      prependMediaAsset(asset);
      setMediaAssetsLoaded(true);
      setMediaImportStatus('Upload complete. Transcript added to CopeNet.');
      setMediaImportProgress(100);
      await openAsset(asset);
    } catch (error) {
      setMediaImportError(error instanceof Error ? error.message : 'Media upload failed.');
      setMediaImportStatus(null);
      setMediaImportProgress(null);
    } finally {
      setMediaImporting(false);
      setMediaAction(null);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-3">
      <section className="grid gap-2.5 xl:grid-cols-[minmax(0,1.45fr)_360px]">
        <div className="shell-page-utility-hero rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-6 sm:py-5">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <PlayCircle className="h-3.5 w-3.5 text-shell-accent" />
            Media Imports
          </div>
          <h1 className="max-w-3xl font-display text-[2rem] leading-[1.02] tracking-tight text-shell-text sm:text-[2.6rem]">
            Paste a video link to transcribe it into CopeNet or download it straight to your device.
          </h1>
          <p className="mt-4 max-w-3xl text-[14px] leading-6 text-shell-muted sm:mt-5 sm:text-base sm:leading-7">
            Transcribe keeps a reusable transcript-backed asset inside CopeNet. Download skips the workspace asset and hands the video straight back to Safari or your desktop browser.
          </p>

          <form onSubmit={handleTranscribe} className="mt-6 space-y-4 sm:mt-8">
            <div className="rounded-[28px] border border-shell-border bg-shell-bg p-3 shadow-shell">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
                <input
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="Paste a YouTube or media URL for transcription or download…"
                  className="h-14 min-w-0 flex-1 rounded-2xl border border-shell-border bg-shell-panel px-5 text-sm text-shell-text outline-none transition placeholder:text-shell-muted hover:border-shell-border-strong focus:border-shell-border-strong"
                />
                <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 xl:flex xl:flex-wrap xl:justify-end">
                  <button
                    type="submit"
                    disabled={!url.trim() || mediaImporting}
                    className="inline-flex h-14 min-w-0 items-center justify-center gap-2 rounded-2xl bg-shell-ink px-4 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-55 lg:px-5"
                  >
                    {mediaImporting && mediaAction === 'transcribe' ? <LoaderCircle className="h-4 w-4 animate-spin shrink-0" /> : <Video className="h-4 w-4 shrink-0" />}
                    <span className="truncate">{isMobile ? 'Transcribe into CopeNet' : 'Transcribe'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDownload()}
                    disabled={!url.trim() || mediaImporting}
                    className="inline-flex h-14 min-w-0 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-4 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-55 lg:px-5"
                  >
                    {mediaImporting && mediaAction === 'download' ? <LoaderCircle className="h-4 w-4 animate-spin shrink-0" /> : <ExternalLink className="h-4 w-4 shrink-0" />}
                    <span className="truncate">{isMobile ? 'Download only' : 'Download'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDoBoth()}
                    disabled={!url.trim() || mediaImporting}
                    className="inline-flex h-14 min-w-0 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-accent-soft px-4 text-sm font-semibold text-shell-accent transition hover:border-shell-accent/40 disabled:cursor-not-allowed disabled:opacity-55 lg:px-5"
                    title="Download and transcribe"
                  >
                    {mediaImporting && mediaAction === 'both' ? <LoaderCircle className="h-4 w-4 animate-spin shrink-0" /> : <Sparkles className="h-4 w-4 shrink-0" />}
                    <span className="truncate">{isMobile ? 'Download + transcribe' : 'Both'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={mediaImporting}
                    className="inline-flex h-14 min-w-0 items-center justify-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-4 text-sm font-semibold text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-55 lg:px-5"
                  >
                    {mediaImporting && mediaAction === 'upload' ? <LoaderCircle className="h-4 w-4 animate-spin shrink-0" /> : <Upload className="h-4 w-4 shrink-0" />}
                    <span className="truncate">{isMobile ? 'Upload video / media' : 'Upload Media'}</span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="video/*,audio/*"
                    capture="environment"
                    className="hidden"
                    onChange={(event) => void handleFileSelected(event)}
                  />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs font-semibold uppercase tracking-[0.18em] text-shell-muted">
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Captions first when available</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Whisper fallback when needed</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Transcribe saves a workspace asset</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Download skips CopeNet storage</div>
              <div className="rounded-full border border-shell-border bg-shell-panel px-3 py-1">Upload from phone camera roll or files</div>
            </div>
          </form>
        </div>

        <div className="space-y-2.5">
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Import status</div>
            <div className="flex items-start gap-3">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
                {mediaImporting ? <LoaderCircle className="h-5 w-5 animate-spin" /> : <Cable className="h-5 w-5" />}
              </div>
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-shell-text">
                  {mediaImporting
                    ? mediaAction === 'download'
                      ? 'Download running'
                      : mediaAction === 'both'
                        ? 'Download + transcription running'
                        : mediaAction === 'upload'
                          ? 'Upload + transcription running'
                          : 'Transcription running'
                    : 'Ready for a new source'}
                </h2>
                <p className="mt-2 text-sm leading-6 text-shell-muted">
                  {mediaImportError || mediaImportStatus || 'Paste a link to either add a transcript-backed asset to CopeNet or download the source video.'}
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

          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">What this unlocks</div>
            <div className="space-y-3">
              {[
                'Transcribe a video into a reusable workspace asset.',
                'Download raw clips straight to Safari or your desktop browser.',
                'Upload videos from your phone into transcript-backed workspace assets.',
                'Turn repeated media pulls into a meme-friendly workflow later.',
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

      <section className="grid gap-2.5 xl:grid-cols-[minmax(0,1.55fr)_320px]">
        <div className="rounded-[34px] border border-shell-border bg-shell-panel px-4 py-5 shadow-shell sm:px-6 sm:py-6">
          <div className={`mb-5 flex gap-4 ${isMobile ? 'flex-col items-start' : 'items-center justify-between'}`}>
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Imported Assets</div>
              <h2 className="mt-2 text-xl font-semibold tracking-tight text-shell-text sm:text-2xl">Recent media ready for the workspace</h2>
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

        <div className="space-y-2.5">
          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
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
                When a transcription is running, recent transcript chunks will appear here so the ingest feels alive instead of opaque.
              </p>
            )}
          </div>

          <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
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
        mobile={isMobile}
        onClose={() => {
          setSelectedAsset(null);
          setSelectedDetail(null);
          setDetailError(null);
          setDetailLoading(false);
        }}
        onUseInAgents={useInAgents}
        onOpenInMemeLab={openInMemeLab}
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
    <div className="space-y-3">
      <SectionBreadcrumb route={route} onBack={handleBack} />
      {route === 'hub' && <DataToolsHub openSources={() => setRoute('sources')} openMessaging={() => setRoute('messaging')} />}
      {route === 'sources' && <DataSourcesPage openMedia={() => setRoute('media')} />}
      {route === 'media' && <MediaImportsPage />}
      {route === 'messaging' && <MessagingSettingsPage />}
    </div>
  );
}
