import { useEffect, useMemo } from 'react';
import { ArrowLeft, ArrowRight, Equal, Trophy } from 'lucide-react';
import type { ArenaState, MemeCandidate, MemeGeneration, MemeRanking } from './types';
import { MemeCandidateCard } from './MemeCandidateCard';

interface MemeArenaProps {
  generation: MemeGeneration;
  rankings: Record<string, MemeRanking>;
  arena: ArenaState;
  ensurePair: () => void;
  rotate: (winner: 'left' | 'right' | 'tie') => void;
  onBumpScore: (candidateId: string, delta: number) => void;
  onTogglePin: (candidateId: string) => void;
  onSelectLeft: (candidateId: string) => void;
  onSelectRight: (candidateId: string) => void;
}

export function MemeArena({
  generation,
  rankings,
  arena,
  ensurePair,
  rotate,
  onBumpScore,
  onTogglePin,
  onSelectLeft,
  onSelectRight,
}: MemeArenaProps) {
  useEffect(() => {
    ensurePair();
  }, [ensurePair]);

  const byId = useMemo(() => {
    const map = new Map<string, MemeCandidate>();
    for (const c of generation.candidates) map.set(c.id, c);
    return map;
  }, [generation]);

  const left = arena.leftId ? byId.get(arena.leftId) : null;
  const right = arena.rightId ? byId.get(arena.rightId) : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        rotate('left');
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        rotate('right');
      } else if (e.key === '=' || e.key === '0') {
        e.preventDefault();
        rotate('tie');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [rotate]);

  const totalPairs = useMemo(() => {
    const n = generation.candidates.length;
    return n > 1 ? (n * (n - 1)) / 2 : 0;
  }, [generation]);

  const verdicts = useMemo(() => Object.values(rankings).filter((r) => r.verdict), [rankings]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* Arena head — score board */}
      <div className="flex items-center justify-between gap-4 rounded-[18px] border border-shell-border bg-shell-panel px-5 py-3 shadow-shell">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
            <Trophy className="h-4 w-4" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Arena</div>
            <div className="font-mono text-[11px] tabular-nums text-shell-muted">
              {verdicts.length} decisions · {totalPairs} possible pairings
            </div>
          </div>
        </div>
        <div className="hidden items-center gap-3 font-mono text-[11px] uppercase tracking-wider text-shell-muted md:flex">
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px]">←</kbd>
            left wins
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px]">=</kbd>
            tie
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-[10px]">→</kbd>
            right wins
          </span>
        </div>
      </div>

      {/* Combat row */}
      <div className="relative grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-stretch gap-3">
        <div className="flex min-w-0 flex-col">
          <PairSelect
            side="left"
            candidates={generation.candidates}
            selectedId={arena.leftId}
            disabledId={arena.rightId}
            onSelect={onSelectLeft}
          />
          {left ? (
            <MemeCandidateCard
              candidate={left}
              ranking={rankings[left.id] ?? null}
              index={generation.candidates.indexOf(left)}
              variant="arena"
              onBumpScore={onBumpScore}
              onTogglePin={onTogglePin}
            />
          ) : (
            <ArenaEmpty label="left slot empty" />
          )}
        </div>

        {/* Center pillar: VS */}
        <div className="relative flex flex-col items-center justify-center gap-3 px-1">
          <div className="font-display text-[3.5rem] leading-none tracking-tighter text-shell-accent">vs</div>
          <div className="h-full w-px bg-gradient-to-b from-transparent via-shell-border to-transparent" />
          {arena.lastVerdict && (
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full whitespace-nowrap pt-2 font-mono text-[10px] uppercase tracking-wider text-shell-muted">
              last · {arena.lastVerdict.winner === 'tie' ? 'tie' : 'winner logged'}
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-col">
          <PairSelect
            side="right"
            candidates={generation.candidates}
            selectedId={arena.rightId}
            disabledId={arena.leftId}
            onSelect={onSelectRight}
          />
          {right ? (
            <MemeCandidateCard
              candidate={right}
              ranking={rankings[right.id] ?? null}
              index={generation.candidates.indexOf(right)}
              variant="arena"
              onBumpScore={onBumpScore}
              onTogglePin={onTogglePin}
            />
          ) : (
            <ArenaEmpty label="right slot empty" />
          )}
        </div>
      </div>

      {/* Verdict bar */}
      <div className="grid grid-cols-3 gap-2">
        <VerdictButton
          tone="left"
          label="left wins"
          icon={ArrowLeft}
          onClick={() => rotate('left')}
          disabled={!left || !right}
        />
        <VerdictButton
          tone="tie"
          label="tie"
          icon={Equal}
          onClick={() => rotate('tie')}
          disabled={!left || !right}
        />
        <VerdictButton
          tone="right"
          label="right wins"
          icon={ArrowRight}
          onClick={() => rotate('right')}
          disabled={!left || !right}
        />
      </div>
    </div>
  );
}

function PairSelect({
  side,
  candidates,
  selectedId,
  disabledId,
  onSelect,
}: {
  side: 'left' | 'right';
  candidates: MemeCandidate[];
  selectedId: string | null;
  disabledId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted">
        {side === 'left' ? '◀ left slot' : 'right slot ▶'}
      </span>
      <select
        value={selectedId || ''}
        onChange={(e) => onSelect(e.target.value)}
        className="flex-1 rounded-md border border-shell-border bg-shell-panel-strong/60 px-2 py-1 font-mono text-[11px] text-shell-text focus:border-shell-accent/50 focus:outline-none"
      >
        <option value="" disabled>
          pick candidate
        </option>
        {candidates.map((c, i) => (
          <option key={c.id} value={c.id} disabled={c.id === disabledId}>
            #{String(i + 1).padStart(2, '0')} · {c.direction.slice(0, 48)}
          </option>
        ))}
      </select>
    </div>
  );
}

function ArenaEmpty({ label }: { label: string }) {
  return (
    <div className="flex min-h-[420px] flex-1 items-center justify-center rounded-[18px] border border-dashed border-shell-border bg-shell-panel-strong/30 font-mono text-[11px] uppercase tracking-wider text-shell-muted">
      {label}
    </div>
  );
}

function VerdictButton({
  tone,
  label,
  icon: Icon,
  onClick,
  disabled,
}: {
  tone: 'left' | 'tie' | 'right';
  label: string;
  icon: typeof ArrowLeft;
  onClick: () => void;
  disabled: boolean;
}) {
  const toneClass =
    tone === 'tie'
      ? 'border-shell-border text-shell-muted hover:border-shell-accent/40 hover:text-shell-text'
      : 'border-shell-accent/30 bg-shell-accent-soft text-shell-accent hover:bg-shell-accent/20';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`focus-ring flex items-center justify-center gap-2 rounded-[14px] border px-4 py-3 font-mono text-[12px] uppercase tracking-[0.22em] transition-all disabled:cursor-not-allowed disabled:opacity-40 ${toneClass}`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}
