import { useEffect, useMemo } from 'react';
import {
  ArrowLeft,
  Clock,
  FlaskConical,
  Grid3x3,
  History,
  Link2,
  MessageSquareText,
  Pin,
  Rows3,
  SendHorizontal,
  Swords,
  Trash2,
  Trophy,
  Zap,
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { Spinner } from '../../components/Spinner';
import { useIsMobile } from '../../lib/responsive';
import { MobileSheet } from '../../components/mobile/MobileSheet';
import { MemeArena } from './MemeArena';
import { MemeCandidateCard } from './MemeCandidateCard';
import { MemeGallery } from './MemeGallery';
import { MemeLabComposer } from './MemeLabComposer';
import type { MemeAttachedMedia, MemeGeneration, MemeRefinementMessage, MemeViewMode } from './types';
import { useMemeLab } from './useMemeLab';

interface MemeLabProps {
  onExit: () => void;
}

export function MemeLab({ onExit }: MemeLabProps) {
  const state = useMemeLab();
  const isMobile = useIsMobile();
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const mobileMemeHistoryOpen = useAppStore((s) => s.mobileMemeHistoryOpen);
  const setMobileMemeHistoryOpen = useAppStore((s) => s.setMobileMemeHistoryOpen);
  const mobileMemeKeepersOpen = useAppStore((s) => s.mobileMemeKeepersOpen);
  const setMobileMemeKeepersOpen = useAppStore((s) => s.setMobileMemeKeepersOpen);

  const {
    brief,
    patchBrief,
    clearSourceAsset,
    generate,
    cancelGenerate,
    isGenerating,
    generationError,
    openInAgents,
    generations,
    activeGeneration,
    setActive,
    deleteGeneration,
    clearAll,
    viewMode,
    setViewMode,
    rankings,
    bumpScore,
    togglePin,
    arena,
    ensureArenaPair,
    rotateArenaRight,
    setArena,
    isRefining,
    refinementError,
    refinementInput,
    setRefinementInput,
    refinementMessages,
    submitRefinement,
  } = state;

  // Keyboard shortcut: A for Arena, G for Gallery, S for Stream
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key.toLowerCase() === 'a') setViewMode('arena');
      else if (e.key.toLowerCase() === 'g') setViewMode('gallery');
      else if (e.key.toLowerCase() === 's') setViewMode('stream');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setViewMode]);

  const pinnedCount = useMemo(() => Object.values(rankings).filter((r) => r.pinned).length, [rankings]);
  const winnerCount = useMemo(
    () => Object.values(rankings).filter((r) => r.verdict === 'winner').length,
    [rankings],
  );

  const sendToArena = (candidateId: string) => {
    setArena((prev) => {
      if (prev.leftId === candidateId || prev.rightId === candidateId) return prev;
      if (!prev.leftId) return { ...prev, leftId: candidateId };
      if (!prev.rightId) return { ...prev, rightId: candidateId };
      // Both slots full — replace right with the newcomer, bump right → left
      return { leftId: prev.rightId, rightId: candidateId, lastVerdict: prev.lastVerdict };
    });
    setViewMode('arena');
  };

  if (isMobile) {
    return (
      <div className="relative flex h-full min-h-0 animate-fade-in-up flex-col gap-3">
        <section className="overflow-hidden rounded-[22px] border border-shell-border bg-gradient-to-br from-shell-panel via-shell-panel to-shell-panel-strong px-4 py-3 shadow-shell">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <button
                type="button"
                onClick={onExit}
                className="focus-ring inline-flex items-center gap-1 rounded-lg border border-shell-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
              >
                <ArrowLeft className="h-3 w-3" />
                workflows
              </button>
              <h1 className="mt-2 font-display text-[1.55rem] leading-none tracking-tight text-shell-text">Meme Lab</h1>
              <div className="mt-1 font-mono text-[11px] leading-5 tabular-nums text-shell-muted">
                phone workbench · meme + arena
              </div>
              <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-shell-muted">
                <span className="inline-flex items-center gap-1 rounded-full border border-shell-border bg-shell-panel px-2 py-1">
                  <Pin className="h-3 w-3 text-shell-accent" />
                  {pinnedCount} pinned
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-shell-border bg-shell-panel px-2 py-1">
                  <Trophy className="h-3 w-3 text-shell-success" />
                  {winnerCount} crowned
                </span>
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMobileMemeHistoryOpen(true)}
              className="flex-1 rounded-xl border border-shell-border bg-shell-panel px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-shell-text"
            >
              History
            </button>
            <button
              type="button"
              onClick={() => setMobileMemeKeepersOpen(true)}
              className="flex-1 rounded-xl border border-shell-border bg-shell-panel px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-shell-text"
            >
              Keepers
            </button>
          </div>
        </section>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pb-2">
          {brief.attachedMedia && (
            <SourceAssetCard
              asset={brief.attachedMedia}
              onClear={clearSourceAsset}
              onOpenInAgents={openInAgents}
            />
          )}
          <MemeLabComposer
            brief={brief}
            patchBrief={patchBrief}
            onGenerate={generate}
            onCancel={cancelGenerate}
            isGenerating={isGenerating}
            error={generationError}
          />
          <ModeTabs viewMode={viewMode} setViewMode={setViewMode} activeGeneration={activeGeneration} />
          <div className="min-h-[45svh]">
            {activeGeneration ? (
              viewMode === 'arena' ? (
                <MemeArena
                  generation={activeGeneration}
                  rankings={rankings}
                  arena={arena}
                  ensurePair={ensureArenaPair}
                  rotate={rotateArenaRight}
                  onBumpScore={bumpScore}
                  onTogglePin={togglePin}
                  onSelectLeft={(id) => setArena((prev) => ({ ...prev, leftId: id }))}
                  onSelectRight={(id) => setArena((prev) => ({ ...prev, rightId: id }))}
                />
              ) : viewMode === 'gallery' ? (
                <MemeGallery
                  generation={activeGeneration}
                  rankings={rankings}
                  onBumpScore={bumpScore}
                  onTogglePin={togglePin}
                  onSendToArena={sendToArena}
                />
              ) : (
                <StreamView
                  generation={activeGeneration}
                  rankings={rankings}
                  onBumpScore={bumpScore}
                  onTogglePin={togglePin}
                  onSendToArena={sendToArena}
                />
              )
            ) : (
              <EmptyCenter isGenerating={isGenerating} />
            )}
          </div>
          <RefinementPanel
            hasGeneration={Boolean(activeGeneration)}
            attachedMedia={brief.attachedMedia}
            messages={refinementMessages}
            input={refinementInput}
            onInputChange={setRefinementInput}
            onSubmit={submitRefinement}
            onOpenInAgents={openInAgents}
            isRefining={isRefining}
            error={refinementError}
          />
        </div>

        <MobileSheet open={mobileMemeHistoryOpen} onClose={() => setMobileMemeHistoryOpen(false)} title="History" fullHeight>
          <HistoryPanel
            generations={generations}
            activeId={activeGeneration?.id ?? null}
            onSelect={(id) => {
              setActive(id);
              setMobileMemeHistoryOpen(false);
            }}
            onDelete={deleteGeneration}
            onClear={clearAll}
          />
        </MobileSheet>

        <MobileSheet open={mobileMemeKeepersOpen} onClose={() => setMobileMemeKeepersOpen(false)} title="Keepers" fullHeight>
          <KeeperRail rankings={rankings} generations={generations} />
        </MobileSheet>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 animate-fade-in-up flex-col gap-3">
      {/* Top banner */}
      <section className="flex flex-wrap items-center justify-between gap-3 overflow-hidden rounded-[22px] border border-shell-border bg-gradient-to-br from-shell-panel via-shell-panel to-shell-panel-strong px-5 py-3.5 shadow-shell">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onExit}
            className="focus-ring inline-flex items-center gap-1 rounded-lg border border-shell-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
          >
            <ArrowLeft className="h-3 w-3" />
            workflows
          </button>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
            <FlaskConical className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-[1.6rem] leading-none tracking-tight text-shell-text">Meme Lab</h1>
              <span className="rounded-full border border-shell-accent/30 bg-shell-accent-soft px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.24em] text-shell-accent">
                configured page
              </span>
            </div>
            <div className="mt-0.5 font-mono text-[11px] tabular-nums text-shell-muted">
              local ideation · rank · arena · keeper wall
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums text-shell-muted">
          <span className="inline-flex items-center gap-1">
            <Pin className="h-3 w-3 text-shell-accent" />
            {pinnedCount} pinned
          </span>
          <span className="text-shell-border-strong">·</span>
          <span className="inline-flex items-center gap-1">
            <Trophy className="h-3 w-3 text-shell-success" />
            {winnerCount} crowned
          </span>
          <button
            type="button"
            onClick={() => setCommandPaletteOpen(true)}
            className="ml-2 rounded-md border border-shell-border px-2 py-1 text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
            title="Open palette"
          >
            ⌘K
          </button>
        </div>
      </section>

      {/* Main workbench: Composer | Workspace | History */}
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[340px_minmax(0,1fr)_260px] xl:grid-cols-[360px_minmax(0,1fr)_300px]">
        {/* Left: Composer */}
        <div className="min-h-0">
          <div className="flex h-full min-h-0 flex-col gap-3">
            {brief.attachedMedia && (
              <SourceAssetCard
                asset={brief.attachedMedia}
                onClear={clearSourceAsset}
                onOpenInAgents={openInAgents}
              />
            )}
            <MemeLabComposer
              brief={brief}
              patchBrief={patchBrief}
              onGenerate={generate}
              onCancel={cancelGenerate}
              isGenerating={isGenerating}
              error={generationError}
            />
          </div>
        </div>

        {/* Center: workspace */}
        <div className="flex min-h-0 flex-col gap-3">
          <ModeTabs
            viewMode={viewMode}
            setViewMode={setViewMode}
            activeGeneration={activeGeneration}
          />
          <div className="min-h-0 flex flex-1 flex-col gap-3 overflow-hidden">
            <div className="min-h-0 flex-1 overflow-hidden">
              {activeGeneration ? (
                viewMode === 'arena' ? (
                  <MemeArena
                    generation={activeGeneration}
                    rankings={rankings}
                    arena={arena}
                    ensurePair={ensureArenaPair}
                    rotate={rotateArenaRight}
                    onBumpScore={bumpScore}
                    onTogglePin={togglePin}
                    onSelectLeft={(id) => setArena((prev) => ({ ...prev, leftId: id }))}
                    onSelectRight={(id) => setArena((prev) => ({ ...prev, rightId: id }))}
                  />
                ) : viewMode === 'gallery' ? (
                  <MemeGallery
                    generation={activeGeneration}
                    rankings={rankings}
                    onBumpScore={bumpScore}
                    onTogglePin={togglePin}
                    onSendToArena={sendToArena}
                  />
                ) : (
                  <StreamView
                    generation={activeGeneration}
                    rankings={rankings}
                    onBumpScore={bumpScore}
                    onTogglePin={togglePin}
                    onSendToArena={sendToArena}
                  />
                )
              ) : (
                <EmptyCenter isGenerating={isGenerating} />
              )}
            </div>
            <RefinementPanel
              hasGeneration={Boolean(activeGeneration)}
              attachedMedia={brief.attachedMedia}
              messages={refinementMessages}
              input={refinementInput}
              onInputChange={setRefinementInput}
              onSubmit={submitRefinement}
              onOpenInAgents={openInAgents}
              isRefining={isRefining}
              error={refinementError}
            />
          </div>
        </div>

        {/* Right: History + keeper rail */}
        <div className="flex min-h-0 flex-col gap-3">
          <HistoryPanel
            generations={generations}
            activeId={activeGeneration?.id ?? null}
            onSelect={setActive}
            onDelete={deleteGeneration}
            onClear={clearAll}
          />
          <KeeperRail rankings={rankings} generations={generations} />
        </div>
      </section>
    </div>
  );
}

