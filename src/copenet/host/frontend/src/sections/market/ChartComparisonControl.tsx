import { useState, type FormEvent } from 'react';
import { GitCompareArrows, X } from 'lucide-react';
import { normalizeComparisonExpression } from './chartComparison';
import { MM, mono } from './marketUi';

export function ChartComparisonControl({
  active,
  expressions,
  onActive,
  onAdd,
  onRemove,
  onClear,
}: {
  active: boolean;
  expressions: string[];
  onActive: (active: boolean) => void;
  onAdd: (expression: string) => void;
  onRemove: (expression: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const expression = normalizeComparisonExpression(input);
    if (!expression) {
      setError('Enter a ticker or one ratio, such as XLK/GLD.');
      return;
    }
    if (expressions.includes(expression)) {
      setError('That comparison is already plotted.');
      return;
    }
    if (expressions.length >= 5) {
      setError('Remove a series before adding another.');
      return;
    }
    onAdd(expression);
    onActive(true);
    setInput('');
    setError(null);
  };

  return (
    <div className="chart-comparison-control">
      <div className="chart-comparison-modes" role="group" aria-label="Chart display mode">
        <button type="button" aria-pressed={!active} onClick={() => onActive(false)}>Price</button>
        <button
          type="button"
          aria-pressed={active}
          onClick={() => {
            if (expressions.length) onActive(true);
            setOpen((value) => !value);
          }}
        >
          <GitCompareArrows size={13} /> Compare{expressions.length ? ` ${expressions.length}` : ''}
        </button>
      </div>
      {open && (
        <div className="chart-comparison-popover">
          <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', gap: 12 }}>
            <div><div style={{ color: MM.text, font: '650 11px Inter' }}>Indexed comparison</div><div style={{ marginTop: 3, color: MM.dim, fontSize: 10.5 }}>Symbols and ratios start at 0% for the visible range.</div></div>
            <button type="button" aria-label="Close comparison editor" onClick={() => setOpen(false)} className="chart-comparison-close"><X size={14} /></button>
          </div>
          <form onSubmit={submit} style={{ marginTop: 12 }}>
            <label htmlFor="chart-comparison-expression" style={{ display: 'block', marginBottom: 5, color: MM.muted, font: '600 9px Inter', letterSpacing: '.08em', textTransform: 'uppercase' }}>Ticker or ratio</label>
            <div style={{ display: 'flex', gap: 6 }}><input id="chart-comparison-expression" value={input} onChange={(event) => { setInput(event.target.value); if (error) setError(null); }} placeholder="XLK or XLK/GLD" autoCapitalize="characters" spellCheck={false} /><button type="submit">Add</button></div>
            {error && <div role="alert" style={{ marginTop: 6, color: MM.down, fontSize: 10.5 }}>{error}</div>}
          </form>
          <div className="chart-comparison-list">
            {expressions.length ? expressions.map((expression) => <span key={expression} style={{ fontFamily: mono }}>{expression}<button type="button" aria-label={`Remove ${expression}`} onClick={() => onRemove(expression)}><X size={11} /></button></span>) : <p>No comparisons yet. Add a ticker or relative-strength ratio.</p>}
          </div>
          {expressions.length > 0 && <button type="button" className="chart-comparison-clear" onClick={onClear}>Clear comparisons</button>}
        </div>
      )}
    </div>
  );
}
