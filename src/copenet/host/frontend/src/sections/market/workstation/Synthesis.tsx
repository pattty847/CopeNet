// AI synthesis — the model's interpretation of the computed facts, visibly stamped as such.
//
// It follows the deterministic delta on purpose: evidence first, interpretation labelled.
// The read's own thesis-killers ("what would make this wrong") live here, under the claim
// they qualify, folded until asked. The Model read control sits with the read, not in the
// bar, because it acts on this block alone.

import { useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw, Sparkles } from 'lucide-react';
import { ModelBadge } from '../marketUi';
import type { ContrarianNote, MarketRead, Panel } from '../types';

/** Headline with its emphasis substring lifted into the accent, when the two align. */
function Emphasized({ text, emphasis }: { text: string; emphasis?: string }) {
  if (!emphasis || !text.includes(emphasis)) return <>{text}</>;
  const [before, after] = text.split(emphasis);
  return (
    <>
      {before}
      <em>{emphasis}</em>
      {after}
    </>
  );
}

function ThesisKillers({ notes, source }: { notes: ContrarianNote[]; source: string }) {
  const [open, setOpen] = useState(false);
  if (notes.length === 0) return null;
  return (
    <div className="mw-killers">
      <button type="button" className="mw-more" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }} onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        What would make this wrong · {notes.length}
        <span className="mw-sect__meta" style={{ marginLeft: 4 }}>{source}</span>
      </button>
      {open && (
        <div className="mw-killers__list">
          {notes.map((note, index) => (
            <div key={index} className="mw-killer">
              <b>{note.signal}</b>
              <p>{note.kill}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Synthesis({
  read,
  reading,
  readError,
  onRunRead,
  onExplain,
  onOpen,
  contrarian,
}: {
  read: MarketRead | null;
  reading: boolean;
  readError: string | null;
  onRunRead: () => void;
  onExplain: () => void;
  onOpen: (symbol: string) => void;
  /** The computed thesis-killers, used until a model read supplies its own. */
  contrarian: Panel<ContrarianNote[]>;
}) {
  const killers = read && read.thesisKillers.length ? read.thesisKillers : contrarian.data;
  const killersSource = read && read.thesisKillers.length ? 'model read' : contrarian.note ?? 'computed';

  return (
    <section className="mw-synth" aria-label="AI synthesis">
      <div className="mw-sect" style={{ marginBottom: 2 }}>
        <span className="mw-sect__label">AI synthesis</span>
        {read && <ModelBadge model={read.model} generatedAt={read.generatedAt} />}
        <span className="mw-sect__spacer" />
        <button type="button" className="tw-btn" style={{ color: 'var(--mkt-info)', borderColor: 'rgba(143,184,232,.3)' }} onClick={onRunRead} disabled={reading}>
          {reading ? <RefreshCw size={12} className="tw-spin" /> : <Sparkles size={12} />}
          {reading ? 'Reading the tape…' : read ? 'Read again' : 'Model read'}
        </button>
      </div>

      {readError && <p className="mw-inline-error" role="alert" style={{ margin: '4px 0 8px' }}>{readError}</p>}

      {read ? (
        <>
          <p className="mw-synth__headline"><Emphasized text={read.headline} emphasis={read.emphasis} /></p>
          <p className="mw-synth__summary">{read.summary}</p>
          {read.attention.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {read.attention.map((item, index) => (
                <button key={`attn-${index}`} type="button" className="mw-attn" onClick={() => onOpen(item.symbol)} title={item.why}>
                  <span className="mw-attn__sym">{item.symbol}</span>
                  <span className="mw-attn__kind">{item.kind}</span>
                </button>
              ))}
            </div>
          )}
          <button type="button" className="mw-more" style={{ marginTop: 8 }} onClick={onExplain}>Why this read →</button>
          {read.caveats && <p className="mw-caveat">{read.caveats}</p>}
        </>
      ) : (
        !readError && (
          <p className="mw-quiet" style={{ margin: '4px 0 0', maxWidth: '78ch' }}>
            No model read yet. A read interprets the computed facts — regime, rotation, attention — and logs every call to the forward ledger. Evidence-based with caveats, never forecasts.
          </p>
        )
      )}

      <ThesisKillers notes={killers} source={killersSource} />
    </section>
  );
}
