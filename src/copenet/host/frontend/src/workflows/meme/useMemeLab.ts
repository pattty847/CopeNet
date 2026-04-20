// Local state for the Meme Lab workflow.
// Generations + rankings persist to localStorage so the "feedback loop" feels real
// without needing backend storage. Easy to lift later: swap the localStorage writer
// for an RPC / REST call.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ideateMemes, MemeIdeationError } from './memeClient';
import type {
  ArenaState,
  MemeBrief,
  MemeGeneration,
  MemeRanking,
  MemeVerdict,
  MemeViewMode,
} from './types';

const STORAGE_KEY = 'copenet.memeLab.v1';

interface PersistShape {
  generations: MemeGeneration[];
  rankings: Record<string, MemeRanking>;
  activeGenerationId: string | null;
}

function loadState(): PersistShape {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { generations: [], rankings: {}, activeGenerationId: null };
    const parsed = JSON.parse(raw) as Partial<PersistShape>;
    return {
      generations: Array.isArray(parsed.generations) ? parsed.generations.slice(0, 24) : [],
      rankings: parsed.rankings && typeof parsed.rankings === 'object' ? parsed.rankings : {},
      activeGenerationId: parsed.activeGenerationId ?? null,
    };
  } catch {
    return { generations: [], rankings: {}, activeGenerationId: null };
  }
}

function saveState(state: PersistShape) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // noop: localStorage may be unavailable in restricted contexts
  }
}

export const DEFAULT_BRIEF: MemeBrief = {
  topic: '',
  trendSummary: '',
  imageSpringboard: '',
  toneHints: ['copecore', 'dry'],
  count: 8,
  provider: 'lm-studio',
  model: null,
  preset: 'shotgun',
};

