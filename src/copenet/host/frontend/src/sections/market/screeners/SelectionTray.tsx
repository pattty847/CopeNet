// Batch research surface. One quiet sentence at zero selections; the copy / export /
// research-list controls appear only once something is checked.
import { useState } from 'react';

export function SelectionTray({
  selected,
  busy,
  onClear,
  onCopy,
  onExport,
  onCreateList,
}: {
  selected: string[];
  busy: boolean;
  onClear: () => void;
  onCopy: () => void;
  onExport: () => void;
  onCreateList: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const empty = selected.length === 0;
  return (
    <div className="scr-tray" data-empty={empty}>
      {!empty && (
        <>
          <strong>{selected.length} selected</strong>
          <span className="scr-tray__symbols">{selected.join('  ')}</span>
        </>
      )}
      <span className="scr-tray__grow" />
      {!empty && (
        <>
          <button type="button" className="tw-btn tw-btn--sm" onClick={onClear}>
            Clear
          </button>
          <button type="button" className="tw-btn tw-btn--sm" disabled={busy} onClick={onCopy}>
            Copy symbols
          </button>
        </>
      )}
      <button type="button" className="tw-btn tw-btn--sm" disabled={busy} onClick={onExport}>
        Export evidence JSON
      </button>
      {!empty && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onCreateList(name.trim()).then(() => setName(''));
          }}
        >
          <label>
            <span className="scr-sr-only">New research list</span>
            <input value={name} required maxLength={30} placeholder="New research list" onChange={(event) => setName(event.target.value)} />
          </label>
          <button type="submit" className="tw-btn tw-btn--sm" data-active="true" disabled={busy || selected.length > 500}>
            Create watchlist
          </button>
        </form>
      )}
      <small>
        {empty
          ? 'Select names to copy them, export the evidence, or build a research list.'
          : 'New lists start with automatic scanning off. Choose the list explicitly in Scans & alerts to acquire research data.'}
      </small>
    </div>
  );
}
