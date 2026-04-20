import { AlertTriangle, Image as ImageIcon, Minus, Plus, Pin, Swords, Trophy, X } from 'lucide-react';
import type { MemeCandidate, MemeRanking } from './types';

interface MemeCandidateCardProps {
  candidate: MemeCandidate;
  ranking: MemeRanking | null;
  index: number;
  variant?: 'stream' | 'gallery' | 'arena';
  onBumpScore?: (candidateId: string, delta: number) => void;
  onTogglePin?: (candidateId: string) => void;
  onSendToArena?: (candidateId: string) => void;
  onDismiss?: (candidateId: string) => void;
}

function scoreTone(score: number): string {
  if (score >= 2) return 'text-shell-accent';
  if (score >= 1) return 'text-shell-accent/80';
  if (score === 0) return 'text-shell-muted';
  if (score >= -1) return 'text-shell-error/70';
  return 'text-shell-error';
}

function scoreLabel(score: number): string {
  if (score >= 3) return 'FIRE';
  if (score === 2) return 'keeper';
  if (score === 1) return 'solid';
  if (score === 0) return '—';
  if (score === -1) return 'weak';
  if (score === -2) return 'cut';
  return 'NUKE';
}

function formatChip(format: string): string {
  return format.replace(/[_-]/g, ' ');
}

export function MemeCandidateCard({
  candidate,
  ranking,
  index,
  variant = 'stream',
  onBumpScore,
  onTogglePin,
  onSendToArena,
  onDismiss,
}: MemeCandidateCardProps) {
  const score = ranking?.score ?? 0;
  const pinned = ranking?.pinned ?? false;
  const verdict = ranking?.verdict ?? null;

  const sizing =
    variant === 'arena'
      ? 'min-h-[420px]'
      : variant === 'gallery'
        ? 'min-h-[280px]'
        : 'min-h-[200px]';

  return (
    <article
      className={`group relative overflow-hidden rounded-[18px] border border-shell-border bg-shell-panel shadow-shell transition-all duration-200 ${sizing} ${
        pinned ? 'ring-1 ring-shell-accent/40' : ''
      } ${verdict === 'winner' ? 'ring-2 ring-shell-success/50' : ''} ${
        verdict === 'loser' ? 'opacity-70' : ''
      }`}
    >
      {/* Accent corner ribbon keyed to score */}
      <div
        className={`pointer-events-none absolute -right-12 -top-8 h-24 w-32 rotate-[32deg] blur-2xl transition-opacity duration-300 ${
          score > 0
            ? 'bg-shell-accent/25 opacity-100'
            : score < 0
              ? 'bg-shell-error/20 opacity-70'
              : 'bg-shell-border-strong/30 opacity-50'
        }`}
      />

      {/* Header row */}
      <header className="relative flex items-start justify-between gap-3 border-b border-shell-border/60 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
            <span className="font-mono text-shell-muted tabular-nums">#{String(index + 1).padStart(2, '0')}</span>
            <span className="truncate">{candidate.direction}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase tabular-nums">
          <span className="rounded-md border border-shell-border bg-shell-panel-strong px-1.5 py-0.5 text-shell-muted">
            {formatChip(candidate.format)}
          </span>
          {candidate.needsVisualContext && (
            <span className="inline-flex items-center gap-1 rounded-md border border-shell-accent/30 bg-shell-accent-soft px-1.5 py-0.5 text-shell-accent">
              <ImageIcon className="h-3 w-3" />
              visual
            </span>
          )}
          {verdict === 'winner' && (
            <span className="inline-flex items-center gap-1 rounded-md bg-shell-success/15 px-1.5 py-0.5 text-shell-success">
              <Trophy className="h-3 w-3" />
              won
            </span>
          )}
        </div>
      </header>

      {/* Hero text */}
      <div className="relative px-5 py-5">
        <blockquote
          className={`font-display leading-[1.08] tracking-tight text-shell-text ${
            variant === 'arena'
              ? 'text-[2.3rem]'
              : variant === 'gallery'
                ? 'text-[1.5rem]'
                : 'text-[1.75rem]'
          }`}
        >
          {candidate.text || <span className="italic text-shell-muted">(no text returned)</span>}
        </blockquote>

        {candidate.optionalCaption && (
          <div className="mt-4 border-t border-dashed border-shell-border/80 pt-3">
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
              caption
            </div>
            <p className="font-mono text-[12px] leading-relaxed text-shell-text/90">
              {candidate.optionalCaption}
            </p>
          </div>
        )}

        {candidate.notes && (
          <div className="mt-3 text-[11px] leading-relaxed text-shell-muted">
            <span className="text-shell-accent/80">▸ </span>
            {candidate.notes}
          </div>
        )}

        {candidate.warnings.length > 0 && (
          <ul className="mt-3 space-y-1">
            {candidate.warnings.map((w, i) => (
              <li key={i} className="inline-flex items-start gap-1.5 font-mono text-[11px] text-shell-error">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Visual context placeholder — design affordance for a future image */}
        {candidate.needsVisualContext && (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-dashed border-shell-accent/30 bg-shell-accent/5 px-3 py-2.5">
            <div className="flex h-10 w-14 shrink-0 items-center justify-center rounded-md bg-shell-panel-strong text-shell-accent">
              <ImageIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 text-[11px] leading-relaxed">
              <div className="font-mono uppercase tracking-wider text-shell-accent">needs image</div>
              <div className="text-shell-muted">
                Wire a source photo or generated asset when the image pipeline is live.
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer: score + actions */}
      <footer className="relative flex items-center justify-between gap-3 border-t border-shell-border/60 bg-shell-panel-strong/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onBumpScore?.(candidate.id, -1)}
            className="focus-ring flex h-7 w-7 items-center justify-center rounded-md border border-shell-border text-shell-muted transition-colors hover:border-shell-error/40 hover:text-shell-error"
            title="Dock (-1)"
            aria-label="Decrease score"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <div
            className={`flex min-w-[70px] flex-col items-center font-mono text-[10px] uppercase tabular-nums ${scoreTone(score)}`}
          >
            <span className="text-[16px] font-semibold leading-none">
              {score > 0 ? `+${score}` : score}
            </span>
            <span className="tracking-[0.2em]">{scoreLabel(score)}</span>
          </div>
          <button
            type="button"
            onClick={() => onBumpScore?.(candidate.id, 1)}
            className="focus-ring flex h-7 w-7 items-center justify-center rounded-md border border-shell-border text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
            title="Boost (+1)"
            aria-label="Increase score"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onTogglePin?.(candidate.id)}
            className={`focus-ring inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
              pinned
                ? 'border-shell-accent/40 bg-shell-accent-soft text-shell-accent'
                : 'border-shell-border text-shell-muted hover:border-shell-accent/40 hover:text-shell-accent'
            }`}
            title={pinned ? 'Unpin from keeper board' : 'Pin to keeper board'}
          >
            <Pin className="h-3 w-3" />
            {pinned ? 'pinned' : 'pin'}
          </button>
          {onSendToArena && (
            <button
              type="button"
              onClick={() => onSendToArena(candidate.id)}
              className="focus-ring inline-flex items-center gap-1 rounded-md border border-shell-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
              title="Send to arena"
            >
              <Swords className="h-3 w-3" />
              arena
            </button>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={() => onDismiss(candidate.id)}
              className="focus-ring inline-flex h-6 w-6 items-center justify-center rounded-md text-shell-muted/60 transition-colors hover:bg-shell-error/10 hover:text-shell-error"
              title="Dismiss"
              aria-label="Dismiss"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </footer>
    </article>
  );
}
