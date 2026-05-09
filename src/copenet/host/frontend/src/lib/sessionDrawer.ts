import type { Session } from '../types/backend';

export interface SessionDrawerRecentGroups {
  today: Session[];
  thisWeek: Session[];
  earlier: Session[];
}

export interface SessionDrawerSections {
  pinned: Session[];
  recent: SessionDrawerRecentGroups;
  archived: Session[];
}

export interface OrganizeSessionDrawerSectionsOptions {
  sessions: Session[];
  pinnedSessionKeys: string[];
  query: string;
  now?: Date;
}

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfWeek(date: Date) {
  const day = date.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const weekStart = startOfDay(date);
  weekStart.setDate(weekStart.getDate() - diff);
  return weekStart;
}

function sortByRecent(sessions: Session[]) {
  return [...sessions].sort((a, b) => String(b.updatedAt || b.createdAt || '').localeCompare(String(a.updatedAt || a.createdAt || '')));
}

function matchesQuery(session: Session, query: string) {
  if (!query.trim()) return true;
  const normalized = query.trim().toLowerCase();
  return [session.title || '', session.key, session.provider || '', session.model || '']
    .join(' ')
    .toLowerCase()
    .includes(normalized);
}

export function organizeSessionDrawerSections({
  sessions,
  pinnedSessionKeys,
  query,
  now = new Date(),
}: OrganizeSessionDrawerSectionsOptions): SessionDrawerSections {
  const pinnedSet = new Set(pinnedSessionKeys);
  const todayStart = startOfDay(now).getTime();
  const weekStart = startOfWeek(now).getTime();
  const activeSessions = sessions.filter((session) => !session.archived && matchesQuery(session, query));
  const archivedSessions = sessions.filter((session) => session.archived && matchesQuery(session, query));
  const pinned = sortByRecent(activeSessions.filter((session) => pinnedSet.has(session.key)));
  const remaining = sortByRecent(activeSessions.filter((session) => !pinnedSet.has(session.key)));

  const recent: SessionDrawerRecentGroups = {
    today: [],
    thisWeek: [],
    earlier: [],
  };

  for (const session of remaining) {
    const sessionTime = new Date(session.updatedAt || session.createdAt || now.toISOString()).getTime();
    if (sessionTime >= todayStart) {
      recent.today.push(session);
      continue;
    }
    if (sessionTime >= weekStart) {
      recent.thisWeek.push(session);
      continue;
    }
    recent.earlier.push(session);
  }

  return {
    pinned,
    recent,
    archived: sortByRecent(archivedSessions),
  };
}
