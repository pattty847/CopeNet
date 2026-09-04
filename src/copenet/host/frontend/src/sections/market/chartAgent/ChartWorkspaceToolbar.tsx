import { MessageSquare, MousePointer2, Scan, Minus, Square, TrendingUp, Type } from 'lucide-react';
import type { ChartWorkspaceController } from './useChartWorkspace';
import type { DrawingMode } from '../drawings/types';

const MODES: { mode: DrawingMode; label: string; Icon: typeof Minus }[] = [
  { mode: 'select', label: 'Select chart drawing', Icon: MousePointer2 },
  { mode: 'range', label: 'Select chart region', Icon: Scan },
  { mode: 'level', label: 'Draw price level', Icon: Minus },
  { mode: 'zone', label: 'Draw price zone', Icon: Square },
  { mode: 'trendline', label: 'Draw trendline', Icon: TrendingUp },
  { mode: 'label', label: 'Add chart label', Icon: Type },
];
export function ChartWorkspaceToolbar({ workspace, comparing }: { workspace: ChartWorkspaceController; comparing: boolean }) {
  const hint = comparing ? 'Price drawings are hidden in comparison mode' : workspace.mode === 'range' ? 'Click the first and last candle' : workspace.mode === 'zone' || workspace.mode === 'trendline' ? 'Click two anchors on the chart' : workspace.mode === 'select' ? '' : 'Click on the chart to place';
  return <div className="ca-toolbar" aria-label="Chart drawing tools"><div>
    {MODES.map(({ mode, label, Icon }) => <button key={mode} title={label} aria-label={label} aria-pressed={workspace.mode === mode} disabled={!workspace.document || workspace.busy || comparing}
      onClick={() => workspace.setMode(mode)}><Icon size={14} /></button>)}
  </div><span className="ca-tool-hint">{hint}</span>
    <button className="ca-open" aria-label={workspace.open ? 'Close chart agent' : 'Open chart agent'} aria-pressed={workspace.open} onClick={() => workspace.setOpen(!workspace.open)}><MessageSquare size={14} /> Agent</button>
  </div>;
}
