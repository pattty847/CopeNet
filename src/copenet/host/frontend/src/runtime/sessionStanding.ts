import type { LiveToolCall, Session, SessionStanding, SessionStandingState } from '../types/backend';

/**
 * One row of the session list, derived.
 *
 * The title is not a name — it is where the thread stands, and it changes three times
 * across a turn:
 *
 *   acting   the model's own live tool-group phrase, which the thread view already
 *            writes ("Inspecting market core and app APIs"). Nothing is asked for; it
 *            is prose we already pay for.
 *   writing  the phrase stops updating, so the title falls back to the last standing
 *            line and the row says "writing…".
 *   settled  the line the model left through session.standing, until the next turn
 *            replaces it. Falls back to the plain session title when none was left.
 *
 * Line 2 is derived in every phase and is NEVER a number on its own — it is a sentence.
 * Line 3 (the ledger) always keeps the same shape so the eye stops reading it word by
 * word. Anything new changes the icon, changes line 2, or becomes a tag; it does not
 * add a fourth line. That rule is what keeps this from turning into a stat block.
 */

export type SessionPhase = 'acting' | 'writing' | 'settled';

export interface SessionRowTag {
  label: string;
  tone: 'warn' | 'alert' | 'neutral';
}

export interface SessionRowModel {
  sessionKey: string;
  phase: SessionPhase;
  state: SessionStandingState;
  title: string;
  /** True when the title is the model's standing line rather than the stored title. */
  titleIsStanding: boolean;
  line: string;
  tags: SessionRowTag[];
  ledger: { added: number; removed: number; files: string[]; moreFiles: number } | null;
  area: string;
  offerClose: boolean;
}

/** Threads that changed nothing group together rather than scattering through the areas. */
export const NO_CHANGE_AREA = 'nothing changed';
/** Standing has not arrived for these yet. NOT the same as "nothing changed". */
export const UNKNOWN_AREA = 'loading…';

export function buildSessionRow(
  session: Session,
  standing: SessionStanding | undefined,
  liveToolCalls: LiveToolCall[],
): SessionRowModel {
  const phase = resolvePhase(session, standing, liveToolCalls);
  // No standing yet is UNKNOWN, never "idle, nothing changed". One call covers 694
  // sessions, so for a moment after load every row would otherwise claim a state it
  // has not been told — the same trap the Market panels are forbidden from falling in.
  const state: SessionStandingState = standing?.state ?? (session.inFlightRunId ? 'running' : 'unknown');
  const liveTitle = latestActivityTitle(liveToolCalls);
  const standingNote = standing?.standingNote?.trim() || '';
  const fallback = session.title?.trim() || session.key || 'New Chat';

  const title = phase === 'acting' && liveTitle ? liveTitle : standingNote || fallback;
  return {
    sessionKey: session.key,
    phase,
    state,
    title,
    titleIsStanding: title === standingNote && Boolean(standingNote),
    line: describeLine(phase, state, standing, liveToolCalls),
    tags: buildTags(standing),
    ledger: buildLedger(standing),
    area: standing ? standing.ledger.area || NO_CHANGE_AREA : UNKNOWN_AREA,
    offerClose: Boolean(standing?.standingDone) && state === 'done',
  };
}

function resolvePhase(
  session: Session,
  standing: SessionStanding | undefined,
  liveToolCalls: LiveToolCall[],
): SessionPhase {
  const live = Boolean(session.inFlightRunId) || standing?.state === 'running';
  if (!live) return 'settled';
  // Acting means a tool is still running. Once the last call resolves the model is
  // composing, and its phrase has stopped changing.
  return liveToolCalls.some((call) => call.state === 'running') ? 'acting' : 'writing';
}

function latestActivityTitle(liveToolCalls: LiveToolCall[]): string {
  for (let index = liveToolCalls.length - 1; index >= 0; index -= 1) {
    const title = liveToolCalls[index].activityTitle?.trim();
    if (title) return title;
  }
  return '';
}

