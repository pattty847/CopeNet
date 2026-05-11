import { Copy, FolderTree, LoaderCircle, Shield, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { wsClient } from '../../lib/wsClient';
import { resolvePersonaRuntime } from '../../lib/personaCommands';
import { useAppStore } from '../../store/useAppStore';
import type { PersonaPrivacyTier, Session } from '../../types/backend';

function groupLoadedFiles(paths: string[]) {
  const groups = {
    sharedCore: [] as string[],
    privateContext: [] as string[],
    memory: [] as string[],
    modelFlavor: [] as string[],
    other: [] as string[],
  };
  for (const path of paths) {
    if (path.includes('/core/')) groups.sharedCore.push(path);
    else if (path.includes('/models/')) groups.modelFlavor.push(path);
    else if (path.includes('/memory/')) groups.memory.push(path);
    else if (path.includes('/user/') || path.includes('/environment/')) groups.privateContext.push(path);
    else groups.other.push(path);
  }
  return groups;
}

function currentSession(sessions: Session[], activeSessionKey: string | null) {
  return sessions.find((session) => session.key === activeSessionKey) || null;
}

function FileGroup({
  title,
  paths,
}: {
  title: string;
  paths: string[];
}) {
  if (paths.length === 0) return null;
  return (
    <section className="space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">{title}</div>
      <div className="space-y-2">
        {paths.map((path) => (
          <div key={path} className="flex items-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-3 py-2 text-sm text-shell-text">
            <FolderTree className="h-3.5 w-3.5 shrink-0 text-shell-accent" />
            <span className="min-w-0 flex-1 truncate" title={path}>
              {path}
            </span>
            <button
              type="button"
              onClick={() => void navigator.clipboard.writeText(path)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-xl text-shell-muted transition hover:bg-shell-panel hover:text-shell-text"
              title="Copy path"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PersonaHomePanel() {
  const personaHome = useAppStore((state) => state.personaHome);
  const personaSettings = useAppStore((state) => state.personaSettings);
  const personaContext = useAppStore((state) => state.personaContext);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setPersonaFlavorReviewOpen = useAppStore((state) => state.setPersonaFlavorReviewOpen);
  const setPersonaFlavorDraft = useAppStore((state) => state.setPersonaFlavorDraft);
  const setAppError = useAppStore((state) => state.setAppError);
  const [loading, setLoading] = useState(false);
  const [savingTier, setSavingTier] = useState<PersonaPrivacyTier | null>(null);

  const runtime = useMemo(
    () => resolvePersonaRuntime(currentSession(sessions, activeSessionKey), draftSettings),
    [activeSessionKey, draftSettings, sessions],
  );
  const loadedGroups = useMemo(() => groupLoadedFiles(personaContext?.loadedFiles || personaHome?.loadedFiles || []), [personaContext, personaHome]);

  const refresh = async () => {
    setLoading(true);
    try {
      await Promise.all([
        wsClient.getPersonaSummary({
          provider: runtime.provider,
          model: runtime.model,
          privacyTier: runtime.personaPrivacyTier,
        }),
        wsClient.getPersonaContext({
          provider: runtime.provider,
          model: runtime.model,
          privacyTier: runtime.personaPrivacyTier,
        }),
      ]);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to load Persona Home.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [runtime.provider, runtime.model, runtime.personaPrivacyTier]);

  const updatePrivacy = async (tier: PersonaPrivacyTier) => {
    if (!personaSettings) return;
    setSavingTier(tier);
    try {
      await wsClient.updatePersonaSettings({
        ...personaSettings,
        defaultPrivacyTier: tier,
      });
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to update persona privacy.');
    } finally {
      setSavingTier(null);
    }
  };

  const handleOnboard = async () => {
    if (!runtime.provider) return;
    setLoading(true);
    try {
      const draft = await wsClient.draftPersonaFlavor({
        provider: runtime.provider,
        model: runtime.model,
      });
      if (!draft) {
        throw new Error('Persona flavor draft returned no content.');
      }
      setPersonaFlavorDraft(draft);
      setPersonaFlavorReviewOpen(true);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to draft persona flavor.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="animate-fade-in-up space-y-3">
      <section className="shell-page-utility-hero rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-6 sm:py-5">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
          <Sparkles className="h-3.5 w-3.5 text-shell-accent" />
          Persona Home
        </div>
        <h1 className="max-w-4xl font-display text-[2rem] leading-[1.02] tracking-tight text-shell-text sm:text-[2.6rem]">
          Give CopeNet a stable self, then let each model earn its own flavor.
        </h1>
        <p className="mt-4 max-w-3xl text-[14px] leading-6 text-shell-muted sm:mt-5 sm:text-base sm:leading-7">
          Persona Home is where identity, privacy, and model-specific nuance become explicit. It stays inspectable so continuity feels grounded instead of spooky.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleOnboard()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-2xl bg-shell-ink px-4 py-2 text-sm font-semibold text-white transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            <span>Onboard current model</span>
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-2xl border border-shell-border bg-shell-bg px-4 py-2 text-sm font-medium text-shell-text transition hover:border-shell-border-strong disabled:cursor-not-allowed disabled:opacity-60"
          >
            Refresh
          </button>
        </div>
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_360px]">
        <div className="space-y-3">
          <div className="shell-page-utility-tile rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-5 sm:py-5">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-shell-border bg-shell-bg px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">
                Active persona
              </span>
              <span className="rounded-full border border-shell-border bg-shell-bg px-3 py-1 text-[11px] font-medium text-shell-text">
                {personaHome?.personaId || runtime.personaId}
              </span>
              <span className="rounded-full border border-shell-border bg-shell-bg px-3 py-1 text-[11px] font-medium text-shell-text">
                {runtime.provider} / {runtime.model || 'default'}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[20px] border border-shell-border bg-shell-bg px-4 py-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Effective flavor</div>
                <div className="mt-2 text-lg font-semibold text-shell-text">{personaHome?.personaFlavorId || runtime.personaFlavorId || 'No saved flavor yet'}</div>
                <p className="mt-2 text-sm leading-6 text-shell-muted">
                  {personaHome?.active ? 'Persona Home is active for this runtime.' : 'Persona Home is currently inactive for this runtime.'}
                </p>
              </div>
              <div className="rounded-[20px] border border-shell-border bg-shell-bg px-4 py-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Root path</div>
                <div className="mt-2 break-all text-sm leading-6 text-shell-text">{personaHome?.rootDir || 'Unavailable'}</div>
              </div>
            </div>
          </div>

          <div className="shell-page-utility-tile rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-5 sm:py-5">
            <div className="mb-4 flex items-center gap-2">
              <Shield className="h-4 w-4 text-shell-accent" />
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-muted">Loaded files</div>
            </div>
            <div className="space-y-4">
              <FileGroup title="Shared core" paths={loadedGroups.sharedCore} />
              <FileGroup title="Private user & environment" paths={loadedGroups.privateContext} />
              <FileGroup title="Memory" paths={loadedGroups.memory} />
              <FileGroup title="Model flavor" paths={loadedGroups.modelFlavor} />
              <FileGroup title="Other" paths={loadedGroups.other} />
            </div>
            <details className="mt-5 rounded-[20px] border border-shell-border bg-shell-bg px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-shell-text">Prompt preview</summary>
              <pre className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-shell-muted">
                {personaContext?.prompt || 'No prompt payload loaded yet.'}
              </pre>
            </details>
          </div>
        </div>

        <div className="space-y-3">
          <div className="shell-page-utility-tile rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Privacy</div>
            <div className="space-y-2">
              {(['private', 'safe', 'off'] as PersonaPrivacyTier[]).map((tier) => (
                <button
                  key={tier}
                  type="button"
                  onClick={() => void updatePrivacy(tier)}
                  disabled={!personaSettings || Boolean(savingTier)}
                  className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm transition ${
                    personaSettings?.defaultPrivacyTier === tier
                      ? 'border-shell-accent bg-shell-accent-soft text-shell-text'
                      : 'border-shell-border bg-shell-bg text-shell-text hover:border-shell-border-strong'
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  <span className="font-medium capitalize">{tier}</span>
                  {savingTier === tier ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm leading-6 text-shell-muted">
              Default privacy affects new drafts and onboarding context. Active locked sessions keep their existing tier.
            </p>
          </div>

          <div className="shell-page-utility-tile rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Model overrides</div>
            <div className="space-y-2">
              {personaSettings && Object.keys(personaSettings.modelOverrides).length > 0 ? (
                Object.entries(personaSettings.modelOverrides).map(([key, override]) => (
                  <div key={key} className="rounded-2xl border border-shell-border bg-shell-bg px-4 py-3">
                    <div className="text-sm font-medium text-shell-text">{key}</div>
                    <div className="mt-1 text-xs leading-5 text-shell-muted">
                      Persona: {override.personaId} · Flavor: {override.flavorId || 'none'}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-shell-border bg-shell-bg px-4 py-4 text-sm leading-6 text-shell-muted">
                  No explicit overrides saved yet. Onboarding the current model will create one.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
