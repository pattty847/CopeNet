import React, { MouseEvent } from 'react';
import { Archive, ArchiveRestore, CheckSquare, Star } from 'lucide-react';
import type { SessionRowModel, SessionRowTag } from '../../runtime/sessionStanding';
import { formatSessionAge } from '../../lib/formatting';
import { SessionStateIcon } from './SessionStateIcon';

/**
 * Three lines, fixed budget. Line 1 is where the thread stands, line 2 is a sentence
 * about state and never a bare number, line 3 is always the same ledger shape so the
 * eye stops reading it word by word. Anything new changes the icon, changes line 2,
 * or becomes a tag — it does not add a fourth line.
 */
export function SessionStandingRow({
  row,
  age,
  active,
  selected,
  selectMode,
  archived,
  pinned = false,
  onSelect,
  onTogglePin,
  onArchiveToggle,
}: {
  row: SessionRowModel;
  age?: string | null;
  active: boolean;
  selected: boolean;
  selectMode: boolean;
  archived: boolean;
  pinned?: boolean;
  onSelect: () => void;
  onTogglePin?: () => void;
  onArchiveToggle: (event: MouseEvent) => void;
}) {
  const live = row.phase !== 'settled';
  return (
    <div
      onClick={onSelect}
      className={`group relative grid w-full cursor-pointer grid-cols-[15px_minmax(0,1fr)] gap-x-[9px] px-3 py-[7px] transition-colors duration-150 ${
        live
          ? 'border-l-2 border-operator-accent bg-operator-accent/[0.06] pl-[10px]'
          : selectMode
          ? selected
            ? 'border-y border-operator-accent/16 bg-operator-panel/30'
            : 'border-y border-transparent hover:bg-operator-panel/16'
          : active
          ? 'border-y border-operator-accent/18 bg-operator-panel/36'
          : 'border-y border-transparent hover:bg-operator-panel/20'
      }`}
    >
      {selectMode && !archived ? (
        <span
          className={`mt-[2px] flex h-4 w-4 items-center justify-center rounded-sm border ${
            selected ? 'border-operator-accent bg-operator-accent/12 text-operator-accent' : 'border-operator-border text-transparent'
          }`}
        >
          <CheckSquare className="h-3 w-3" />
        </span>
      ) : (
        <SessionStateIcon state={row.state} phase={row.phase} />
      )}

      <div className="flex min-w-0 flex-col gap-[2px]">
        {/* Line 1 — where it stands. Wraps to two lines before it truncates. */}
        <div className="flex items-baseline gap-2">
          <span
            className={`min-w-0 flex-grow text-[12.5px] font-semibold leading-[1.3] line-clamp-2 ${
              active || live ? 'text-operator-text' : 'text-operator-muted group-hover:text-operator-text'
            }`}
            title={row.title}
          >
            {row.title}
          </span>
          {row.offerClose ? (
            <span className="shrink-0 rounded border border-operator-accent/35 px-[5px] py-[1px] text-[9.5px] font-semibold text-operator-accent">
              close?
            </span>
          ) : (
            <span className={`shrink-0 text-[9.5px] tabular-nums ${live ? 'font-semibold text-operator-accent' : 'text-operator-muted/50'}`}>
              {live ? 'now' : formatSessionAge(age)}
            </span>
          )}
        </div>

        {/* Line 2 — a sentence about the work. */}
        {row.line ? (
          <div
            className={`truncate text-[11px] leading-[1.35] ${
              row.state === 'blocked'
                ? 'text-operator-accent'
                : row.phase === 'writing'
                ? 'italic text-operator-muted/75'
                : 'text-operator-muted/90'
            }`}
            title={row.line}
          >
            {row.line}
          </div>
        ) : null}

        {/* Line 3 — the ledger, always the same shape. */}
        {row.ledger || row.tags.length > 0 ? (
          <div className="flex items-center gap-[7px] font-mono text-[9.5px] text-operator-muted/85">
            {row.ledger ? (
              <>
                {row.ledger.added > 0 && <span className="text-operator-success">+{row.ledger.added}</span>}
                {row.ledger.removed > 0 && <span className="text-operator-error">&minus;{row.ledger.removed}</span>}
                {row.ledger.files.map((file) => (
                  <span key={file} className="truncate">
                    {file}
                  </span>
                ))}
                {row.ledger.moreFiles > 0 && <span className="text-operator-muted/50">+{row.ledger.moreFiles}</span>}
              </>
            ) : null}
            {row.tags.length > 0 ? (
              <span className="ml-auto flex shrink-0 items-center gap-[4px]">
                {row.tags.map((tag) => (
                  <RowTag key={tag.label} tag={tag} />
                ))}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {!selectMode && (
        <div className="absolute right-1.5 top-1.5 flex items-center gap-1.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          {onTogglePin && !archived && (
            <button
              onClick={(event) => {
                event.stopPropagation();
                onTogglePin();
              }}
              className={`transition-colors ${pinned ? 'text-operator-accent' : 'text-operator-muted hover:text-operator-accent'}`}
              title={pinned ? 'Unpin session' : 'Pin session'}
            >
              <Star className={`h-3 w-3 ${pinned ? 'fill-current' : ''}`} />
            </button>
          )}
          <button
            onClick={onArchiveToggle}
            className="text-operator-muted transition-colors hover:text-operator-accent"
            title={archived ? 'Restore Session' : 'Archive Session'}
          >
            {archived ? <ArchiveRestore className="h-3 w-3" /> : <Archive className="h-3 w-3" />}
          </button>
        </div>
      )}
    </div>
  );
}

function RowTag({ tag }: { tag: SessionRowTag }) {
  const tone =
    tag.tone === 'alert'
      ? 'border-operator-error/40 text-operator-error'
      : tag.tone === 'warn'
      ? 'border-operator-accent/35 text-operator-accent'
      : 'border-operator-border text-operator-muted/90';
  return <span className={`rounded border px-[5px] py-[1.5px] text-[8.5px] ${tone}`}>{tag.label}</span>;
}