/** Line 2: a sentence about the work, never a bare number. */
function describeLine(
  phase: SessionPhase,
  state: SessionStandingState,
  standing: SessionStanding | undefined,
  liveToolCalls: LiveToolCall[],
): string {
  if (phase === 'writing') return 'writing…';
  if (phase === 'acting') {
    const done = liveToolCalls.filter((call) => call.state !== 'running').length;
    return done > 0 ? `${done} ${plural(done, 'tool call')} so far` : 'starting…';
  }
  // Say nothing rather than invent a state we were not told.
  if (!standing) return '';

  const { branch, ledger, toolCalls } = standing;
  switch (state) {
    case 'blocked':
      return `blocked · approval needed for ${standing.approvalCommand}`;
    case 'unmerged': {
      const commits = `${branch.commitsAhead} ${plural(branch.commitsAhead, 'commit')}`;
      return branch.branch ? `done, not merged · ${commits} on ${branch.branch}` : `done, not merged · ${commits}`;
    }
    case 'done':
      return `done · merged${toolCalls ? ` after ${toolCalls} ${plural(toolCalls, 'tool call')}` : ''}`;
    case 'talk':
      return `talk only · ${toolCalls ? `${toolCalls} ${plural(toolCalls, 'tool call')}, ` : ''}nothing changed`;
    case 'idle':
    default:
      return standing.verificationFailed
        ? `stopped with the suite red · ${ledger.fileCount} ${plural(ledger.fileCount, 'file')} changed`
        : `idle · ${ledger.fileCount} ${plural(ledger.fileCount, 'file')} changed, nothing running`;
  }
}

function buildTags(standing: SessionStanding | undefined): SessionRowTag[] {
  if (!standing) return [];
  const tags: SessionRowTag[] = [];
  if (standing.verificationFailed) tags.push({ label: 'red', tone: 'alert' });
  if (standing.state === 'unmerged') tags.push({ label: 'unmerged', tone: 'warn' });
  // The branch quietly holding two features: name the file, not the count.
  const shared = standing.sharesWith[0];
  if (shared) tags.push({ label: `shares ${shared.path}`, tone: 'alert' });
  return tags;
}

function buildLedger(standing: SessionStanding | undefined): SessionRowModel['ledger'] {
  if (!standing || standing.ledger.fileCount === 0) return null;
  const files = standing.ledger.recentFiles.slice(0, 2);
  return {
    added: standing.ledger.linesAdded,
    removed: standing.ledger.linesRemoved,
    files,
    moreFiles: Math.max(0, standing.ledger.fileCount - files.length),
  };
}

function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}

/** Group rows by the area their work lives in, most recent activity first inside each. */
export function groupRowsByArea(rows: SessionRowModel[]): { area: string; rows: SessionRowModel[] }[] {
  const groups = new Map<string, SessionRowModel[]>();
  for (const row of rows) {
    const bucket = groups.get(row.area);
    if (bucket) bucket.push(row);
    else groups.set(row.area, [row]);
  }
  return [...groups.entries()]
    .map(([area, areaRows]) => ({ area, rows: areaRows }))
    // Threads that changed nothing sink to the bottom; everything else keeps list order.
    .sort((left, right) => Number(left.area === NO_CHANGE_AREA) - Number(right.area === NO_CHANGE_AREA));
}

/** The filter chips over the list: what the operator is hunting for, with live counts. */
export type SessionFilterId = 'all' | 'live' | 'unmerged' | 'blocked' | 'idle' | 'pinned' | 'archived' | 'unknown';

export interface SessionFilter {
  id: SessionFilterId;
  label: string;
  count: number;
}

// Pinned and archived are not states a thread is IN — they are the operator's own
// shelves. They ride the same chip row because to the eye they are the same question
// ("show me this slice"), which is what let the header drop from five bands to three.
export const SHELF_FILTERS: ReadonlySet<SessionFilterId> = new Set<SessionFilterId>(['pinned', 'archived']);

const FILTER_MATCHES: Record<SessionFilterId, (row: SessionRowModel) => boolean> = {
  all: () => true,
  live: (row) => row.state === 'running',
  unmerged: (row) => row.state === 'unmerged',
  blocked: (row) => row.state === 'blocked',
  // Work left in the middle of something: the threads you forgot were open.
  idle: (row) => row.state === 'idle',
  pinned: () => true,
  archived: () => true,
  unknown: (row) => row.state === 'unknown',
};

export function matchesFilter(row: SessionRowModel, filter: SessionFilterId): boolean {
  return FILTER_MATCHES[filter](row);
}

/** Chips for every filter that currently matches something, 'all' always first. */
export function buildFilters(
  rows: SessionRowModel[],
  shelves: { pinned: number; archived: number },
): SessionFilter[] {
  const labels: Record<SessionFilterId, string> = {
    all: 'All',
    live: 'Live',
    unmerged: 'Unmerged',
    blocked: 'Blocked',
    idle: 'Idle',
    pinned: 'Pinned',
    archived: 'Archived',
    // Never offered as a chip: "we have not loaded yet" is not a slice to filter to.
    unknown: '',
  };
  return (Object.keys(labels) as SessionFilterId[])
    .map((id) => ({
      id,
      label: labels[id],
      count: id === 'pinned' ? shelves.pinned : id === 'archived' ? shelves.archived : rows.filter((row) => matchesFilter(row, id)).length,
    }))
    .filter((chip) => chip.id !== 'unknown' && (chip.id === 'all' || chip.count > 0));
}
