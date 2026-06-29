import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, FolderOpen, Loader2, Mic, Paperclip, Plus, Send, Sparkles, Square, X } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import { useVoiceToText } from '../../lib/useVoiceToText';
import { useAppStore } from '../../store/useAppStore';
import { accessOptionsFor, providerAllowsFullAccess } from '../../lib/access';
import { uploadChatAttachment } from '../../lib/appApi';
import type { ChatAttachment, DraftSettings, Model, PromptOptimizationVariant, PromptOption, Provider } from '../../types/backend';

/** A composer-local image attachment in flight: object-URL preview + upload status. */
interface PendingAttachment {
  localId: string;
  filename: string;
  previewUrl: string;
  status: 'uploading' | 'ready' | 'error';
  attachment: ChatAttachment | null;
  error?: string;
}

export interface RuntimePillSummary {
  provider: string;
  model: string;
  profile: string;
  statusLabel: string;
  workspaceRoot?: string | null;
  locked: boolean;
}

type DraftRuntimeField = 'provider' | 'model' | 'profile' | 'access';

interface RuntimeOption {
  id: string;
  label: string;
  hint?: string;
}


function workspaceLabel(workspaceRoot?: string | null) {
  if (!workspaceRoot) return 'Choose workspace';
  const parts = workspaceRoot.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || workspaceRoot;
}

function makeProviderOptions(providers: Provider[]): RuntimeOption[] {
  return providers.map((provider) => ({
    id: provider.id,
    label: provider.displayName,
    hint: provider.available ? undefined : provider.error || 'Unavailable',
  }));
}

function makeModelOptions(models: Model[]): RuntimeOption[] {
  return models.map((model) => ({
    id: model.id,
    label: model.displayName,
    hint: model.description || undefined,
  }));
}

function makePromptOptions(options: PromptOption[]): RuntimeOption[] {
  return options.map((option) => ({
    id: option.id,
    label: option.name,
    hint: undefined,
  }));
}

