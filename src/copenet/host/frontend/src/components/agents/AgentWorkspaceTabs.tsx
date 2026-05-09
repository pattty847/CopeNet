import type { AgentWorkspaceTab } from '../../store/useAppStore';

const TABS: Array<{ id: AgentWorkspaceTab; label: string }> = [
  { id: 'messages', label: 'Messages' },
  { id: 'tool_activity', label: 'Tool Activity' },
  { id: 'artifacts', label: 'Artifacts' },
];

export function AgentWorkspaceTabs({
  value,
  onChange,
}: {
  value: AgentWorkspaceTab;
  onChange: (tab: AgentWorkspaceTab) => void;
}) {
  return (
    <div className="border-b border-operator-border px-3 pt-1.5">
      <div className="flex items-center gap-1 text-[11px] font-semibold">
        {TABS.map((tab) => {
          const active = value === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              className={`rounded-t-lg border-b-2 px-3 py-2 transition-colors ${
                active
                  ? 'border-operator-accent bg-operator-accent/6 text-operator-accent'
                  : 'border-transparent text-operator-muted hover:text-operator-text'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
