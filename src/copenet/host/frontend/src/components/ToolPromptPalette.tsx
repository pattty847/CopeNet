import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import type { ToolDescriptor } from '../types/backend';

// Categories the operator can meaningfully ask for by name. Internal/plumbing
// tools stay out of the palette even though they are registered.
const HIDDEN_TOOL_IDS = new Set(['context.prepare']);

const CATEGORY_LABELS: Record<string, string> = {
  'repo-read': 'Repository',
  'repo-write': 'Repository (write)',
  'shell-read': 'Shell',
  context: 'Data & Context',
  artifact: 'Artifacts',
  mcp: 'Connected (MCP)',
};

export function toolDirective(tool: ToolDescriptor): string {
  return `Use the \`${tool.id}\` tool for this — call it rather than answering from memory. `;
}

function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || (category ? category : 'Other');
}

export function ToolPromptPalette({ onInsert }: { onInsert: (text: string) => void }) {
  const tools = useAppStore((state) => state.tools);
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({ context: true });

  const grouped = useMemo(() => {
    const groups = new Map<string, ToolDescriptor[]>();
    for (const tool of tools) {
      if (!tool.id || HIDDEN_TOOL_IDS.has(tool.id)) continue;
      const list = groups.get(tool.category) || [];
      list.push(tool);
      groups.set(tool.category, list);
    }
    for (const list of groups.values()) list.sort((a, b) => a.id.localeCompare(b.id));
    // Data & Context first — it holds the market tools this palette exists for.
    return [...groups.entries()].sort(([a], [b]) => {
      if (a === b) return 0;
      if (a === 'context') return -1;
      if (b === 'context') return 1;
      return a.localeCompare(b);
    });
  }, [tools]);

  if (grouped.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-operator-border p-3 text-[11px] text-operator-muted">
        No tools reported by the backend yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {grouped.map(([category, categoryTools]) => {
        const open = openCategories[category] ?? false;
        return (
          <div key={category} className="rounded-xl border border-operator-border bg-operator-bg/45">
            <button
              type="button"
              onClick={() => setOpenCategories((current) => ({ ...current, [category]: !open }))}
              className="flex w-full items-center justify-between px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-muted transition hover:text-operator-text"
            >
              <span>{categoryLabel(category)}</span>
              {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            </button>
            {open && (
              <div className="flex flex-col gap-1 px-2 pb-2">
                {categoryTools.map((tool) => (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => onInsert(toolDirective(tool))}
                    title={tool.description}
                    className="group flex items-start gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-operator-panel"
                  >
                    <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-operator-muted group-hover:text-operator-accent" />
                    <span className="min-w-0">
                      <span className="block truncate text-[11px] font-medium text-operator-text">{tool.name || tool.id}</span>
                      <span className="block truncate font-mono text-[9px] text-operator-muted">{tool.id}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
