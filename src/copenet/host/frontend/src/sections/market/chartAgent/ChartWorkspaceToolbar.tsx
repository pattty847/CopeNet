import { DRAWING_KINDS } from '../drawings/kinds';
import { MAGNET_LABELS, MAGNET_MODES } from '../drawings/magnet';
import { useEffect, useRef } from 'react';
import { Activity, ArrowRight, CircleDot, GitBranch, Layers3, Magnet, MessageSquare, MousePointer2, Minus, MoveVertical, Ruler, Scan, Square, Target, TrendingUp, Type, X } from 'lucide-react';
import type { ChartWorkspaceController } from './useChartWorkspace';
import type { DrawingMode } from '../drawings/types';
import { useChartMenuRegistry } from '../chartMenuRegistry';

type Tool = { mode: DrawingMode; label: string; Icon: typeof Minus };
const PRIMARY: Tool[] = [
  { mode: 'select', label: 'Select chart drawing', Icon: MousePointer2 },
  { mode: 'range', label: 'Select chart region', Icon: Scan },
  { mode: 'level', label: 'Draw price level', Icon: Minus },
];
const GROUPS: Array<{ label: string; Icon: typeof Minus; tools: Tool[] }> = [
  { label: 'Lines', Icon: TrendingUp, tools: [
    { mode: 'trendline', label: 'Draw trendline', Icon: TrendingUp },
    { mode: 'extended_trendline', label: 'Draw extended trendline', Icon: TrendingUp },
    { mode: 'horizontal_ray', label: 'Draw horizontal ray', Icon: ArrowRight },
    { mode: 'ray', label: 'Draw ray', Icon: ArrowRight },
    { mode: 'vertical_line', label: 'Draw vertical line', Icon: MoveVertical },
  ] },
  { label: 'Measure', Icon: Ruler, tools: [
    { mode: 'measurement', label: 'Measure price and time range', Icon: Ruler },
    { mode: 'position', label: 'Draw long or short position', Icon: Target },
    { mode: 'channel', label: 'Draw parallel channel', Icon: GitBranch },
  ] },
  { label: 'Studies', Icon: Activity, tools: [
    { mode: 'avwap', label: 'Draw anchored VWAP', Icon: Activity },
    { mode: 'fib_retracement', label: 'Draw Fibonacci retracement', Icon: Layers3 },
  ] },
  { label: 'Annotate', Icon: Type, tools: [
    { mode: 'zone', label: 'Draw price zone', Icon: Square },
    { mode: 'label', label: 'Add chart label', Icon: Type },
    { mode: 'callout', label: 'Add chart callout', Icon: CircleDot },
  ] },
];

function ToolButton({ tool, workspace, comparing, closeMenu }: { tool: Tool; workspace: ChartWorkspaceController; comparing?: boolean; closeMenu?: () => void }) {
  const { mode, label, Icon } = tool;
  return <button type="button" title={label} aria-label={label} aria-pressed={workspace.mode === mode}
    disabled={!workspace.document || workspace.busy || comparing} onClick={() => { workspace.setMode(mode); closeMenu?.(); }}>
    <Icon size={14} />{closeMenu ? label : mode === 'range' ? 'Range' : null}
  </button>;
}

/** Controlled, not native.
 *
 *  A bare `<details>` knows nothing about its siblings, so all four groups opened at once
 *  and stayed open — and `closeMenu` reached for `document.querySelector('.ca-tool-menu[open]')`,
 *  which is the FIRST open menu rather than this one. The toolbar owns which group is open
 *  and `preventDefault` on the summary stops the browser toggling it independently. */
