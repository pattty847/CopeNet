import type { StoreApi } from 'zustand';

// Per-composer message drafts, keyed by session key (or the draft transcript
// key before first send). Lives in the store — not component state — so the
// right panel's tool palette can inject text into whichever composer is active.
export interface ComposerSlice {
  composerDrafts: Record<string, string>;
  setComposerDraft: (composerKey: string, value: string) => void;
  appendComposerDraft: (composerKey: string, text: string) => void;
}

export function createComposerSlice<T extends ComposerSlice>(
  set: StoreApi<T>['setState'],
): ComposerSlice {
  return {
    composerDrafts: {},
    setComposerDraft: (composerKey, value) =>
      set((state) => ({
        composerDrafts: { ...state.composerDrafts, [composerKey]: value },
      } as Partial<T>)),
    appendComposerDraft: (composerKey, text) =>
      set((state) => {
        const current = state.composerDrafts[composerKey] || '';
        const joined = current && !current.endsWith(' ') && !current.endsWith('\n')
          ? `${current} ${text}`
          : `${current}${text}`;
        return { composerDrafts: { ...state.composerDrafts, [composerKey]: joined } } as Partial<T>;
      }),
  };
}
