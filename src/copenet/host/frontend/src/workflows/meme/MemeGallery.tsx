import { useMemo, useState } from 'react';
import { SortAsc, Pin, Filter } from 'lucide-react';
import type { MemeCandidate, MemeGeneration, MemeRanking } from './types';
import { MemeCandidateCard } from './MemeCandidateCard';

interface MemeGalleryProps {
  generation: MemeGeneration;
  rankings: Record<string, MemeRanking>;
  onBumpScore: (candidateId: string, delta: number) => void;
  onTogglePin: (candidateId: string) => void;
  onSendToArena: (candidateId: string) => void;
}

type SortMode = 'order' | 'score' | 'pinned';

export function MemeGallery({
  generation,
  rankings,
  onBumpScore,
  onTogglePin,
  onSendToArena,
}: MemeGalleryProps) {
  const [sort, setSort] = useState<SortMode>('order');
  const [onlyVisual, setOnlyVisual] = useState(false);
  const [onlyPinned, setOnlyPinned] = useState(false);

  const candidates = useMemo<MemeCandidate[]>(() => {
    let list = [...generation.candidates];
    if (onlyVisual) list = list.filter((c) => c.needsVisualContext);
    if (onlyPinned) list = list.filter((c) => rankings[c.id]?.pinned);
    if (sort === 'score') {
      list = list.sort((a, b) => (rankings[b.id]?.score ?? 0) - (rankings[a.id]?.score ?? 0));
    } else if (sort === 'pinned') {
      list = list.sort((a, b) => {
        const ap = rankings[a.id]?.pinned ? 1 : 0;
        const bp = rankings[b.id]?.pinned ? 1 : 0;
        if (bp - ap !== 0) return bp - ap;
        return (rankings[b.id]?.score ?? 0) - (rankings[a.id]?.score ?? 0);
      });
    }
    return list;
  }, [generation, rankings, sort, onlyVisual, onlyPinned]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-shell-border bg-shell-panel px-4 py-2.5 shadow-shell">
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-shell-muted">
          <Filter className="h-3 w-3" />
          <span>{candidates.length}</span>
          <span className="text-shell-muted/60">/ {generation.candidates.length}</span>
          <span className="text-shell-muted/60">showing</span>
        </div>
        <div className="flex items-center gap-1">
          <ToolbarChip active={onlyVisual} onClick={() => setOnlyVisual((v) => !v)}>
            needs visual
          </ToolbarChip>
          <ToolbarChip active={onlyPinned} onClick={() => setOnlyPinned((v) => !v)} icon={Pin}>
            pinned only
          </ToolbarChip>
          <div className="mx-1 h-4 w-px bg-shell-border" />
          <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted">
            <SortAsc className="h-3 w-3" />
            sort
          </span>
          {(['order', 'score', 'pinned'] as SortMode[]).map((mode) => (
            <ToolbarChip key={mode} active={sort === mode} onClick={() => setSort(mode)}>
              {mode}
            </ToolbarChip>
          ))}
        </div>
      </div>

      {candidates.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-[18px] border border-dashed border-shell-border bg-shell-panel-strong/30 px-6 py-20 text-center">
          <div>
            <div className="mb-2 font-display text-xl text-shell-text">No survivors in view</div>
            <div className="font-mono text-[11px] text-shell-muted">
              drop a filter to see more of the batch
            </div>
          </div>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-y-auto pr-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {candidates.map((c) => (
            <MemeCandidateCard
              key={c.id}
              candidate={c}
              ranking={rankings[c.id] ?? null}
              index={generation.candidates.indexOf(c)}
              variant="gallery"
              onBumpScore={onBumpScore}
              onTogglePin={onTogglePin}
              onSendToArena={onSendToArena}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolbarChip({
  active,
  onClick,
  children,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  icon?: typeof Pin;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
        active
          ? 'border-shell-accent/40 bg-shell-accent-soft text-shell-accent'
          : 'border-shell-border bg-shell-panel-strong/40 text-shell-muted hover:border-shell-accent/30 hover:text-shell-accent'
      }`}
    >
      {Icon && <Icon className="h-3 w-3" />}
      {children}
    </button>
  );
}