function ToolMenu({ group, workspace, comparing, open, onToggle, onPick }: {
  group: typeof GROUPS[number];
  workspace: ChartWorkspaceController;
  comparing: boolean;
  open: boolean;
  onToggle: () => void;
  onPick: () => void;
}) {
  const active = group.tools.some((tool) => tool.mode === workspace.mode);
  return <details className={`ca-tool-menu${active ? ' is-active' : ''}`} open={open}>
    <summary
      title={`${group.label} drawing tools`}
      aria-expanded={open}
      onClick={(event) => { event.preventDefault(); onToggle(); }}
    ><group.Icon size={14} /><span>{group.label}</span></summary>
    <div className="ca-tool-menu__items" role="menu" aria-label={`${group.label} drawing tools`}>
      {group.tools.map((tool) => (
        <ToolButton key={tool.mode} tool={tool} workspace={workspace} comparing={comparing} closeMenu={onPick} />
      ))}
    </div>
  </details>;
}

export function ChartWorkspaceToolbar({ workspace, comparing }: { workspace: ChartWorkspaceController; comparing: boolean }) {
  // Shared with the chart toolbar's popovers: opening Plots puts an open tool group away
  // and vice versa. `id` is the group label, or null when none of them is the open menu.
  const menus = useChartMenuRegistry();
  const openGroup = menus.openId?.startsWith('draw:') ? menus.openId.slice('draw:'.length) : null;
  const barRef = useRef<HTMLDivElement>(null);

  // Anything outside the bar closes the open group — including a tap on the chart, which is
  // where the operator looks next. `pointerdown` in the CAPTURE phase, not `mousedown`:
  // Lightweight Charts handles touch on its canvas and calls `preventDefault`, so on a phone
  // a tap there never produced a synthesized mouse event and the menu stayed open over the
  // chart it was about to be used on.
  useEffect(() => {
    if (!openGroup) return;
    const dismiss = (event: Event) => {
      if (!barRef.current?.contains(event.target as Node)) menus.setOpenId(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') menus.setOpenId(null);
    };
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', dismiss, true);
      document.removeEventListener('keydown', escape);
    };
  }, [menus, openGroup]);

  const touchHint = workspace.mode !== 'select' && workspace.mode !== 'range' && window.matchMedia('(pointer: coarse)').matches;
  const hint = comparing ? 'Price drawings are hidden in comparison mode' : touchHint ? 'Tap to drop the cursor · drag anywhere to move it · tap to place' : workspace.mode === 'range' ? 'Drag across candles or tap start and end · Esc cancels' : workspace.mode === 'select' ? '' : ['Click/tap the chart to place', 'Click/tap anchor 1, then anchor 2', 'Click/tap three anchors'][DRAWING_KINDS[workspace.mode].anchors - 1] + ' · Esc cancels';
  return <div className="ca-toolbar" aria-label="Chart drawing tools" ref={barRef}><div className="ca-toolbar__tools">
    {PRIMARY.map((tool) => <ToolButton key={tool.mode} tool={tool} workspace={workspace} />)}
    {GROUPS.map((group) => (
      <ToolMenu
        key={group.label}
        group={group}
        workspace={workspace}
        comparing={comparing}
        open={openGroup === group.label}
        onToggle={() => menus.setOpenId(openGroup === group.label ? null : `draw:${group.label}`)}
        onPick={() => menus.setOpenId(null)}
      />
    ))}
    <button type="button" className="ca-magnet" data-magnet={workspace.magnet} aria-label={MAGNET_LABELS[workspace.magnet]} title={`${MAGNET_LABELS[workspace.magnet]} · click to change`}
      aria-pressed={workspace.magnet !== 'off'} disabled={comparing}
      onClick={() => workspace.setMagnet(MAGNET_MODES[(MAGNET_MODES.indexOf(workspace.magnet) + 1) % MAGNET_MODES.length])}>
      <Magnet size={14} />{workspace.magnet === 'strong' && <sup>+</sup>}
    </button>
  {workspace.selection && <button type="button" aria-label="Clear selected range" title="Clear selected range · use visible range" onClick={() => workspace.setSelection(null)}><X size={14} /></button>}
  </div><span className="ca-tool-hint">{hint}</span>
    <button type="button" className="ca-open" aria-label={workspace.open ? 'Close chart agent' : 'Open chart agent'} aria-pressed={workspace.open} onClick={() => workspace.setOpen(!workspace.open)}><MessageSquare size={14} /> Agent</button>
  </div>;
}