function RuntimeMenu({
  label,
  options,
  selectedId,
  onSelect,
  onClose,
}: {
  label: string;
  options: RuntimeOption[];
  selectedId: string;
  onSelect: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute bottom-full left-0 z-30 mb-2 min-w-[15rem] overflow-hidden rounded-2xl border border-operator-border bg-operator-panel shadow-shell-xl backdrop-blur">
      <div className="border-b border-operator-border/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted/85">
        {label}
      </div>
      <div className="max-h-72 overflow-y-auto p-1.5">
        {options.length > 0 ? options.map((option) => {
          const selected = option.id === selectedId;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                onSelect(option.id);
                onClose();
              }}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${selected ? 'bg-operator-accent/10 text-operator-accent' : 'text-operator-text hover:bg-operator-bg/70'}`}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium">{option.label}</span>
                {option.hint ? <span className="mt-0.5 block truncate text-[10px] text-operator-muted/85">{option.hint}</span> : null}
              </span>
              <span className="shrink-0 text-operator-accent">{selected ? <Check className="h-3.5 w-3.5" /> : null}</span>
            </button>
          );
        }) : (
          <div className="px-3 py-3 text-[11px] text-operator-muted">No options available.</div>
        )}
      </div>
    </div>
  );
}

function RuntimeSegment({
  title,
  value,
  active,
  disabled,
  onClick,
  children,
}: {
  title: string;
  value: string;
  active: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="relative min-w-0 flex-1">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || !onClick}
        className={`group flex w-full min-w-0 items-center gap-1 rounded-lg px-2 py-1 text-left transition-all ${disabled || !onClick ? 'cursor-default opacity-60' : active ? 'bg-operator-accent/8 text-operator-accent shadow-[inset_0_0_0_1px_var(--color-operator-accent)]/[.18]' : 'hover:bg-operator-panel/70'} `}
      >
        <span className="block min-w-0">
          <span className="block text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-muted/75">{title}</span>
          <span className="mt-0.5 block truncate text-[11.5px] font-medium text-operator-text">{value}</span>
        </span>
        {onClick ? <ChevronDown className={`ml-auto h-3 w-3 shrink-0 text-operator-muted/65 transition-transform ${active ? 'rotate-180 text-operator-accent' : 'group-hover:text-operator-text'}`} /> : null}
      </button>
      {children}
    </div>
  );
}

function PromptOptimizerModal({
  open,
  busy,
  error,
  originalPrompt,
  onOriginalPromptChange,
  variants,
  selectedVariantId,
  onSelectVariant,
  onVariantPromptChange,
  customTransform,
  onCustomTransformChange,
  onGenerate,
  onGenerateCustom,
  onUseOriginal,
  onReplaceComposer,
  onSendSelected,
  onClose,
}: {
  open: boolean;
  busy: boolean;
  error: string | null;
  originalPrompt: string;
  onOriginalPromptChange: (value: string) => void;
  variants: PromptOptimizationVariant[];
  selectedVariantId: string | null;
  onSelectVariant: (value: string) => void;
  onVariantPromptChange: (variantId: string, value: string) => void;
  customTransform: string;
  onCustomTransformChange: (value: string) => void;
  onGenerate: () => void;
  onGenerateCustom: () => void;
  onUseOriginal: () => void;
  onReplaceComposer: () => void;
  onSendSelected: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [open, onClose]);

  if (!open) return null;

  const selectedVariant = variants.find((variant) => variant.id === selectedVariantId) || null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-3xl border border-operator-border bg-operator-bg shadow-shell-xl sm:rounded-3xl">
        <div className="flex items-start gap-3 border-b border-operator-border px-4 py-3.5 sm:px-5">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-operator-accent/10 text-operator-accent">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted/85">Optimize Prompt</div>
            <div className="mt-0.5 text-[14px] font-medium text-operator-text">Clarify the ask before sending. Original stays yours unless you replace it.</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-operator-muted transition-colors hover:bg-operator-panel hover:text-operator-text"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-5">
          <section className="rounded-2xl border border-operator-border bg-operator-panel/40 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div>
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-operator-muted/85">Original</div>
                <div className="mt-0.5 text-[11.5px] text-operator-muted/85">Edit the source prompt, then regenerate variants if you want a fresh pass.</div>
              </div>
              <button
                type="button"
                onClick={onGenerate}
                disabled={!originalPrompt.trim() || busy}
                className="rounded-lg border border-operator-border px-3 py-1.5 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
              >
                {busy ? 'Generating…' : 'Regenerate'}
              </button>
            </div>
            <textarea
              value={originalPrompt}
              onChange={(event) => onOriginalPromptChange(event.target.value)}
              rows={4}
              className="w-full resize-y rounded-xl border border-operator-border bg-operator-bg px-3 py-2.5 text-[13px] leading-5 text-operator-text outline-none transition-colors focus:border-operator-accent/40"
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-operator-muted/85">Optimized Variants</div>
                <div className="mt-0.5 text-[11.5px] text-operator-muted/85">Pick one, tweak it if you want, then replace the composer or send it.</div>
              </div>
              {error ? <div className="text-right text-[11px] text-operator-error">{error}</div> : null}
            </div>

            <div className="grid gap-3 lg:grid-cols-3">
              {variants.map((variant) => {
                const selected = variant.id === selectedVariantId;
                return (
                  <button
                    key={variant.id}
                    type="button"
                    onClick={() => onSelectVariant(variant.id)}
                    className={`rounded-2xl border p-3 text-left transition-all ${selected ? 'border-operator-accent/45 bg-operator-accent/8' : 'border-operator-border bg-operator-panel/30 hover:border-operator-accent/25 hover:bg-operator-panel/50'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[13px] font-semibold text-operator-text">{variant.label}</div>
                        <div className="mt-1 text-[11px] leading-[1.4] text-operator-muted/85">{variant.rationale}</div>
                      </div>
                      <span className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected ? 'border-operator-accent/60 bg-operator-accent/20 text-operator-accent' : 'border-operator-border text-transparent'}`}>
                        <Check className="h-3 w-3" />
                      </span>
                    </div>
                    <textarea
                      value={variant.prompt}
                      onChange={(event) => onVariantPromptChange(variant.id, event.target.value)}
                      onClick={(event) => event.stopPropagation()}
                      rows={8}
                      className="mt-3 w-full resize-y rounded-xl border border-operator-border bg-operator-bg px-3 py-2.5 text-[12px] leading-5 text-operator-text outline-none transition-colors focus:border-operator-accent/40"
                    />
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-operator-border bg-operator-panel/30 p-3">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-operator-muted/85">Custom Transform</div>
            <div className="mt-0.5 text-[11.5px] text-operator-muted/85">Ask for a specific rewrite like "make it more technical" or "turn this into an execution plan".</div>
            <div className="mt-2.5 flex flex-col gap-2 sm:flex-row">
              <input
                value={customTransform}
                onChange={(event) => onCustomTransformChange(event.target.value)}
                placeholder="Make it more technical, shorter, or execution-focused…"
                className="min-w-0 flex-1 rounded-xl border border-operator-border bg-operator-bg px-3 py-2 text-[12px] text-operator-text outline-none transition-colors focus:border-operator-accent/40"
              />
              <button
                type="button"
                onClick={onGenerateCustom}
                disabled={!originalPrompt.trim() || !customTransform.trim() || busy}
                className="rounded-xl border border-operator-border px-3 py-2 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
              >
                {busy ? 'Generating…' : 'Generate custom'}
              </button>
            </div>
          </section>
        </div>

        <div className="flex flex-col gap-2 border-t border-operator-border bg-operator-panel/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <button
            type="button"
            onClick={onUseOriginal}
            className="rounded-xl border border-operator-border px-3 py-2 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
          >
            Send original
          </button>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={onReplaceComposer}
              disabled={!selectedVariant?.prompt?.trim()}
              className="rounded-xl border border-operator-border px-3 py-2 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
            >
              Replace composer
            </button>
            <button
              type="button"
              onClick={onSendSelected}
              disabled={!selectedVariant?.prompt?.trim()}
              className="glow-accent rounded-xl bg-operator-accent px-4 py-2 text-[11px] font-semibold text-operator-bg disabled:opacity-40"
            >
              Send selected
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function AgentComposer({
  value,
  onChange,
  onKeyDown,
  onSend,
  optimizationProviderId,
  optimizationModelId,
  disabled,
  placeholder,
  statusCopy,
  runtimeSummary,
  onStartNewSession,
}: {
  value: string;
  onChange: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: (messageOverride?: string, attachments?: ChatAttachment[]) => void;
  optimizationProviderId: string;
  optimizationModelId?: string | null;
  disabled: boolean;
  placeholder: string;
  statusCopy: string;
  runtimeSummary: RuntimePillSummary;
  onStartNewSession: () => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const runtimeRef = useRef<HTMLDivElement | null>(null);
  const lastDirectSendAtRef = useRef(0);
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [openDraftMenu, setOpenDraftMenu] = useState<DraftRuntimeField | null>(null);
  const [optimizerOpen, setOptimizerOpen] = useState(false);
  const [optimizerBusy, setOptimizerBusy] = useState(false);
  const [optimizerError, setOptimizerError] = useState<string | null>(null);
  const [optimizerOriginal, setOptimizerOriginal] = useState('');
  const [customTransform, setCustomTransform] = useState('');
  const [optimizedVariants, setOptimizedVariants] = useState<PromptOptimizationVariant[]>([]);
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);

  const providers = useAppStore((state) => state.providers);
  const modelsByProvider = useAppStore((state) => state.modelsByProvider);
  const loadedModelProviders = useAppStore((state) => state.loadedModelProviders);
  const profiles = useAppStore((state) => state.profiles);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const runtimeContext = useAppStore((state) => state.runtimeContext);
  const patchDraftSettings = useAppStore((state) => state.patchDraftSettings);
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessionRuntimeOverrides = useAppStore((state) => state.sessionRuntimeOverrides);
  const setSessionRuntimeOverride = useAppStore((state) => state.setSessionRuntimeOverride);
  const activeRunId = useAppStore((state) => state.activeRunId);

  const [aborting, setAborting] = useState(false);
  const isRunning = Boolean(activeRunId);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const hasUploadingAttachment = attachments.some((item) => item.status === 'uploading');
  const readyAttachments = attachments.filter((item) => item.status === 'ready' && item.attachment);

  const ingestFiles = (files: File[]) => {
    const images = files.filter((file) => file.type.startsWith('image/'));
    if (images.length === 0) return;
    for (const file of images) {
      const localId = `att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const previewUrl = URL.createObjectURL(file);
      setAttachments((current) => [
        ...current,
        { localId, filename: file.name || 'image', previewUrl, status: 'uploading', attachment: null },
      ]);
      void uploadChatAttachment(file)
        .then((attachment) => {
          setAttachments((current) =>
            current.map((item) =>
              item.localId === localId ? { ...item, status: 'ready', attachment } : item,
            ),
          );
        })
        .catch((error) => {
          setAttachments((current) =>
            current.map((item) =>
              item.localId === localId
                ? { ...item, status: 'error', error: error instanceof Error ? error.message : 'Upload failed' }
                : item,
            ),
          );
        });
    }
  };

  const removeAttachment = (localId: string) => {
    setAttachments((current) => {
      const target = current.find((item) => item.localId === localId);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.localId !== localId);
    });
  };

  const clearAttachments = () => {
    setAttachments((current) => {
      current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      return [];
    });
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    ingestFiles(files);
    event.target.value = '';
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData?.files || []);
    const images = files.filter((file) => file.type.startsWith('image/'));
    if (images.length > 0) {
      event.preventDefault();
      ingestFiles(images);
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const files = event.dataTransfer?.files ? Array.from(event.dataTransfer.files) : [];
    ingestFiles(files);
  };

  const handleStop = async () => {
    if (aborting) return;
    setAborting(true);
    try {
      await wsClient.abortActiveRun();
    } catch (error) {
      useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Unable to stop the run.');
    } finally {
      setAborting(false);
    }
  };

  // Voice-to-text: dictate into the composer. Appends the transcript to whatever
  // is already typed (Whisper runs locally via /api/v1/media/transcribe).
  const voice = useVoiceToText((text) => {
    const needsSpace = value.length > 0 && !/\s$/.test(value);
    onChange(value + (needsSpace ? ' ' : '') + text);
  });
  useEffect(() => {
    if (voice.error) useAppStore.getState().setAppError(voice.error);
  }, [voice.error]);

  const isDraft = !runtimeSummary.locked && runtimeSummary.statusLabel.toLowerCase() === 'draft';
  const availableModels = draftSettings.provider ? modelsByProvider[draftSettings.provider] || [] : [];
  const currentWorkspaceRoot = draftSettings.workspaceRoot || runtimeContext?.workspaceRoot || '';
  const workspaceName = useMemo(() => workspaceLabel(currentWorkspaceRoot), [currentWorkspaceRoot]);

  const providerOptions = useMemo(() => makeProviderOptions(providers), [providers]);
  const modelOptions = useMemo(() => makeModelOptions(availableModels), [availableModels]);
  const profileOptions = useMemo(() => makePromptOptions(profiles), [profiles]);
  const accessOptions = useMemo(() => accessOptionsFor(draftSettings.provider), [draftSettings.provider]);

  const selectedProvider = providerOptions.find((option) => option.id === draftSettings.provider)?.label || 'Select provider';
  const selectedModel = modelOptions.find((option) => option.id === draftSettings.model)?.label || (draftSettings.provider ? 'Select model' : 'Pick provider first');
  const selectedProfile = profileOptions.find((option) => option.id === draftSettings.systemPromptId)?.label || 'Profile';
  const selectedAccess = accessOptions.find((option) => option.id === draftSettings.taskPromptId)?.label || 'Read-only';
  const selectedVariant = optimizedVariants.find((variant) => variant.id === selectedVariantId) || null;

  // Locked-session mid-session controls (A + B1): Model + Access can change on an
  // existing session (same provider). The pending change is an override applied on the
  // next send; provider/profile stay locked.
  const lockedSession = !isDraft && activeSessionKey ? sessions.find((s) => s.key === activeSessionKey) || null : null;
  const lockedOverride = activeSessionKey ? sessionRuntimeOverrides[activeSessionKey] : undefined;
  const lockedModelValue = lockedOverride?.model ?? lockedSession?.model ?? '';
  const lockedAccessValue = lockedOverride?.taskPromptId ?? lockedSession?.taskPromptId ?? 'none';
  const lockedProviderModels = lockedSession ? modelsByProvider[lockedSession.provider] || [] : [];
  const lockedAccessOptions = useMemo(() => accessOptionsFor(lockedSession?.provider), [lockedSession?.provider]);
  const lockedRuntimeDirty = Boolean(lockedOverride && (lockedOverride.model || lockedOverride.taskPromptId));
  const lockedModelLabel = lockedProviderModels.find((model) => model.id === lockedModelValue)?.displayName || lockedModelValue || runtimeSummary.model;

  // Ensure the locked session's provider models are loaded so the Model dropdown has options.
  useEffect(() => {
    if (!lockedSession) return;
    if (loadedModelProviders[lockedSession.provider]) return;
    void wsClient.loadModels(lockedSession.provider);
  }, [lockedSession, loadedModelProviders]);

  // Keep the draft honest: if the chosen provider can't grant Full Access, drop the
  // draft back to Read-only so the UI matches what the backend would actually enforce.
  useEffect(() => {
    if (!isDraft) return;
    if (draftSettings.taskPromptId === 'full-access' && !providerAllowsFullAccess(draftSettings.provider)) {
      patchDraftSettings({ taskPromptId: 'none' });
    }
  }, [isDraft, draftSettings.provider, draftSettings.taskPromptId, patchDraftSettings]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 128)}px`;
  }, [value]);

  useEffect(() => {
    if (!isDraft || !draftSettings.provider || loadedModelProviders[draftSettings.provider]) return;
    void wsClient.loadModels(draftSettings.provider);
  }, [draftSettings.provider, isDraft, loadedModelProviders]);

  useEffect(() => {
    if (!openDraftMenu && !runtimeOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (runtimeRef.current && !runtimeRef.current.contains(event.target as Node)) {
        setOpenDraftMenu(null);
        setRuntimeOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenDraftMenu(null);
        setRuntimeOpen(false);
      }
    };
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [openDraftMenu, runtimeOpen]);

  const updateDraftSetting = (key: 'provider' | 'model' | 'systemPromptId' | 'taskPromptId', nextValue: string) => {
    if (key === 'provider') {
      patchDraftSettings({ provider: nextValue, model: '' });
      void wsClient.loadModels(nextValue);
      return;
    }
    patchDraftSettings({ [key]: nextValue } as Partial<DraftSettings>);
  };

  const chooseWorkspaceRoot = async () => {
    setWorkspaceBusy(true);
    try {
      const { workspaceRoot, runtimeContext: nextContext } = await wsClient.browseWorkspaceRoot();
      if (workspaceRoot) {
        patchDraftSettings({ workspaceRoot });
      }
      if (nextContext) {
        useAppStore.getState().setRuntimeContext(nextContext);
      }
    } catch (error) {
      useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Unable to choose workspace root.');
    } finally {
      setWorkspaceBusy(false);
    }
  };

  const generateVariants = async (custom?: string) => {
    const prompt = optimizerOriginal.trim();
    if (!prompt) return;
    setOptimizerBusy(true);
    setOptimizerError(null);
    try {
      const result = await wsClient.optimizePrompt({
        prompt,
        provider: optimizationProviderId || undefined,
        model: optimizationModelId || undefined,
        customTransform: custom?.trim() || undefined,
      });
      setOptimizedVariants(result.variants);
      setSelectedVariantId(result.variants[0]?.id || null);
      if (!result.variants.length) {
        setOptimizerError('No optimized variants came back. Try regenerating.');
      }
    } catch (error) {
      setOptimizerError(error instanceof Error ? error.message : 'Unable to optimize this prompt right now.');
    } finally {
      setOptimizerBusy(false);
    }
  };

  const openOptimizer = async () => {
    const prompt = value.trim();
    if (!prompt || disabled) return;
    setOptimizerOriginal(prompt);
    setCustomTransform('');
    setOptimizerOpen(true);
    setOptimizedVariants([]);
    setSelectedVariantId(null);
    setOptimizerError(null);
    setOptimizerBusy(true);
    try {
      const result = await wsClient.optimizePrompt({
        prompt,
        provider: optimizationProviderId || undefined,
        model: optimizationModelId || undefined,
      });
      setOptimizedVariants(result.variants);
      setSelectedVariantId(result.variants[0]?.id || null);
      if (!result.variants.length) {
        setOptimizerError('No optimized variants came back. Try regenerating.');
      }
    } catch (error) {
      setOptimizerError(error instanceof Error ? error.message : 'Unable to optimize this prompt right now.');
    } finally {
      setOptimizerBusy(false);
    }
  };

  // Pass ready attachments (carrying their local previewUrl so the sent bubble
  // renders instantly) up to the parent, then clear the composer tray.
  const submitMessage = (text: string) => {
    const ready: ChatAttachment[] = readyAttachments.map((item) => ({
      ...(item.attachment as ChatAttachment),
      previewUrl: item.previewUrl,
    }));
    onSend(text, ready.length > 0 ? ready : undefined);
    clearAttachments();
  };

  const canSend = (Boolean(value.trim()) || readyAttachments.length > 0) && !disabled && !hasUploadingAttachment;

  const triggerDirectSend = () => {
    if (!canSend) return;
    const now = Date.now();
    if (now - lastDirectSendAtRef.current < 700) return;
    lastDirectSendAtRef.current = now;
    submitMessage(value);
  };

  return (
    <>
      <div className="border-t border-operator-border bg-operator-bg px-3 pb-3 pt-2">
        {!isDraft && (
          <div className="relative mb-1.5 flex items-center gap-2 px-1 text-[10.5px]" ref={runtimeRef}>
            <button
              type="button"
              onClick={() => setRuntimeOpen((current) => !current)}
              className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-full border border-operator-border bg-operator-panel/50 px-2.5 py-1 text-operator-muted/85 transition-colors hover:border-operator-accent/30 hover:text-operator-text"
              title="Runtime details"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-operator-success opacity-50" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-operator-success" />
              </span>
              <span className="truncate text-operator-text/90">{runtimeSummary.provider}</span>
              <span className="text-operator-muted/45">/</span>
              <span className="truncate text-operator-text/85">{lockedSession ? lockedModelLabel : runtimeSummary.model}</span>
              <span className="text-operator-muted/45">·</span>
              <span className="truncate">{runtimeSummary.profile}</span>
              {lockedRuntimeDirty && (
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-operator-accent" title="Pending runtime change — applies on your next message" />
              )}
              <ChevronDown className={`h-3 w-3 shrink-0 transition-transform ${runtimeOpen ? 'rotate-180 text-operator-accent' : ''}`} />
            </button>

            <span className={`ml-auto truncate text-[10.5px] ${disabled ? 'text-operator-muted/50' : 'text-operator-muted/70'}`}>
              {statusCopy}
            </span>

            {runtimeOpen && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-full max-w-sm rounded-2xl border border-operator-border bg-operator-bg p-3 shadow-shell-xl">
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted/85">Runtime</div>
                <div className="mt-2 space-y-1.5 text-[12px] text-operator-text">
                  <div className="flex items-center justify-between gap-2"><span className="text-operator-muted">Provider</span><span className="truncate text-right">{runtimeSummary.provider}</span></div>
                  {lockedSession ? (
                    <label className="flex items-center justify-between gap-2">
                      <span className="text-operator-muted">Model</span>
                      <select
                        value={lockedModelValue}
                        onChange={(event) => setSessionRuntimeOverride(lockedSession.key, { model: event.target.value })}
                        className="min-w-0 max-w-[62%] flex-1 truncate rounded-md border border-operator-border bg-operator-panel/60 px-1.5 py-1 text-right text-[11.5px] text-operator-text outline-none transition-colors focus:border-operator-accent/40"
                      >
                        {!lockedProviderModels.some((model) => model.id === lockedModelValue) && (
                          <option value={lockedModelValue}>{lockedModelValue || 'default'}</option>
                        )}
                        {lockedProviderModels.map((model) => (
                          <option key={model.id} value={model.id}>{model.displayName || model.id}</option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <div className="flex items-center justify-between gap-2"><span className="text-operator-muted">Model</span><span className="truncate text-right">{runtimeSummary.model}</span></div>
                  )}
                  <div className="flex items-center justify-between gap-2"><span className="text-operator-muted">Profile</span><span className="truncate text-right">{runtimeSummary.profile}</span></div>
                  {lockedSession && (
                    <label className="flex items-center justify-between gap-2">
                      <span className="text-operator-muted">Access</span>
                      <select
                        value={lockedAccessValue}
                        onChange={(event) => setSessionRuntimeOverride(lockedSession.key, { taskPromptId: event.target.value })}
                        className="min-w-0 max-w-[62%] flex-1 truncate rounded-md border border-operator-border bg-operator-panel/60 px-1.5 py-1 text-right text-[11.5px] text-operator-text outline-none transition-colors focus:border-operator-accent/40"
                      >
                        {lockedAccessOptions.map((option) => (
                          <option key={option.id} value={option.id}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  {runtimeSummary.workspaceRoot && (
                    <div className="pt-1 break-all font-mono text-[10.5px] leading-5 text-operator-muted">{runtimeSummary.workspaceRoot}</div>
                  )}
                </div>
                {runtimeSummary.locked && (
                  <div className="mt-2.5 rounded-lg border border-operator-accent/15 bg-operator-accent/5 px-2.5 py-1.5 text-[11px] leading-5 text-operator-muted">
                    {lockedRuntimeDirty
                      ? 'Model / Access apply on your next message.'
                      : 'Model and Access can change here. Provider and profile are locked — start a new session to change those.'}
                  </div>
                )}
                <div className="mt-2.5">
                  <button
                    type="button"
                    onClick={() => {
                      setRuntimeOpen(false);
                      onStartNewSession();
                    }}
                    className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-operator-border px-3 py-1.5 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Start new session
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div
          className={`rounded-2xl border bg-operator-panel/65 shadow-shell transition-colors focus-within:border-operator-accent/45 focus-within:shadow-shell-hover ${isDragging ? 'border-operator-accent/60 ring-1 ring-operator-accent/40' : 'border-operator-border'}`}
          ref={isDraft ? runtimeRef : undefined}
          onDragOver={(event) => { event.preventDefault(); if (!disabled) setIsDragging(true); }}
          onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }}
          onDrop={handleDrop}
        >
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 border-b border-operator-border/60 px-3 py-2">
              {attachments.map((item) => (
                <div
                  key={item.localId}
                  className="group relative h-16 w-16 overflow-hidden rounded-lg border border-operator-border bg-operator-bg"
                  title={item.error || item.filename}
                >
                  <img src={item.previewUrl} alt={item.filename} className="h-full w-full object-cover" />
                  {item.status === 'uploading' && (
                    <div className="absolute inset-0 flex items-center justify-center bg-operator-bg/60">
                      <Loader2 className="h-4 w-4 animate-spin text-operator-accent" />
                    </div>
                  )}
                  {item.status === 'error' && (
                    <div className="absolute inset-0 flex items-center justify-center bg-operator-error/30 text-[9px] font-semibold text-operator-error">
                      Failed
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => removeAttachment(item.localId)}
                    className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-operator-bg/80 text-operator-muted opacity-0 transition-opacity hover:text-operator-error group-hover:opacity-100"
                    title="Remove"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-1 px-3 py-2">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={onKeyDown}
              onPaste={handlePaste}
              disabled={disabled}
              placeholder={placeholder}
              className="max-h-[160px] min-h-[28px] flex-1 resize-none overflow-y-auto bg-transparent px-0.5 py-1 text-[13.5px] leading-[1.5] text-operator-text outline-none placeholder:text-operator-muted/55 disabled:opacity-40"
              rows={1}
            />
            <div className="flex items-center gap-0.5 pb-0">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                multiple
                className="hidden"
                onChange={handleFileInputChange}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
                className="rounded-lg p-2 text-operator-muted/80 transition-colors hover:bg-operator-panel hover:text-operator-accent disabled:opacity-40"
                title="Attach image"
              >
                <Paperclip className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => voice.toggle()}
                disabled={disabled || voice.state === 'transcribing'}
                className={`rounded-lg p-2 transition-colors disabled:opacity-40 ${
                  voice.state === 'recording'
                    ? 'text-operator-error animate-pulse'
                    : 'text-operator-muted/80 hover:bg-operator-panel hover:text-operator-accent'
                }`}
                title={
                  voice.state === 'recording'
                    ? 'Stop & transcribe'
                    : voice.state === 'transcribing'
                      ? 'Transcribing…'
                      : 'Voice input (dictate)'
                }
                aria-label="Voice input"
              >
                {voice.state === 'transcribing' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Mic className="h-3.5 w-3.5" />
                )}
              </button>
              <button
                type="button"
                onClick={() => void openOptimizer()}
                disabled={!value.trim() || disabled}
                className="rounded-lg p-2 text-operator-muted/80 transition-colors hover:bg-operator-panel hover:text-operator-accent disabled:opacity-40"
                title="Optimize prompt"
              >
                <Sparkles className="h-3.5 w-3.5" />
              </button>
              {isRunning ? (
                <button
                  type="button"
                  onClick={() => void handleStop()}
                  disabled={aborting}
                  className="ml-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-operator-error text-white transition-colors hover:bg-operator-error/90 disabled:cursor-not-allowed disabled:opacity-40"
                  title={aborting ? 'Stopping…' : 'Stop run'}
                  aria-label="Stop run"
                >
                  <Square className="h-3 w-3 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onPointerUp={(event) => {
                    if (event.pointerType === 'mouse') return;
                    event.preventDefault();
                    triggerDirectSend();
                  }}
                  onTouchEnd={(event) => {
                    event.preventDefault();
                    triggerDirectSend();
                  }}
                  onClick={triggerDirectSend}
                  disabled={!canSend}
                  className="glow-accent ml-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-operator-accent text-operator-bg disabled:cursor-not-allowed disabled:opacity-30 disabled:shadow-none"
                  title="Send"
                  aria-label="Send message"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          {isDraft ? (
            <div className="border-t border-operator-border/60 px-1.5 pb-1.5 pt-1.5">
              <div className="flex flex-wrap items-stretch gap-0.5 rounded-xl bg-operator-bg/40 p-0.5">
                <RuntimeSegment title="Provider" value={selectedProvider} active={openDraftMenu === 'provider'} onClick={() => setOpenDraftMenu((current) => current === 'provider' ? null : 'provider')}>
                  {openDraftMenu === 'provider' ? (
                    <RuntimeMenu
                      label="Provider"
                      options={providerOptions}
                      selectedId={draftSettings.provider || ''}
                      onSelect={(nextValue) => updateDraftSetting('provider', nextValue)}
                      onClose={() => setOpenDraftMenu(null)}
                    />
                  ) : null}
                </RuntimeSegment>

                <span className="my-1 hidden w-px bg-operator-border/55 sm:block" />

                <RuntimeSegment title="Model" value={selectedModel} active={openDraftMenu === 'model'} disabled={!draftSettings.provider} onClick={() => draftSettings.provider ? setOpenDraftMenu((current) => current === 'model' ? null : 'model') : null}>
                  {openDraftMenu === 'model' ? (
                    <RuntimeMenu
                      label="Model"
                      options={modelOptions}
                      selectedId={draftSettings.model || ''}
                      onSelect={(nextValue) => updateDraftSetting('model', nextValue)}
                      onClose={() => setOpenDraftMenu(null)}
                    />
                  ) : null}
                </RuntimeSegment>

                <span className="my-1 hidden w-px bg-operator-border/55 sm:block" />

                <RuntimeSegment title="Profile" value={selectedProfile} active={openDraftMenu === 'profile'} onClick={() => setOpenDraftMenu((current) => current === 'profile' ? null : 'profile')}>
                  {openDraftMenu === 'profile' ? (
                    <RuntimeMenu
                      label="Profile"
                      options={profileOptions}
                      selectedId={draftSettings.systemPromptId || ''}
                      onSelect={(nextValue) => updateDraftSetting('systemPromptId', nextValue)}
                      onClose={() => setOpenDraftMenu(null)}
                    />
                  ) : null}
                </RuntimeSegment>

                <span className="my-1 hidden w-px bg-operator-border/55 sm:block" />

                <RuntimeSegment title="Access" value={selectedAccess} active={openDraftMenu === 'access'} onClick={() => setOpenDraftMenu((current) => current === 'access' ? null : 'access')}>
                  {openDraftMenu === 'access' ? (
                    <RuntimeMenu
                      label="Access"
                      options={accessOptions}
                      selectedId={draftSettings.taskPromptId || 'none'}
                      onSelect={(nextValue) => updateDraftSetting('taskPromptId', nextValue)}
                      onClose={() => setOpenDraftMenu(null)}
                    />
                  ) : null}
                </RuntimeSegment>

                <span className="my-1 hidden w-px bg-operator-border/55 sm:block" />

                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => void chooseWorkspaceRoot()}
                    disabled={workspaceBusy}
                    className="group flex h-full min-h-[2.4rem] w-full min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-left transition-colors hover:bg-operator-panel/70 disabled:opacity-50"
                    title={currentWorkspaceRoot || 'Choose workspace root'}
                  >
                    <FolderOpen className="h-3.5 w-3.5 shrink-0 text-operator-accent" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-muted/75">Workspace</span>
                      <span className="mt-0.5 block truncate text-[11.5px] font-medium text-operator-text">{workspaceBusy ? 'Choosing workspace…' : workspaceName}</span>
                    </span>
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <PromptOptimizerModal
        open={optimizerOpen}
        busy={optimizerBusy}
        error={optimizerError}
        originalPrompt={optimizerOriginal}
        onOriginalPromptChange={setOptimizerOriginal}
        variants={optimizedVariants}
        selectedVariantId={selectedVariantId}
        onSelectVariant={setSelectedVariantId}
        onVariantPromptChange={(variantId, nextPrompt) => {
          setOptimizedVariants((current) => current.map((variant) => (
            variant.id === variantId ? { ...variant, prompt: nextPrompt } : variant
          )));
        }}
        customTransform={customTransform}
        onCustomTransformChange={setCustomTransform}
        onGenerate={() => void generateVariants()}
        onGenerateCustom={() => void generateVariants(customTransform)}
        onUseOriginal={() => {
          setOptimizerOpen(false);
          submitMessage(optimizerOriginal);
        }}
        onReplaceComposer={() => {
          if (!selectedVariant?.prompt?.trim()) return;
          onChange(selectedVariant.prompt);
          setOptimizerOpen(false);
        }}
        onSendSelected={() => {
          if (!selectedVariant?.prompt?.trim()) return;
          setOptimizerOpen(false);
          submitMessage(selectedVariant.prompt);
        }}
        onClose={() => setOptimizerOpen(false)}
      />
    </>
  );
}
