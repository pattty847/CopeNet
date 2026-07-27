import { useMemo, useState } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  FilePenLine,
  FlaskConical,
  Globe2,
  Landmark,
  Plug,
  Search,
  Terminal,
  Wrench,
} from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import type { ToolDescriptor } from '../types/backend';

const HIDDEN_TOOL_IDS = new Set(['context.prepare']);

const GROUP_ORDER = [
  'market',
  'search',
  'run',
  'change',
  'remember',
  'web',
  'artifacts',
  'connected',
  'other',
] as const;

type ToolGroupId = (typeof GROUP_ORDER)[number];

const GROUP_LABELS: Record<ToolGroupId, string> = {
  market: 'Market research',
  search: 'Find & read',
  run: 'Run & verify',
  change: 'Change files',
  remember: 'Plan & remember',
  web: 'Web',
  artifacts: 'Artifacts',
  connected: 'Connected',
  other: 'Other',
};

function groupForTool(tool: ToolDescriptor): ToolGroupId {
  if (tool.id.startsWith('market.')) return 'market';
  if (tool.id === 'files.rg' || tool.id === 'files.read' || tool.id.startsWith('repo.')) return 'search';
  if (tool.id === 'shell.exec' || tool.category === 'shell-read') return 'run';
  if (tool.category === 'repo-write' || tool.id === 'files.edit' || tool.id === 'files.write') return 'change';
  if (
    tool.id.startsWith('memory.') ||
    tool.id.startsWith('persona.') ||
    tool.id.startsWith('plan.') ||
    tool.id.startsWith('user.')
  ) return 'remember';
  if (tool.id.startsWith('web.')) return 'web';
  if (tool.category === 'artifact') return 'artifacts';
  if (tool.category === 'mcp') return 'connected';
  return 'other';
}

export function toolDisplayName(tool: ToolDescriptor): string {
  return tool.name || tool.id;
}

export function ToolGlyph({ toolId, className = 'h-3 w-3' }: { toolId: string; className?: string }) {
  if (toolId.startsWith('market.')) return <Landmark className={className} />;
  if (toolId === 'files.rg' || toolId === 'files.read') return <Search className={className} />;
  if (toolId === 'shell.exec') return <Terminal className={className} />;
  if (toolId === 'files.edit' || toolId === 'files.write') return <FilePenLine className={className} />;
  if (toolId.startsWith('memory.') || toolId.startsWith('persona.') || toolId.startsWith('plan.')) {
    return <Brain className={className} />;
  }
  if (toolId.startsWith('web.')) return <Globe2 className={className} />;
  if (toolId.startsWith('artifact.')) return <FlaskConical className={className} />;
  if (toolId.includes('.')) return <Plug className={className} />;
  return <Wrench className={className} />;
}

export function toolDirective(tool: ToolDescriptor): string {
  return `Use the \`${tool.id}\` tool for this — call it rather than answering from memory. `;
}

interface ToolPromptPaletteProps {
  selectedToolIds?: string[];
  onToggle?: (tool: ToolDescriptor) => void;
  /** Fleet still uses its text composer until structured fleet turns land. */
  onInsert?: (text: string) => void;
  compact?: boolean;
}

export function ToolPromptPalette({
  selectedToolIds = [],
  onToggle,
  onInsert,
  compact = false,
}: ToolPromptPaletteProps) {
  const tools = useAppStore((state) => state.tools);
  const [query, setQuery] = useState('');
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    market: true,
    search: true,
  });
  const selected = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const groups = new Map<ToolGroupId, ToolDescriptor[]>();
    for (const tool of tools) {
      if (!tool.id || HIDDEN_TOOL_IDS.has(tool.id)) continue;
      const primarySearch = `${tool.id} ${tool.name || ''}`.toLowerCase();
      const descriptionSearch = (tool.description || '').toLowerCase();
      const matchesDescription = needle.length >= 4 && descriptionSearch.includes(needle);
      if (needle && !primarySearch.includes(needle) && !matchesDescription) continue;
      const groupId = groupForTool(tool);
      groups.set(groupId, [...(groups.get(groupId) || []), tool]);
    }
    for (const list of groups.values()) list.sort((a, b) => a.id.localeCompare(b.id));
    return GROUP_ORDER.flatMap((groupId) => {
      const groupTools = groups.get(groupId);
      return groupTools?.length ? [[groupId, groupTools] as const] : [];
    });
  }, [query, tools]);

  if (tools.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-operator-border p-3 text-[11px] text-operator-muted">
        No tools reported by the backend yet.
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <label className="relative block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-operator-muted/65" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a tool…"
          aria-label="Find a tool"
          className="w-full rounded-lg border border-operator-border bg-operator-bg/70 py-2 pl-8 pr-2 text-[11px] text-operator-text outline-none transition-colors placeholder:text-operator-muted/55 focus:border-operator-accent/40"
        />
      </label>

      <div className={`flex flex-col gap-1.5 overflow-y-auto ${compact ? 'max-h-72' : ''}`}>
        {grouped.length === 0 ? (
          <div className="rounded-lg border border-dashed border-operator-border px-3 py-4 text-center text-[11px] text-operator-muted">
            No tools match “{query}”.
          </div>
        ) : grouped.map(([groupId, groupTools]) => {
          const open = query ? true : (openGroups[groupId] ?? false);
          const selectedCount = groupTools.filter((tool) => selected.has(tool.id)).length;
          return (
            <div key={groupId} className="rounded-xl border border-operator-border bg-operator-bg/45">
              <button
                type="button"
                onClick={() => setOpenGroups((current) => ({ ...current, [groupId]: !open }))}
                className="flex w-full items-center justify-between px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-muted transition hover:text-operator-text"
              >
                <span className="flex items-center gap-1.5">
                  {GROUP_LABELS[groupId]}
                  {selectedCount > 0 ? (
                    <span className="rounded-full bg-operator-accent/12 px-1.5 py-0.5 text-[9px] text-operator-accent">
                      {selectedCount}
                    </span>
                  ) : null}
                </span>
                {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              </button>
              {open && (
                <div className="flex flex-col gap-1 px-2 pb-2">
                  {groupTools.map((tool) => {
                    const isSelected = selected.has(tool.id);
                    return (
                      <button
                        key={tool.id}
                        type="button"
                        onClick={() => {
                          if (onToggle) onToggle(tool);
                          else if (onInsert) onInsert(toolDirective(tool));
                        }}
                        aria-pressed={onToggle ? isSelected : undefined}
                        title={tool.description}
                        className={`group flex items-start gap-2 rounded-lg px-2 py-1.5 text-left transition ${
                          isSelected
                            ? 'bg-operator-accent/10 text-operator-accent'
                            : 'hover:bg-operator-panel'
                        }`}
                      >
                        <span className="mt-0.5 shrink-0 text-operator-muted group-hover:text-operator-accent">
                          <ToolGlyph toolId={tool.id} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[11px] font-medium text-operator-text">{toolDisplayName(tool)}</span>
                          <span className="block truncate font-mono text-[9px] text-operator-muted">{tool.id}</span>
                        </span>
                        {isSelected ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-operator-accent" /> : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
