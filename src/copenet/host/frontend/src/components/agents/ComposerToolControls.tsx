import { useEffect, useMemo, useRef, useState } from 'react';
import { Wrench, X } from 'lucide-react';
import { ToolGlyph, ToolPromptPalette, toolDisplayName } from '../ToolPromptPalette';
import { useAppStore } from '../../store/useAppStore';
import type { ToolDescriptor } from '../../types/backend';

const EMPTY_TOOL_IDS: string[] = [];

function useComposerTools(composerKey: string) {
  const selectedToolIds = useAppStore((state) => state.composerRequestedToolIds[composerKey]) || EMPTY_TOOL_IDS;
  const addTool = useAppStore((state) => state.addComposerRequestedTool);
  const removeTool = useAppStore((state) => state.removeComposerRequestedTool);

  const toggleTool = (tool: ToolDescriptor) => {
    if (selectedToolIds.includes(tool.id)) removeTool(composerKey, tool.id);
    else addTool(composerKey, tool.id);
  };

  return { selectedToolIds, removeTool, toggleTool };
}

export function ComposerToolPalette({ composerKey, compact = false }: { composerKey: string; compact?: boolean }) {
  const { selectedToolIds, toggleTool } = useComposerTools(composerKey);
  return (
    <ToolPromptPalette
      selectedToolIds={selectedToolIds}
      onToggle={toggleTool}
      compact={compact}
    />
  );
}

export function ComposerToolTray({ composerKey }: { composerKey: string }) {
  const tools = useAppStore((state) => state.tools);
  const { selectedToolIds, removeTool } = useComposerTools(composerKey);
  const toolById = useMemo(() => new Map(tools.map((tool) => [tool.id, tool])), [tools]);

  if (selectedToolIds.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-operator-border/60 px-3 py-2">
      <span className="mr-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-muted/65">
        Tools
      </span>
      {selectedToolIds.map((toolId) => {
        const tool = toolById.get(toolId);
        return (
          <span
            key={toolId}
            title={tool?.description || toolId}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-operator-accent/20 bg-operator-accent/7 py-1 pl-2 pr-1 text-[10.5px] text-operator-text"
          >
            <span className="text-operator-accent">
              <ToolGlyph toolId={toolId} />
            </span>
            <span className="max-w-44 truncate">{tool ? toolDisplayName(tool) : toolId}</span>
            <button
              type="button"
              onClick={() => removeTool(composerKey, toolId)}
              aria-label={`Remove ${tool ? toolDisplayName(tool) : toolId}`}
              className="flex h-4 w-4 items-center justify-center rounded-full text-operator-muted transition-colors hover:bg-operator-bg/70 hover:text-operator-error"
              title="Remove tool"
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </span>
        );
      })}
    </div>
  );
}

export function ComposerToolPickerButton({
  composerKey,
  disabled,
}: {
  composerKey: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const selectedToolIds = useAppStore((state) => state.composerRequestedToolIds[composerKey]) || EMPTY_TOOL_IDS;

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, [open]);

  return (
    <div className="relative lg:hidden" ref={rootRef}>
      {open ? (
        <div className="absolute bottom-full right-0 z-40 mb-2 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-operator-border bg-operator-panel p-2.5 shadow-shell-xl backdrop-blur">
          <div className="mb-2 flex items-center justify-between px-1">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted">
                Tools for next message
              </div>
              <div className="mt-0.5 text-[10px] text-operator-muted/65">
                Attached behind the scenes; your message stays clean.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close tool picker"
              className="rounded-md p-1 text-operator-muted hover:bg-operator-bg hover:text-operator-text"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <ComposerToolPalette composerKey={composerKey} compact />
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        disabled={disabled}
        aria-label="Attach tools"
        aria-expanded={open}
        className={`relative rounded-lg p-2 transition-colors disabled:opacity-40 ${
          open || selectedToolIds.length > 0
            ? 'bg-operator-accent/10 text-operator-accent'
            : 'text-operator-muted/80 hover:bg-operator-panel hover:text-operator-accent'
        }`}
        title="Attach tools to the next message"
      >
        <Wrench className="h-3.5 w-3.5" />
        {selectedToolIds.length > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-operator-accent px-0.5 text-[8px] font-bold text-operator-bg">
            {selectedToolIds.length}
          </span>
        ) : null}
      </button>
    </div>
  );
}
