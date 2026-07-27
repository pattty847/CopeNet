import type { StoreApi } from 'zustand';

// Per-composer text and structured tool intent, keyed by session key (or the
// draft transcript key before first send). This stays global because the
// inspector and the chat composer both edit the same next-message state.
export interface ComposerSlice {
  composerDrafts: Record<string, string>;
  composerRequestedToolIds: Record<string, string[]>;
  setComposerDraft: (composerKey: string, value: string) => void;
  addComposerRequestedTool: (composerKey: string, toolId: string) => void;
  removeComposerRequestedTool: (composerKey: string, toolId: string) => void;
  clearComposerRequestedTools: (composerKey: string) => void;
}

export function createComposerSlice<T extends ComposerSlice>(
  set: StoreApi<T>['setState'],
): ComposerSlice {
  return {
    composerDrafts: {},
    composerRequestedToolIds: {},
    setComposerDraft: (composerKey, value) =>
      set((state) => ({
        composerDrafts: { ...state.composerDrafts, [composerKey]: value },
      } as Partial<T>)),
    addComposerRequestedTool: (composerKey, toolId) =>
      set((state) => {
        const current = state.composerRequestedToolIds[composerKey] || [];
        if (current.includes(toolId)) return {} as Partial<T>;
        return {
          composerRequestedToolIds: {
            ...state.composerRequestedToolIds,
            [composerKey]: [...current, toolId],
          },
        } as Partial<T>;
      }),
    removeComposerRequestedTool: (composerKey, toolId) =>
      set((state) => ({
        composerRequestedToolIds: {
          ...state.composerRequestedToolIds,
          [composerKey]: (state.composerRequestedToolIds[composerKey] || []).filter((id) => id !== toolId),
        },
      } as Partial<T>)),
    clearComposerRequestedTools: (composerKey) =>
      set((state) => {
        const next = { ...state.composerRequestedToolIds };
        delete next[composerKey];
        return { composerRequestedToolIds: next } as Partial<T>;
      }),
  };
}
