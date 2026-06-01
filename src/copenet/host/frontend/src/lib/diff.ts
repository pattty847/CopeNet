// Unified-diff parsing for the inline diff renderer.
//
// Turns the unified-diff string the backend emits (files.write / files.edit)
// into rows carrying real old/new line numbers parsed from the @@ hunk headers,
// so the UI can render GitHub-style gutters — the "mini-IDE, never leave to
// verify" feel applied to the surface the operator already loves.

export type DiffRowKind = 'add' | 'del' | 'context' | 'hunk';

export interface DiffRow {
  kind: DiffRowKind;
  /** Old-file line number. null for added lines and hunk headers. */
  oldNo: number | null;
  /** New-file line number. null for removed lines and hunk headers. */
  newNo: number | null;
  /** Line content with the leading +/-/space marker stripped. */
  text: string;
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/**
 * Parse a unified diff into renderable rows with line numbers.
 * Skips the ---/+++ file-header lines (the path is shown in the block header).
 */
export function parseUnifiedDiff(diff: string): DiffRow[] {
  const rows: DiffRow[] = [];
  if (!diff) return rows;
  let oldNo = 0;
  let newNo = 0;
  for (const line of diff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---')) continue;
    if (line.startsWith('@@')) {
      const match = HUNK_RE.exec(line);
      if (match) {
        oldNo = Number(match[1]);
        newNo = Number(match[2]);
      }
      rows.push({ kind: 'hunk', oldNo: null, newNo: null, text: line });
      continue;
    }
    if (line.startsWith('+')) {
      rows.push({ kind: 'add', oldNo: null, newNo, text: line.slice(1) });
      newNo += 1;
    } else if (line.startsWith('-')) {
      rows.push({ kind: 'del', oldNo, newNo: null, text: line.slice(1) });
      oldNo += 1;
    } else {
      // Context line (leading space) or a blank trailing line.
      const text = line.startsWith(' ') ? line.slice(1) : line;
      rows.push({ kind: 'context', oldNo, newNo, text });
      oldNo += 1;
      newNo += 1;
    }
  }
  return rows;
}

/** Widest line-number string across all rows — used to size the gutter. */
export function diffGutterWidth(rows: DiffRow[]): number {
  let max = 1;
  for (const row of rows) {
    if (row.oldNo != null) max = Math.max(max, String(row.oldNo).length);
    if (row.newNo != null) max = Math.max(max, String(row.newNo).length);
  }
  return max;
}
