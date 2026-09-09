// My Focus: the operator's own checklist and notes pad.
//
// The only thing on Home that CopeNet does not derive — it is what the operator wrote down,
// as distinct from memory, which is what CopeNet learned. It never enters a prompt.
//
// State lives on the server rather than in localStorage because the same desk is opened
// from the Mac and from the phone over Tailscale, and a checklist that disagreed between
// them would be worse than no checklist. Every mutation returns the whole document, so
// the component replaces state rather than patching it.

import { useEffect, useRef, useState } from 'react';
import { Check, ListTodo, X } from 'lucide-react';
import { wsClient } from '../../../lib/wsClient';
import type { FocusUpdate } from '../../../lib/wsHomeRpc';
import type { FocusState } from '../../../types/backend';
import { Card } from './Card';

const NOTES_DEBOUNCE_MS = 700;

export function MyFocus({ focus, onChange }: { focus: FocusState | null; onChange: (next: FocusState) => void }) {
  const [draft, setDraft] = useState('');
  const [notes, setNotes] = useState(focus?.notes ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const notesTimer = useRef<number | null>(null);
  // Typing must not be interrupted by a save round-trip echoing the old text back.
  const notesDirty = useRef(false);

  useEffect(() => {
    if (!notesDirty.current) setNotes(focus?.notes ?? '');
  }, [focus?.notes]);

  const apply = async (update: FocusUpdate) => {
    setError(null);
    try {
      onChange(await wsClient.updateFocus(update));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save.');
    }
  };

  const submitItem = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    void apply({ op: 'add', text });
  };

  const queueNotes = (value: string) => {
    setNotes(value);
    notesDirty.current = true;
    if (notesTimer.current) window.clearTimeout(notesTimer.current);
    notesTimer.current = window.setTimeout(() => {
      setSaving(true);
      void apply({ op: 'notes', notes: value }).finally(() => {
        notesDirty.current = false;
        setSaving(false);
      });
    }, NOTES_DEBOUNCE_MS);
  };

  useEffect(() => () => {
    if (notesTimer.current) window.clearTimeout(notesTimer.current);
  }, []);

  const items = focus?.items ?? [];
  const open = items.filter((item) => !item.done).length;

  return (
    <Card
      title="My focus"
      icon={ListTodo}
      span={3}
      className="hd-focus"
      head={
        <>
          <div className="hd-card__spacer" />
          {items.some((item) => item.done) && (
            <button type="button" className="hd-link" onClick={() => void apply({ op: 'clearDone' })}>
              Clear done
            </button>
          )}
          <span className="hd-saved">{open > 0 ? `${open} open` : ''}</span>
        </>
      }
    >
      {items.map((item) => (
        <div key={item.itemId} className="hd-check">
          <button
            type="button"
            role="checkbox"
            aria-checked={item.done}
            aria-label={item.done ? `Mark "${item.text}" not done` : `Mark "${item.text}" done`}
            className="hd-check__box"
            onClick={() => void apply({ op: 'toggle', itemId: item.itemId, done: !item.done })}
          >
            {item.done && <Check size={10} strokeWidth={3} />}
          </button>
          <span className="hd-check__text" data-done={item.done}>
            {item.text}
          </span>
          <button
            type="button"
            className="hd-check__remove"
            aria-label={`Remove "${item.text}"`}
            onClick={() => void apply({ op: 'remove', itemId: item.itemId })}
          >
            <X size={11} />
          </button>
        </div>
      ))}

      {/* Enter is handled on the input rather than by implicit form submission: a bare
          input with no submit button does not reliably submit its form, and the failure
          mode is silent — the operator keeps typing into a field that never commits. */}
      <input
        className="hd-focus__add"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            submitItem();
          }
        }}
        onBlur={submitItem}
        placeholder={items.length === 0 ? 'What are you doing today?' : 'Add another…'}
        aria-label="Add a focus item"
      />

      <div className="hd-notes-label">
        Notes{saving && <span className="hd-saved"> · saving</span>}
        {error && <span style={{ color: 'var(--mkt-down)' }}> · {error}</span>}
      </div>
      <textarea
        className="hd-notes"
        value={notes}
        onChange={(event) => queueNotes(event.target.value)}
        placeholder="Jot down notes, ideas, or reminders…"
        aria-label="Notes"
      />
    </Card>
  );
}
