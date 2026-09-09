import { Wrench } from 'lucide-react';
import { TOOL_SHORTCUTS, type ToolShortcut } from '../dataTools';
import { Card, CardLink } from './Card';

/** Data & Tools shortcuts. Every tile goes somewhere that exists — a tile that navigates
 *  nowhere is worse than a gap, because the operator cannot tell them apart until they
 *  click. When a capability lands, it gets a tile in `dataTools.ts`. */
export function ToolShortcuts({
  onOpen,
  onOpenAll,
}: {
  onOpen: (destination: ToolShortcut['destination']) => void;
  onOpenAll: () => void;
}) {
  return (
    <Card
      title="Data &amp; tools"
      icon={Wrench}
      span={3}
      head={
        <>
          <div className="hd-card__spacer" />
          <CardLink label="Open all" onClick={onOpenAll} />
        </>
      }
    >
      <div className="hd-tool-grid">
        {TOOL_SHORTCUTS.map((tool) => (
          <button key={tool.id} type="button" className="hd-tool" onClick={() => onOpen(tool.destination)}>
            <span className="hd-tool__icon">
              <tool.icon size={12} />
            </span>
            <span className="hd-tool__text">
              <span className="hd-tool__label">{tool.label}</span>
              <span className="hd-tool__detail">{tool.detail}</span>
            </span>
          </button>
        ))}
      </div>
    </Card>
  );
}