// ---------- Mode tabs ----------

function ModeTabs({
  viewMode,
  setViewMode,
  activeGeneration,
}: {
  viewMode: MemeViewMode;
  setViewMode: (m: MemeViewMode) => void;
  activeGeneration: MemeGeneration | null;
}) {
  const tabs: Array<{ id: MemeViewMode; label: string; icon: typeof Rows3; key: string }> = [
    { id: 'stream', label: 'Stream', icon: Rows3, key: 'S' },
    { id: 'gallery', label: 'Gallery', icon: Grid3x3, key: 'G' },
    { id: 'arena', label: 'Arena', icon: Swords, key: 'A' },
  ];
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-[16px] border border-shell-border bg-shell-panel px-3 py-2 shadow-shell">
      <div className="flex w-full gap-1 sm:w-auto">
        {tabs.map((t) => {
          const Icon = t.icon;
          const active = viewMode === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setViewMode(t.id)}
              className={`inline-flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em] transition-all sm:flex-none ${
                active
                  ? 'bg-shell-accent-soft text-shell-accent shadow-[0_0_0_1px_var(--color-shell-accent-soft)_inset]'
                  : 'text-shell-muted hover:bg-shell-panel-strong hover:text-shell-text'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
              <kbd className="ml-1 hidden rounded border border-shell-border bg-shell-panel-strong px-1 py-0 text-[9px] text-shell-muted sm:inline">
                {t.key}
              </kbd>
            </button>
          );
        })}
      </div>
      {activeGeneration && (
        <div className="font-mono text-[10px] tabular-nums text-shell-muted">
          <span className="text-shell-accent">gen</span>{' '}
          <span>{activeGeneration.id.slice(-6)}</span>{' '}
          <span className="text-shell-border-strong">·</span>{' '}
          <span>{activeGeneration.candidates.length} candidates</span>
          {activeGeneration.source === 'mock' && (
            <span className="ml-2 rounded bg-shell-accent/10 px-1.5 py-0.5 uppercase tracking-wider text-shell-accent">
              mock
            </span>
          )}
          {activeGeneration.latencyMs != null && (
            <span className="ml-2">
              {activeGeneration.latencyMs < 1000
                ? `${activeGeneration.latencyMs}ms`
                : `${(activeGeneration.latencyMs / 1000).toFixed(2)}s`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- Stream view ----------

function StreamView({
  generation,
  rankings,
  onBumpScore,
  onTogglePin,
  onSendToArena,
}: {
  generation: MemeGeneration;
  rankings: Record<string, import('./types').MemeRanking>;
  onBumpScore: (id: string, delta: number) => void;
  onTogglePin: (id: string) => void;
  onSendToArena: (id: string) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pr-1">
      {generation.warnings.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 rounded-lg border border-shell-accent/20 bg-shell-accent/5 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-shell-accent">
          {generation.warnings.map((w, i) => (
            <li key={i}>▸ {w}</li>
          ))}
        </ul>
      )}
      <div className="space-y-3">
        {generation.candidates.map((c, i) => (
          <MemeCandidateCard
            key={c.id}
            candidate={c}
            ranking={rankings[c.id] ?? null}
            index={i}
            variant="stream"
            onBumpScore={onBumpScore}
            onTogglePin={onTogglePin}
            onSendToArena={onSendToArena}
          />
        ))}
      </div>
    </div>
  );
}

function SourceAssetCard({
  asset,
  onClear,
  onOpenInAgents,
}: {
  asset: MemeAttachedMedia;
  onClear: () => void;
  onOpenInAgents: () => void;
}) {
  return (
    <section className="rounded-[18px] border border-shell-border bg-shell-panel shadow-shell">
      <div className="flex items-start justify-between gap-3 border-b border-shell-border px-4 py-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Source Asset</div>
          <h3 className="mt-1 text-sm font-semibold text-shell-text">{asset.title}</h3>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-shell-muted">
            {asset.transcriptSource || 'transcript'}
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="rounded-md border border-shell-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-error/40 hover:text-shell-error"
        >
          clear
        </button>
      </div>
      <div className="space-y-3 px-4 py-3">
        <p className="text-sm leading-6 text-shell-muted">
          {asset.transcriptPack.summary || asset.transcriptExcerpt || 'Transcript-backed media attached to this brief.'}
        </p>
        {asset.transcriptPack.keyLines.length > 0 && (
          <div className="space-y-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-shell-muted">Key lines</div>
            <ul className="space-y-1 text-sm text-shell-text">
              {asset.transcriptPack.keyLines.slice(0, 2).map((line) => (
                <li key={line} className="truncate">- {line}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenInAgents}
            className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-shell-border bg-shell-bg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-shell-text"
          >
            <MessageSquareText className="h-3.5 w-3.5" />
            Open in Agents
          </button>
          {asset.sourceUrl && (
            <a
              href={asset.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-shell-border bg-shell-bg px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-shell-text"
            >
              <Link2 className="h-3.5 w-3.5" />
              Source
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

function RefinementPanel({
  hasGeneration,
  attachedMedia,
  messages,
  input,
  onInputChange,
  onSubmit,
  onOpenInAgents,
  isRefining,
  error,
}: {
  hasGeneration: boolean;
  attachedMedia: MemeAttachedMedia | null;
  messages: MemeRefinementMessage[];
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onOpenInAgents: () => void;
  isRefining: boolean;
  error: string | null;
}) {
  const canSubmit = Boolean(input.trim()) && hasGeneration;
  return (
    <section className="flex min-h-[220px] flex-col overflow-hidden rounded-[18px] border border-shell-border bg-shell-panel shadow-shell">
      <header className="flex items-center justify-between gap-3 border-b border-shell-border px-4 py-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Refine</div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-shell-muted">
            post iteration chat
          </div>
        </div>
        <button
          type="button"
          onClick={onOpenInAgents}
          disabled={!attachedMedia}
          className="rounded-md border border-shell-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent disabled:opacity-50"
        >
          Agents handoff
        </button>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <div className="rounded-xl border border-dashed border-shell-border bg-shell-panel-strong/30 px-4 py-4 text-sm leading-6 text-shell-muted">
            {hasGeneration
              ? 'Ask for sharper overlays, meaner framing, stronger transcript contamination, or different artifact shells.'
              : 'Generate a meme set first, then refine it conversationally here.'}
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`rounded-xl px-4 py-3 text-sm leading-6 ${
                message.role === 'user'
                  ? 'ml-6 border border-shell-accent/20 bg-shell-accent-soft text-shell-text'
                  : 'mr-6 border border-shell-border bg-shell-bg text-shell-muted'
              }`}
            >
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-shell-muted">
                {message.role}
              </div>
              {message.content}
            </div>
          ))
        )}
        {error && (
          <div className="rounded-xl border border-shell-error/20 bg-shell-error/10 px-4 py-3 text-sm text-shell-error">
            {error}
          </div>
        )}
      </div>
      <div className="border-t border-shell-border px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder={hasGeneration ? 'make it meaner, tighten to the narration, push the artifact shell…' : 'Generate once, then refine here.'}
            disabled={!hasGeneration || isRefining}
            className="flex-1 rounded-xl border border-shell-border bg-shell-bg px-3 py-2 text-sm text-shell-text outline-none transition placeholder:text-shell-muted disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit || isRefining}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-shell-ink px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60 sm:justify-start"
          >
            {isRefining ? <Spinner variant="flip" className="text-white" /> : <SendHorizontal className="h-4 w-4" />}
            Refine
          </button>
        </div>
      </div>
    </section>
  );
}

// ---------- Empty state ----------

function EmptyCenter({ isGenerating }: { isGenerating: boolean }) {
  return (
    <div className="flex h-full items-center justify-center rounded-[22px] border border-dashed border-shell-border bg-shell-panel/40 px-8 py-12 text-center">
      <div className="max-w-md">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
          {isGenerating ? <Spinner variant="flip" /> : <Zap className="h-5 w-5" />}
        </div>
        <h3 className="font-display text-[1.8rem] leading-tight tracking-tight text-shell-text">
          {isGenerating ? 'Cooking variants…' : 'A blank workbench.'}
        </h3>
        <p className="mt-2 font-mono text-[12px] leading-relaxed text-shell-muted">
          {isGenerating
            ? 'the local model is writing drafts — keep the brief sharp for next time'
            : 'fill in the brief on the left and hit generate. ⌘+Enter fires from anywhere.'}
        </p>
      </div>
    </div>
  );
}

// ---------- History panel ----------

function HistoryPanel({
  generations,
  activeId,
  onSelect,
  onDelete,
  onClear,
}: {
  generations: MemeGeneration[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-[18px] border border-shell-border bg-shell-panel shadow-shell">
      <header className="flex items-center justify-between gap-2 border-b border-shell-border px-3 py-2">
        <div className="flex items-center gap-1.5">
          <History className="h-3.5 w-3.5 text-shell-accent" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">History</span>
          <span className="font-mono text-[10px] tabular-nums text-shell-muted">
            {generations.length}
          </span>
        </div>
        {generations.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="text-shell-muted/60 hover:text-shell-error"
            title="Wipe local history"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </header>
      <ul className="flex-1 space-y-1 overflow-y-auto px-2 py-2">
        {generations.length === 0 ? (
          <li className="py-6 text-center font-mono text-[10px] uppercase tracking-wider text-shell-muted">
            no runs yet
          </li>
        ) : (
          generations.map((g) => {
            const active = g.id === activeId;
            const topAngle = g.candidates[0]?.direction.slice(0, 40) || '(empty)';
            return (
              <li key={g.id}>
                <button
                  type="button"
                  onClick={() => onSelect(g.id)}
                  className={`group relative w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                    active
                      ? 'border-shell-accent/40 bg-shell-accent-soft'
                      : 'border-transparent hover:border-shell-border hover:bg-shell-panel-strong/40'
                  }`}
                >
                  <div className="mb-0.5 flex items-center justify-between font-mono text-[10px] uppercase tabular-nums text-shell-muted">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-2.5 w-2.5" />
                      {new Date(g.generatedAt).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false,
                      })}
                    </span>
                    <span>{g.candidates.length}x</span>
                  </div>
                  <div className="truncate text-[11px] text-shell-text">{g.brief.topic || '(untitled)'}</div>
                  <div className="truncate font-mono text-[10px] text-shell-muted">▸ {topAngle}</div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(g.id);
                    }}
                    className="absolute right-1 top-1 rounded p-1 text-shell-muted/50 opacity-0 transition-opacity group-hover:opacity-100 hover:text-shell-error"
                    aria-label="delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}

// ---------- Keeper rail ----------

function KeeperRail({
  rankings,
  generations,
}: {
  rankings: Record<string, import('./types').MemeRanking>;
  generations: MemeGeneration[];
}) {
  const pinned = useMemo(() => {
    const out: Array<{
      id: string;
      text: string;
      direction: string;
      score: number;
      generationId: string;
      time: string;
    }> = [];
    for (const g of generations) {
      for (const c of g.candidates) {
        const r = rankings[c.id];
        if (r?.pinned) {
          out.push({
            id: c.id,
            text: c.text,
            direction: c.direction,
            score: r.score,
            generationId: g.id,
            time: g.generatedAt,
          });
        }
      }
    }
    return out.sort((a, b) => b.score - a.score).slice(0, 12);
  }, [rankings, generations]);

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-shell-border bg-shell-panel shadow-shell">
      <header className="flex items-center justify-between gap-2 border-b border-shell-border px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Pin className="h-3.5 w-3.5 text-shell-accent" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Keepers</span>
        </div>
        <span className="font-mono text-[10px] tabular-nums text-shell-muted">{pinned.length}</span>
      </header>
      <ul className="flex-1 space-y-1.5 overflow-y-auto px-3 py-3">
        {pinned.length === 0 ? (
          <li className="py-4 text-center font-mono text-[10px] uppercase tracking-wider text-shell-muted">
            pin candidates to save them here
          </li>
        ) : (
          pinned.map((p) => (
            <li
              key={p.id}
              className="rounded-lg border border-shell-border bg-shell-panel-strong/40 px-2.5 py-2"
            >
              <div className="mb-0.5 flex items-center justify-between font-mono text-[9px] uppercase tabular-nums text-shell-muted">
                <span className="truncate">{p.direction}</span>
                <span className={p.score > 0 ? 'text-shell-accent' : 'text-shell-muted'}>
                  {p.score > 0 ? `+${p.score}` : p.score}
                </span>
              </div>
              <div className="line-clamp-2 font-display text-[14px] leading-snug text-shell-text">{p.text}</div>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
