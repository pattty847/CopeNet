import { useEffect, useRef, useState } from 'react';
import { Image as ImageIcon, Sparkles, X, Zap, FileText, Hash } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { wsClient } from '../../lib/wsClient';
import { Spinner } from '../../components/Spinner';
import type { MemeBrief } from './types';
import { IDEATION_PRESETS, TONE_PRESETS } from './types';

interface MemeLabComposerProps {
  brief: MemeBrief;
  patchBrief: (updates: Partial<MemeBrief>) => void;
  onGenerate: () => void;
  onCancel: () => void;
  isGenerating: boolean;
  error: string | null;
}

export function MemeLabComposer({
  brief,
  patchBrief,
  onGenerate,
  onCancel,
  isGenerating,
  error,
}: MemeLabComposerProps) {
  const providers = useAppStore((s) => s.providers);
  const modelsByProvider = useAppStore((s) => s.modelsByProvider);
  const loadedModelProviders = useAppStore((s) => s.loadedModelProviders);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const provider = brief.provider || providers.find((p) => p.available)?.id || 'lm-studio';
  const canGenerate =
    Boolean(brief.topic.trim() || brief.trendSummary.trim() || brief.imageSpringboard.trim()) &&
    brief.count >= 1 &&
    brief.count <= 8;

  useEffect(() => {
    if (provider && !loadedModelProviders[provider]) {
      void wsClient.loadModels(provider);
    }
  }, [provider, loadedModelProviders]);

  const availableModels = provider ? modelsByProvider[provider] || [] : [];

  const toggleTone = (id: string) => {
    const set = new Set(brief.toneHints);
    if (set.has(id)) set.delete(id); else set.add(id);
    patchBrief({ toneHints: Array.from(set) });
  };

  const setCount = (n: number) => {
    const clamped = Math.max(1, Math.min(8, n));
    patchBrief({ count: clamped });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canGenerate) {
      textareaRef.current?.focus();
      return;
    }
    onGenerate();
  };

  // keyboard: ⌘/Ctrl + Enter to generate
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !isGenerating && canGenerate) {
        e.preventDefault();
        onGenerate();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onGenerate, isGenerating, canGenerate]);

  return (
    <form
      onSubmit={handleSubmit}
      className="relative flex h-full flex-col overflow-hidden rounded-[22px] border border-shell-border bg-shell-panel shadow-shell"
    >
      {/* Title rail */}
      <header className="flex items-center justify-between gap-2 border-b border-shell-border px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Brief</div>
            <div className="font-mono text-[10px] tabular-nums text-shell-muted">
              {brief.count} ideas · {brief.toneHints.length || 0} tones · {brief.preset || 'no preset'}
            </div>
          </div>
        </div>
        <span className="hidden font-mono text-[10px] uppercase tracking-wider text-shell-muted md:inline">
          ⌘ enter to fire
        </span>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {/* Topic */}
        <div>
          <label className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <span className="inline-flex items-center gap-1.5">
              <Hash className="h-3 w-3" />
              topic
            </span>
            <span className="font-mono tabular-nums">{brief.topic.length}</span>
          </label>
          <textarea
            ref={textareaRef}
            value={brief.topic}
            onChange={(e) => patchBrief({ topic: e.target.value })}
            rows={3}
            placeholder="what are we poking at? e.g. 'the rise of cope-fluencers who pretend to meditate'"
            className="w-full resize-none rounded-lg border border-shell-border bg-shell-panel-strong/60 px-3 py-2.5 text-[13px] leading-relaxed text-shell-text placeholder:text-shell-muted/60 focus:border-shell-accent/50 focus:outline-none"
          />
        </div>

        {/* Trend summary */}
        <div>
          <label className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <span className="inline-flex items-center gap-1.5">
              <FileText className="h-3 w-3" />
              trend / source material
            </span>
          </label>
          <textarea
            value={brief.trendSummary}
            onChange={(e) => patchBrief({ trendSummary: e.target.value })}
            rows={3}
            placeholder="paste a summary of the trend, quote block, or link context (optional but grounds results)"
            className="w-full resize-none rounded-lg border border-shell-border bg-shell-panel-strong/60 px-3 py-2.5 text-[12px] leading-relaxed text-shell-text placeholder:text-shell-muted/60 focus:border-shell-accent/50 focus:outline-none"
          />
        </div>

        {/* Image springboard */}
        <div>
          <label className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <span className="inline-flex items-center gap-1.5">
              <ImageIcon className="h-3 w-3" />
              image springboard
            </span>
            <span className="font-mono text-[9px] tabular-nums text-shell-muted/70">text-only for now</span>
          </label>
          <div className="flex items-start gap-2">
            <div
              className="flex h-[60px] w-[72px] shrink-0 items-center justify-center rounded-lg border border-dashed border-shell-border text-shell-muted/60"
              title="Image upload coming — describe the reference image in words for now."
            >
              <ImageIcon className="h-4 w-4" />
            </div>
            <input
              type="text"
              value={brief.imageSpringboard}
              onChange={(e) => patchBrief({ imageSpringboard: e.target.value })}
              placeholder="describe the reference image: 'closeup of a guy in sunglasses at 2am kitchen sink'"
              className="flex-1 rounded-lg border border-shell-border bg-shell-panel-strong/60 px-3 py-2 text-[12px] leading-relaxed text-shell-text placeholder:text-shell-muted/60 focus:border-shell-accent/50 focus:outline-none"
            />
          </div>
        </div>

        {/* Preset row */}
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
            preset
          </div>
          <div className="flex flex-wrap gap-1.5">
            {IDEATION_PRESETS.map((p) => {
              const active = brief.preset === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => patchBrief({ preset: active ? null : p.id })}
                  title={p.description}
                  className={`rounded-lg border px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider transition-colors ${
                    active
                      ? 'border-shell-accent/50 bg-shell-accent-soft text-shell-accent'
                      : 'border-shell-border bg-shell-panel-strong/50 text-shell-muted hover:border-shell-accent/40 hover:text-shell-accent'
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Tones */}
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
            tone cocktail
          </div>
          <div className="flex flex-wrap gap-1.5">
            {TONE_PRESETS.map((t) => {
              const active = brief.toneHints.includes(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleTone(t.id)}
                  title={t.hint}
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] transition-colors ${
                    active
                      ? 'border-shell-accent/50 bg-shell-accent/15 text-shell-text'
                      : 'border-shell-border bg-shell-panel-strong/40 text-shell-muted hover:border-shell-accent/30 hover:text-shell-text'
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Count + model */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
              candidates
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-shell-border bg-shell-panel-strong/60 px-2 py-1.5">
              <button
                type="button"
                onClick={() => setCount(brief.count - 1)}
                className="font-mono text-shell-muted hover:text-shell-accent"
                aria-label="decrease count"
              >
                −
              </button>
              <input
                type="number"
                min={1}
                max={8}
                value={brief.count}
                onChange={(e) => setCount(Number(e.target.value || 0))}
                className="flex-1 bg-transparent text-center font-mono text-[14px] tabular-nums text-shell-text focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setCount(brief.count + 1)}
                className="font-mono text-shell-muted hover:text-shell-accent"
                aria-label="increase count"
              >
                +
              </button>
            </div>
            <div className="mt-1 flex gap-1">
              {[2, 4, 6, 8].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setCount(n)}
                  className={`flex-1 rounded-md border px-1 py-0.5 font-mono text-[10px] tabular-nums transition-colors ${
                    brief.count === n
                      ? 'border-shell-accent/40 bg-shell-accent-soft text-shell-accent'
                      : 'border-shell-border text-shell-muted hover:border-shell-accent/30 hover:text-shell-accent'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
              model
            </div>
            <select
              value={provider}
              onChange={(e) => patchBrief({ provider: e.target.value || null, model: null })}
              className="mb-1 w-full rounded-lg border border-shell-border bg-shell-panel-strong/60 px-2.5 py-1.5 text-[12px] text-shell-text focus:border-shell-accent/50 focus:outline-none"
            >
              <option value="">auto</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.displayName}
                  {p.available ? '' : ' · offline'}
                </option>
              ))}
            </select>
            <select
              value={brief.model || ''}
              onChange={(e) => patchBrief({ model: e.target.value || null })}
              className="w-full rounded-lg border border-shell-border bg-shell-panel-strong/60 px-2.5 py-1.5 text-[12px] text-shell-text focus:border-shell-accent/50 focus:outline-none"
            >
              <option value="">inherit from preset</option>
              {availableModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.displayName}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-shell-error/30 bg-shell-error/10 px-3 py-2 font-mono text-[11px] text-shell-error">
            {error}
          </div>
        )}
      </div>

      {/* Fire button */}
      <footer className="border-t border-shell-border bg-shell-panel-strong/40 px-3 py-3">
        {isGenerating ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="relative flex flex-1 items-center justify-center gap-2 overflow-hidden rounded-lg border border-shell-accent/40 bg-shell-accent-soft px-4 py-2.5 font-mono text-[12px] uppercase tracking-[0.22em] text-shell-accent"
            >
              <Spinner variant="flip" className="relative z-10 text-shell-accent" />
              <span className="relative z-10">Igniting · local model cooking</span>
              <span className="absolute inset-0 animate-[run-progress_1.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-shell-accent/20 to-transparent" />
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="focus-ring inline-flex items-center gap-1 rounded-lg border border-shell-border px-3 py-2.5 font-mono text-[11px] uppercase tracking-wider text-shell-muted transition-colors hover:border-shell-error/40 hover:text-shell-error"
            >
              <X className="h-3.5 w-3.5" />
              abort
            </button>
          </div>
        ) : (
          <button
            type="submit"
            disabled={!canGenerate}
            className="focus-ring glow-accent flex w-full items-center justify-center gap-2 rounded-lg border border-shell-accent/40 bg-shell-accent text-shell-ink px-4 py-2.5 font-mono text-[12px] font-semibold uppercase tracking-[0.22em] transition-all disabled:cursor-not-allowed disabled:border-shell-border disabled:bg-shell-panel-strong disabled:text-shell-muted"
          >
            <Zap className="h-3.5 w-3.5" />
            generate {brief.count} ideas
          </button>
        )}
      </footer>
    </form>
  );
}
