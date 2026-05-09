import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, FolderOpen, Mic, Paperclip, Plus, Send, Sparkles, X } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import { useAppStore } from '../../store/useAppStore';
import type { DraftSettings, Model, PromptOptimizationVariant, PromptOption, Provider } from '../../types/backend';

export interface RuntimePillSummary {
  provider: string;
  model: string;
  profile: string;
  statusLabel: string;
  workspaceRoot?: string | null;
  locked: boolean;
}

type DraftRuntimeField = 'provider' | 'model' | 'profile' | 'mode';

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
    <div className="absolute bottom-full left-0 z-30 mb-2 min-w-[15rem] overflow-hidden rounded-2xl border border-white/10 bg-[#171c27]/95 shadow-[0_22px_60px_rgba(0,0,0,0.55)] backdrop-blur-xl">
      <div className="border-b border-white/6 px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-muted">
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
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${selected ? 'bg-white/8 text-white' : 'text-operator-text hover:bg-white/5'}`}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium">{option.label}</span>
                {option.hint ? <span className="mt-0.5 block truncate text-[10px] text-operator-muted">{option.hint}</span> : null}
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
    <div className="relative min-w-0">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || !onClick}
        className={`group flex min-w-0 items-center gap-1 rounded-lg px-2 py-1.25 text-left transition-all ${disabled || !onClick ? 'cursor-default opacity-70' : active ? 'bg-white/8 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]' : 'hover:bg-white/5'} `}
      >
        <span className="block min-w-0">
          <span className="block text-[9px] font-semibold uppercase tracking-[0.16em] text-operator-muted/80">{title}</span>
          <span className="mt-0.5 block truncate text-[12px] font-medium text-operator-text">{value}</span>
        </span>
        {onClick ? <ChevronDown className={`h-3 w-3 shrink-0 text-operator-muted transition-transform ${active ? 'translate-y-[1px] text-operator-accent' : 'group-hover:text-operator-text'}`} /> : null}
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
      <div className="relative z-10 flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-[1.8rem] border border-white/10 bg-[#0f141c] shadow-[0_30px_120px_rgba(0,0,0,0.65)] sm:rounded-[1.8rem]">
        <div className="flex items-start gap-3 border-b border-white/8 px-4 py-4 sm:px-5">
          <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-operator-accent/12 text-operator-accent">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-muted">Optimize Prompt</div>
            <div className="mt-1 text-[14px] font-medium text-operator-text">Clarify the ask before sending. Original stays yours unless you replace it.</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-xl text-operator-muted transition-colors hover:bg-white/5 hover:text-white"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-5">
          <section className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Original</div>
                <div className="mt-1 text-[12px] text-operator-muted">Edit the source prompt, then regenerate variants if you want a fresh pass.</div>
              </div>
              <button
                type="button"
                onClick={onGenerate}
                disabled={!originalPrompt.trim() || busy}
                className="rounded-xl border border-white/10 px-3 py-2 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
              >
                {busy ? 'Generating…' : 'Regenerate'}
              </button>
            </div>
            <textarea
              value={originalPrompt}
              onChange={(event) => onOriginalPromptChange(event.target.value)}
              rows={4}
              className="w-full resize-y rounded-2xl border border-white/8 bg-[#0b1017] px-3 py-3 text-[13px] leading-5 text-operator-text outline-none transition-colors focus:border-operator-accent/35"
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Optimized Variants</div>
                <div className="mt-1 text-[12px] text-operator-muted">Pick one, tweak it if you want, then replace the composer or send it.</div>
              </div>
              {error ? <div className="text-right text-[11px] text-amber-300">{error}</div> : null}
            </div>

            <div className="grid gap-3 lg:grid-cols-3">
              {variants.map((variant) => {
                const selected = variant.id === selectedVariantId;
                return (
                  <button
                    key={variant.id}
                    type="button"
                    onClick={() => onSelectVariant(variant.id)}
                    className={`rounded-2xl border p-3 text-left transition-all ${selected ? 'border-operator-accent/45 bg-operator-accent/10 shadow-[inset_0_0_0_1px_rgba(109,168,255,0.18)]' : 'border-white/8 bg-white/[0.03] hover:border-white/14 hover:bg-white/[0.05]'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[13px] font-semibold text-operator-text">{variant.label}</div>
                        <div className="mt-1 text-[11px] leading-4 text-operator-muted">{variant.rationale}</div>
                      </div>
                      <span className={`mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full border ${selected ? 'border-operator-accent/55 bg-operator-accent/20 text-operator-accent' : 'border-white/10 text-transparent'}`}>
                        <Check className="h-3 w-3" />
                      </span>
                    </div>
                    <textarea
                      value={variant.prompt}
                      onChange={(event) => onVariantPromptChange(variant.id, event.target.value)}
                      onClick={(event) => event.stopPropagation()}
                      rows={8}
                      className="mt-3 w-full resize-y rounded-2xl border border-white/8 bg-[#0b1017] px-3 py-3 text-[12px] leading-5 text-operator-text outline-none transition-colors focus:border-operator-accent/35"
                    />
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Custom Transform</div>
            <div className="mt-1 text-[12px] text-operator-muted">Ask for a specific rewrite like “make it more technical” or “turn this into an execution plan”.</div>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                value={customTransform}
                onChange={(event) => onCustomTransformChange(event.target.value)}
                placeholder="Make it more technical, shorter, or execution-focused…"
                className="min-w-0 flex-1 rounded-2xl border border-white/8 bg-[#0b1017] px-3 py-2.5 text-[12px] text-operator-text outline-none transition-colors focus:border-operator-accent/35"
              />
              <button
                type="button"
                onClick={onGenerateCustom}
                disabled={!originalPrompt.trim() || !customTransform.trim() || busy}
                className="rounded-2xl border border-white/10 px-3 py-2.5 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
              >
                {busy ? 'Generating…' : 'Generate custom'}
              </button>
            </div>
          </section>
        </div>

        <div className="flex flex-col gap-2 border-t border-white/8 bg-[#0c1118] px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <button
            type="button"
            onClick={onUseOriginal}
            className="rounded-2xl border border-white/10 px-3 py-2.5 text-[11px] font-semibold text-operator-text transition-colors hover:border-white/20"
          >
            Send original
          </button>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={onReplaceComposer}
              disabled={!selectedVariant?.prompt?.trim()}
              className="rounded-2xl border border-white/10 px-3 py-2.5 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/35 hover:text-operator-accent disabled:opacity-40"
            >
              Replace composer
            </button>
            <button
              type="button"
              onClick={onSendSelected}
              disabled={!selectedVariant?.prompt?.trim()}
              className="rounded-2xl bg-operator-accent px-3 py-2.5 text-[11px] font-semibold text-operator-bg transition-opacity disabled:opacity-40"
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
  onSend: (messageOverride?: string) => void;
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
  const taskModes = useAppStore((state) => state.taskModes);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const runtimeContext = useAppStore((state) => state.runtimeContext);
  const patchDraftSettings = useAppStore((state) => state.patchDraftSettings);

  const isDraft = !runtimeSummary.locked && runtimeSummary.statusLabel.toLowerCase() === 'draft';
  const availableModels = draftSettings.provider ? modelsByProvider[draftSettings.provider] || [] : [];
  const currentWorkspaceRoot = draftSettings.workspaceRoot || runtimeContext?.workspaceRoot || '';
  const workspaceName = useMemo(() => workspaceLabel(currentWorkspaceRoot), [currentWorkspaceRoot]);

  const providerOptions = useMemo(() => makeProviderOptions(providers), [providers]);
  const modelOptions = useMemo(() => makeModelOptions(availableModels), [availableModels]);
  const profileOptions = useMemo(() => makePromptOptions(profiles), [profiles]);
  const modeOptions = useMemo(() => makePromptOptions(taskModes), [taskModes]);

  const selectedProvider = providerOptions.find((option) => option.id === draftSettings.provider)?.label || 'Select provider';
  const selectedModel = modelOptions.find((option) => option.id === draftSettings.model)?.label || (draftSettings.provider ? 'Select model' : 'Pick provider first');
  const selectedProfile = profileOptions.find((option) => option.id === draftSettings.systemPromptId)?.label || 'Profile';
  const selectedMode = modeOptions.find((option) => option.id === draftSettings.taskPromptId)?.label || 'Mode';
  const selectedVariant = optimizedVariants.find((variant) => variant.id === selectedVariantId) || null;

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

  return (
    <>
      <div className="border-t border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center justify-between px-0.5 pb-1 text-[10px] font-semibold uppercase tracking-wider">
          <span className={disabled ? 'text-operator-muted/50' : 'text-operator-muted'}>{statusCopy}</span>
          <span className={runtimeSummary.locked ? 'text-operator-success' : 'text-operator-accent'}>{runtimeSummary.statusLabel}</span>
        </div>

        {!isDraft && (
          <div className="mb-2 relative" ref={runtimeRef}>
            <button
              type="button"
              onClick={() => setRuntimeOpen((current) => !current)}
              className="flex min-h-10 w-full flex-wrap items-center gap-2 rounded-xl border border-operator-border bg-operator-bg px-3 py-2 text-left text-[12px] transition-colors hover:border-operator-accent/30"
            >
              <span className="font-medium text-operator-text">{runtimeSummary.provider}</span>
              <span className="text-operator-muted">·</span>
              <span className="text-operator-text">{runtimeSummary.model}</span>
              <span className="text-operator-muted">·</span>
              <span className="text-operator-text">{runtimeSummary.profile}</span>
              <span className="ml-auto inline-flex items-center rounded-full border border-operator-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-success">
                {runtimeSummary.statusLabel}
              </span>
            </button>

            {runtimeOpen && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-full rounded-2xl border border-operator-border bg-operator-bg p-3 shadow-xl">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Runtime</div>
                <div className="mt-2 space-y-1.5 text-[12px] text-operator-text">
                  <div>Provider: {runtimeSummary.provider}</div>
                  <div>Model: {runtimeSummary.model}</div>
                  <div>Profile: {runtimeSummary.profile}</div>
                  {runtimeSummary.workspaceRoot && <div className="break-all text-operator-muted">Workspace: {runtimeSummary.workspaceRoot}</div>}
                </div>
                {runtimeSummary.locked && (
                  <div className="mt-3 rounded-xl border border-operator-accent/20 bg-operator-accent/8 px-3 py-2 text-[11px] leading-5 text-operator-muted">
                    This session is locked to its current runtime. Start a new session if you want a different provider, model, profile, or mode.
                  </div>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setRuntimeOpen(false);
                      onStartNewSession();
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-operator-border px-3 py-2 text-[11px] font-semibold text-operator-text transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Start new session
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="rounded-[1.2rem] border border-white/7 bg-[#0f141c] shadow-[inset_0_1px_0_rgba(255,255,255,0.02)] transition-colors focus-within:border-operator-accent/35" ref={isDraft ? runtimeRef : undefined}>
          <div className="flex items-end gap-1 px-2.5 py-2">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={onKeyDown}
              disabled={disabled}
              placeholder={placeholder}
              className="max-h-[128px] flex-1 resize-none overflow-y-auto bg-transparent px-0.5 py-0.5 text-[13px] leading-5 text-operator-text outline-none placeholder:text-operator-muted/50 disabled:opacity-40"
              rows={1}
            />
            <div className="flex items-center gap-0.5 pb-0">
              <button disabled={disabled} className="rounded-lg p-2 text-operator-muted transition-colors hover:bg-white/5 hover:text-operator-text disabled:opacity-40" title="Attach file">
                <Paperclip className="h-3.5 w-3.5" />
              </button>
              <button disabled={disabled} className="rounded-lg p-2 text-operator-muted transition-colors hover:bg-white/5 hover:text-operator-text disabled:opacity-40" title="Voice input">
                <Mic className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => void openOptimizer()}
                disabled={!value.trim() || disabled}
                className="rounded-lg p-2 text-operator-muted transition-colors hover:bg-white/5 hover:text-operator-accent disabled:opacity-40"
                title="Optimize prompt"
              >
                <Sparkles className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onSend()}
                disabled={!value.trim() || disabled}
                className="glow-accent ml-0.5 flex h-10 w-10 items-center justify-center rounded-xl bg-operator-accent text-operator-bg disabled:cursor-not-allowed disabled:opacity-30 disabled:shadow-none"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {isDraft ? (
            <div className="border-t border-white/6 px-2 pb-2 pt-1.5">
              <div className="flex flex-wrap items-stretch gap-1 rounded-[1rem] border border-white/6 bg-[#141923] p-1">
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

                <span className="my-1 hidden w-px bg-white/6 sm:block" />

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

                <span className="my-1 hidden w-px bg-white/6 sm:block" />

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

                <span className="my-1 hidden w-px bg-white/6 sm:block" />

                <RuntimeSegment title="Mode" value={selectedMode} active={openDraftMenu === 'mode'} onClick={() => setOpenDraftMenu((current) => current === 'mode' ? null : 'mode')}>
                  {openDraftMenu === 'mode' ? (
                    <RuntimeMenu
                      label="Task mode"
                      options={modeOptions}
                      selectedId={draftSettings.taskPromptId || ''}
                      onSelect={(nextValue) => updateDraftSetting('taskPromptId', nextValue)}
                      onClose={() => setOpenDraftMenu(null)}
                    />
                  ) : null}
                </RuntimeSegment>

                <span className="my-1 hidden w-px bg-white/6 sm:block" />

                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => void chooseWorkspaceRoot()}
                    disabled={workspaceBusy}
                    className="group flex h-full min-h-[2.8rem] w-full min-w-0 items-center gap-2 rounded-lg px-2 py-1.25 text-left transition-colors hover:bg-white/5 disabled:opacity-50"
                    title={currentWorkspaceRoot || 'Choose workspace root'}
                  >
                    <FolderOpen className="h-3.5 w-3.5 shrink-0 text-operator-accent" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[9px] font-semibold uppercase tracking-[0.18em] text-operator-muted/80">Workspace</span>
                      <span className="mt-0.5 block truncate text-[12px] font-medium text-operator-text">{workspaceBusy ? 'Choosing workspace…' : workspaceName}</span>
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
          onSend(optimizerOriginal);
        }}
        onReplaceComposer={() => {
          if (!selectedVariant?.prompt?.trim()) return;
          onChange(selectedVariant.prompt);
          setOptimizerOpen(false);
        }}
        onSendSelected={() => {
          if (!selectedVariant?.prompt?.trim()) return;
          setOptimizerOpen(false);
          onSend(selectedVariant.prompt);
        }}
        onClose={() => setOptimizerOpen(false)}
      />
    </>
  );
}
