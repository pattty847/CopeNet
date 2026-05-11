import { LoaderCircle, Sparkles, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { wsClient } from '../../lib/wsClient';
import { buildPersonaFlavorId, buildPersonaModelKey, resolvePersonaRuntime } from '../../lib/personaCommands';
import { useAppStore } from '../../store/useAppStore';
import { ChatMarkdown } from '../ChatMarkdown';

interface DraftState {
  displayName: string;
  identityMarkdown: string;
  soulMarkdown: string;
  notesMarkdown: string;
}

function EditorSection({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">{label}</div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-[150px] w-full rounded-[20px] border border-shell-border bg-shell-bg px-4 py-3 text-sm leading-6 text-shell-text outline-none transition focus:border-shell-border-strong"
      />
    </div>
  );
}

export function PersonaFlavorReviewModal() {
  const open = useAppStore((state) => state.personaFlavorReviewOpen);
  const draft = useAppStore((state) => state.personaFlavorDraft);
  const setDraft = useAppStore((state) => state.setPersonaFlavorDraft);
  const setOpen = useAppStore((state) => state.setPersonaFlavorReviewOpen);
  const personaSettings = useAppStore((state) => state.personaSettings);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const patchDraftSettings = useAppStore((state) => state.patchDraftSettings);
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setAppError = useAppStore((state) => state.setAppError);
  const [localDraft, setLocalDraft] = useState<DraftState | null>(draft);
  const [saving, setSaving] = useState(false);

  const activeSession = useMemo(
    () => sessions.find((session) => session.key === activeSessionKey) || null,
    [activeSessionKey, sessions],
  );
  const runtime = resolvePersonaRuntime(activeSession, draftSettings);

  useEffect(() => {
    setLocalDraft(draft);
  }, [draft]);

  if (!open || !localDraft) return null;

  const close = () => {
    if (saving) return;
    setOpen(false);
    setDraft(null);
  };

  const updateField = (field: keyof DraftState, value: string) => {
    setLocalDraft((current) => (current ? { ...current, [field]: value } : current));
  };

  const handleSave = async () => {
    if (!localDraft || !runtime.provider) return;
    setSaving(true);
    try {
      await wsClient.savePersonaFlavor({
        provider: runtime.provider,
        model: runtime.model || undefined,
        draft: { ...localDraft },
      });
      const nextFlavorId = buildPersonaFlavorId(runtime.provider, runtime.model);
      const currentSettings = personaSettings || {
        defaultPersonaId: runtime.personaId || 'default',
        defaultPrivacyTier: runtime.personaPrivacyTier,
        modelOverrides: {},
      };
      await wsClient.updatePersonaSettings({
        ...currentSettings,
        modelOverrides: {
          ...currentSettings.modelOverrides,
          [buildPersonaModelKey(runtime.provider, runtime.model)]: {
            personaId: runtime.personaId || currentSettings.defaultPersonaId || 'default',
            flavorId: nextFlavorId,
          },
        },
      });
      if (!activeSession) {
        patchDraftSettings({ personaFlavorId: nextFlavorId });
      }
      await wsClient.getPersonaSummary({
        provider: runtime.provider,
        model: runtime.model,
        privacyTier: runtime.personaPrivacyTier,
      });
      await wsClient.getPersonaContext({
        provider: runtime.provider,
        model: runtime.model,
        privacyTier: runtime.personaPrivacyTier,
      });
      close();
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to save persona flavor.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/45 p-3 sm:items-center sm:p-6" role="dialog" aria-modal="true">
      <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border border-shell-border bg-shell-canvas shadow-shell-xl">
        <div className="flex items-start justify-between gap-4 border-b border-shell-border px-5 py-4 sm:px-6">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">
              <Sparkles className="h-3.5 w-3.5 text-shell-accent" />
              Persona Onboarding
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-shell-text">
              Review {runtime.provider} / {runtime.model || 'default'}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-shell-muted">
              This draft used your private Persona Home baseline. Edit anything you want before CopeNet saves the model flavor.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-shell-border bg-shell-panel text-shell-muted transition hover:border-shell-border-strong hover:text-shell-text"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-0 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="min-h-0 overflow-y-auto border-b border-shell-border px-5 py-5 xl:border-b-0 xl:border-r xl:px-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Display Name</div>
                <input
                  value={localDraft.displayName}
                  onChange={(event) => updateField('displayName', event.target.value)}
                  className="h-12 w-full rounded-2xl border border-shell-border bg-shell-bg px-4 text-sm text-shell-text outline-none transition focus:border-shell-border-strong"
                />
              </div>
              <EditorSection label="Identity" value={localDraft.identityMarkdown} onChange={(next) => updateField('identityMarkdown', next)} />
              <EditorSection label="Soul" value={localDraft.soulMarkdown} onChange={(next) => updateField('soulMarkdown', next)} />
              <EditorSection label="Notes" value={localDraft.notesMarkdown} onChange={(next) => updateField('notesMarkdown', next)} />
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto px-5 py-5 xl:px-6">
            <div className="space-y-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Preview</div>
                <h3 className="mt-2 text-xl font-semibold text-shell-text">{localDraft.displayName || 'Model Flavor'}</h3>
              </div>
              <div className="space-y-4 rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4">
                <section>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Identity</div>
                  <ChatMarkdown content={localDraft.identityMarkdown || '_No identity drafted yet._'} />
                </section>
                <section>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Soul</div>
                  <ChatMarkdown content={localDraft.soulMarkdown || '_No soul draft yet._'} />
                </section>
                <section>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Notes</div>
                  <ChatMarkdown content={localDraft.notesMarkdown || '_No notes draft yet._'} />
                </section>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-shell-border px-5 py-4 sm:px-6">
          <button
            type="button"
            onClick={close}
            className="inline-flex items-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-4 py-2 text-sm font-medium text-shell-text transition hover:border-shell-border-strong"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-2xl bg-shell-ink px-4 py-2 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            <span>{saving ? 'Saving flavor…' : 'Approve and save'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