export function useMemeLab() {
  const bootstrap = useRef<PersistShape | null>(null);
  if (bootstrap.current === null) {
    bootstrap.current = loadState();
  }

  const [generations, setGenerations] = useState<MemeGeneration[]>(bootstrap.current.generations);
  const [rankings, setRankings] = useState<Record<string, MemeRanking>>(bootstrap.current.rankings);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(
    bootstrap.current.activeGenerationId,
  );
  const [brief, setBrief] = useState<MemeBrief>(DEFAULT_BRIEF);
  const [viewMode, setViewMode] = useState<MemeViewMode>('stream');
  const [arena, setArena] = useState<ArenaState>({ leftId: null, rightId: null, lastVerdict: null });

  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Persist whenever meaningful state changes.
  useEffect(() => {
    saveState({ generations, rankings, activeGenerationId });
  }, [generations, rankings, activeGenerationId]);

  const activeGeneration = useMemo(
    () => generations.find((g) => g.id === activeGenerationId) ?? generations[0] ?? null,
    [generations, activeGenerationId],
  );

  const patchBrief = useCallback((updates: Partial<MemeBrief>) => {
    setBrief((prev) => ({ ...prev, ...updates }));
  }, []);

  const generate = useCallback(async () => {
    if (isGenerating) return;
    setGenerationError(null);
    setIsGenerating(true);
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;
    try {
      const gen = await ideateMemes(brief, { signal: ctrl.signal });
      setGenerations((prev) => [gen, ...prev].slice(0, 24));
      setActiveGenerationId(gen.id);
    } catch (err) {
      if ((err as { name?: string }).name === 'AbortError') return;
      if (err instanceof MemeIdeationError) {
        setGenerationError(`${err.message} (status ${err.status})`);
      } else {
        setGenerationError(String((err as Error).message || err));
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setIsGenerating(false);
    }
  }, [brief, isGenerating]);

  const cancelGenerate = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const setActive = useCallback((id: string | null) => {
    setActiveGenerationId(id);
    setArena({ leftId: null, rightId: null, lastVerdict: null });
  }, []);

  const deleteGeneration = useCallback((id: string) => {
    setGenerations((prev) => prev.filter((g) => g.id !== id));
    setActiveGenerationId((prev) => (prev === id ? null : prev));
  }, []);

  // -------- Ranking --------

  const upsertRanking = useCallback(
    (candidateId: string, updates: Partial<Omit<MemeRanking, 'candidateId' | 'updatedAt'>>) => {
      setRankings((prev) => {
        const current: MemeRanking = prev[candidateId] ?? {
          candidateId,
          score: 0,
          pinned: false,
          verdict: null,
          note: null,
          updatedAt: new Date().toISOString(),
        };
        const next: MemeRanking = {
          ...current,
          ...updates,
          candidateId,
          updatedAt: new Date().toISOString(),
        };
        return { ...prev, [candidateId]: next };
      });
    },
    [],
  );

  const bumpScore = useCallback(
    (candidateId: string, delta: number) => {
      const current = rankings[candidateId];
      const next = Math.max(-3, Math.min(3, (current?.score ?? 0) + delta));
      upsertRanking(candidateId, { score: next });
    },
    [rankings, upsertRanking],
  );

  const togglePin = useCallback(
    (candidateId: string) => {
      const current = rankings[candidateId];
      upsertRanking(candidateId, { pinned: !(current?.pinned ?? false) });
    },
    [rankings, upsertRanking],
  );

  const setVerdict = useCallback(
    (candidateId: string, verdict: MemeVerdict) => {
      upsertRanking(candidateId, { verdict });
    },
    [upsertRanking],
  );

  // -------- Arena helpers --------

  const ensureArenaPair = useCallback(() => {
    if (!activeGeneration) return;
    const ids = activeGeneration.candidates.map((c) => c.id);
    if (ids.length < 2) return;
    setArena((prev) => {
      const left = prev.leftId && ids.includes(prev.leftId) ? prev.leftId : ids[0];
      const remaining = ids.filter((id) => id !== left);
      const right = prev.rightId && remaining.includes(prev.rightId) ? prev.rightId : remaining[0] || null;
      return { ...prev, leftId: left, rightId: right };
    });
  }, [activeGeneration]);

  const rotateArenaRight = useCallback(
    (winnerSide: 'left' | 'right' | 'tie') => {
      if (!activeGeneration) return;
      const ids = activeGeneration.candidates.map((c) => c.id);
      if (ids.length < 2) return;
      setArena((prev) => {
        const { leftId, rightId } = prev;
        if (!leftId || !rightId) return prev;
        const winnerId = winnerSide === 'left' ? leftId : winnerSide === 'right' ? rightId : null;
        if (winnerSide === 'left') {
          upsertRanking(leftId, { verdict: 'winner' });
          upsertRanking(rightId, { verdict: 'loser' });
        } else if (winnerSide === 'right') {
          upsertRanking(rightId, { verdict: 'winner' });
          upsertRanking(leftId, { verdict: 'loser' });
        } else {
          upsertRanking(leftId, { verdict: 'tie' });
          upsertRanking(rightId, { verdict: 'tie' });
        }
        const nextRightIndex = (ids.indexOf(rightId) + 1) % ids.length;
        const pickedRight = ids[nextRightIndex];
        const nextLeft = winnerId ?? leftId;
        const pickedLeft = pickedRight === nextLeft ? ids[(nextRightIndex + 1) % ids.length] : nextLeft;
        return {
          leftId: pickedLeft,
          rightId: pickedRight === pickedLeft ? ids[(nextRightIndex + 2) % ids.length] : pickedRight,
          lastVerdict: {
            leftId,
            rightId,
            winner: winnerSide === 'tie' ? 'tie' : (winnerId as string),
          },
        };
      });
    },
    [activeGeneration, upsertRanking],
  );

  const clearAll = useCallback(() => {
    setGenerations([]);
    setRankings({});
    setActiveGenerationId(null);
    setArena({ leftId: null, rightId: null, lastVerdict: null });
  }, []);

  return {
    // brief / action
    brief,
    patchBrief,
    generate,
    cancelGenerate,
    isGenerating,
    generationError,
    // history
    generations,
    activeGeneration,
    setActive,
    deleteGeneration,
    clearAll,
    // view mode
    viewMode,
    setViewMode,
    // rankings
    rankings,
    bumpScore,
    togglePin,
    setVerdict,
    upsertRanking,
    // arena
    arena,
    ensureArenaPair,
    rotateArenaRight,
    setArena,
  };
}
