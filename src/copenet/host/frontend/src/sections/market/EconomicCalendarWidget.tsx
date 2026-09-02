import { useMemo, useState } from 'react';
import { MM, mono } from './marketUi';
import type { EconomicCalendarEvent, EconomicCalendarPayload } from './types';

function localDay(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('sv-SE');
}

function dayLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const key = parsed.toLocaleDateString('sv-SE');
  if (key === new Date().toLocaleDateString('sv-SE')) return 'Today';
  if (key === new Date(Date.now() + 86_400_000).toLocaleDateString('sv-SE')) return 'Tomorrow';
  return parsed.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function timeLabel(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Time TBD' : parsed.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function EventRow({ event }: { event: EconomicCalendarEvent }) {
  const figure = event.actual
    ? { text: `${event.actual} actual`, color: MM.text }
    : event.forecast
      ? { text: `${event.forecast} expected`, color: MM.muted }
      : event.previous
        ? { text: `${event.previous} previous`, color: MM.dim }
        : null;
  const name = event.sourceUrl ? (
    <a href={event.sourceUrl} target="_blank" rel="noreferrer" style={{ color: MM.textSoft, textDecoration: 'none' }}>{event.event}</a>
  ) : event.event;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '68px minmax(130px, 1fr) auto', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: `1px solid rgba(254,252,244,.05)` }}>
      <span style={{ fontFamily: mono, fontSize: 10, color: MM.dim, fontVariantNumeric: 'tabular-nums' }}>{timeLabel(event.date)}</span>
      <span style={{ minWidth: 0, display: 'inline-flex', alignItems: 'center', gap: 7, color: MM.textSoft, fontSize: 11.5, lineHeight: 1.35 }}>
        <span aria-label={event.importance === 3 ? 'High impact' : 'Medium impact'} title={event.importance === 3 ? 'High impact' : 'Medium impact'} style={{ width: 6, height: 6, borderRadius: '50%', flex: '0 0 auto', background: event.importance === 3 ? MM.down : MM.accent, boxShadow: event.importance === 3 ? `0 0 0 3px rgba(217,109,95,.12)` : 'none' }} />
        {name}
      </span>
      {figure && <span style={{ fontFamily: mono, fontSize: 9.5, color: figure.color, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{figure.text}</span>}
    </div>
  );
}

export function EconomicCalendarWidget({ calendar, loading, refreshing, error, onRefresh }: {
  calendar: EconomicCalendarPayload | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const upcoming = useMemo(
    () => (calendar?.events ?? []).filter((event) => new Date(event.date).getTime() >= Date.now() - 60_000),
    [calendar],
  );
  const visible = expanded ? upcoming : upcoming.slice(0, 3);
  const groups = visible.reduce<Record<string, EconomicCalendarEvent[]>>((result, event) => {
    (result[localDay(event.date)] ??= []).push(event);
    return result;
  }, {});

  if (loading && !calendar) return <span style={{ color: MM.dim, fontSize: 11.5, fontStyle: 'italic' }}>Loading the next seven days…</span>;
  if (calendar && !calendar.configured && calendar.events.length === 0) {
    return <span style={{ color: MM.dim, fontSize: 11.5 }}>Calendar ready · add <span style={{ fontFamily: mono, color: MM.accent }}>TRADING_ECONOMICS_API_KEY</span> to load releases.</span>;
  }

  return (
    <div style={{ minWidth: 0 }}>
      {calendar?.stale && <div style={{ color: MM.accent, fontSize: 10, marginBottom: 4 }}>Cached calendar · refresh unavailable</div>}
      {error && !calendar?.events.length && <div role="status" style={{ color: MM.down, fontSize: 10.5, marginBottom: 5 }}>{error}</div>}
      {visible.length === 0 ? (
        <span style={{ color: MM.dim, fontSize: 11.5, fontStyle: 'italic' }}>No medium- or high-impact US releases in the next seven days.</span>
      ) : Object.entries(groups).map(([key, events]) => (
        <div key={key}>
          <div style={{ color: MM.dimmer, font: '600 8.5px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase', marginTop: 3 }}>{dayLabel(events[0].date)}</div>
          {events.map((event) => <EventRow key={event.id} event={event} />)}
        </div>
      ))}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: visible.length ? 6 : 3 }}>
        {upcoming.length > 3 && <button type="button" onClick={() => setExpanded((value) => !value)} style={{ border: 0, padding: 0, background: 'transparent', color: MM.accent, cursor: 'pointer', font: '600 10px var(--mkt-sans)' }}>{expanded ? 'Show next 3' : `Show all ${upcoming.length}`}</button>}
        <button type="button" onClick={onRefresh} disabled={refreshing} style={{ border: 0, padding: 0, background: 'transparent', color: MM.dim, cursor: refreshing ? 'default' : 'pointer', font: '600 10px var(--mkt-sans)', opacity: refreshing ? 0.55 : 1 }}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>
        {calendar?.sourceUrl && <a href={calendar.sourceUrl} target="_blank" rel="noreferrer" style={{ marginLeft: 'auto', color: MM.dim, font: '500 9px var(--mkt-sans)', textDecoration: 'none' }}>Trading Economics ↗</a>}
      </div>
    </div>
  );
}
