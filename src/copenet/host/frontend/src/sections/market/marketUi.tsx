// Shared Market Monitor UI primitives. Palette mirrors the approved Claude Design dashboard
// (which used CopeNet's token handoff), so these hexes match the app's dark theme exactly.

import type { CSSProperties, ReactNode } from 'react';
import type { EvidenceItem, PanelStatus, Tone } from './types';

export const MM = {
  bg: '#000103',
  panel: '#080809',
  panelInset: '#0d0d0e',
  text: '#fefcf4',
  textSoft: '#cdc7bc',
  muted: '#a29b90',
  faint: '#8c857a',
  dim: '#6f685e',
  dimmer: '#4a443c',
  border: 'rgba(254,252,244,.06)',
  borderHi: 'rgba(251,148,35,.22)',
  accent: '#fb9423',
  accentSoft: 'rgba(251,148,35,.12)',
  up: '#69c589',
  down: '#d96d5f',
} as const;

export function toneColor(tone: Tone): string {
  return tone === 'up' ? MM.up : tone === 'down' ? MM.down : MM.muted;
}

export const label: CSSProperties = {
  margin: 0,
  font: '600 9.5px Inter',
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: MM.muted,
};

export const mono = "'JetBrains Mono', monospace";

/** Tone from a signed value string ("+4.3%" green, "-8.4%" red) — display accents only. */
export function valueTone(value: string): string {
  if (value.startsWith('+')) return MM.up;
  if (value.startsWith('-')) return MM.down;
  return MM.dim;
}

/** ▲/▼ tone glyph for an evidence row (insider buy green / sell red); nothing when flat. */
export function EvidenceToneGlyph({ tone }: { tone: Tone }) {
  if (tone === 'flat') return null;
  return (
    <span style={{ flex: '0 0 auto', fontFamily: mono, fontSize: 10, color: toneColor(tone) }}>
      {tone === 'up' ? '▲' : '▼'}
    </span>
  );
}

/** Compact evidence date from a unix-seconds stamp, e.g. "Jun 8". Empty when absent. */
export function evidenceDate(t?: number): string {
  if (!t || !Number.isFinite(t)) return '';
  const parsed = new Date(t * 1000);
  if (Number.isNaN(parsed.getTime())) return '';
  const sameYear = parsed.getUTCFullYear() === new Date().getUTCFullYear();
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }), timeZone: 'UTC' });
}

export function evidenceTypeBg(t: EvidenceItem['type']): string {
  if (t === 'Insider') return MM.accentSoft;
  if (t === 'Form 144') return 'rgba(217,109,95,.12)';
  return 'rgba(254,252,244,.06)';
}

export function evidenceTypeColor(t: EvidenceItem['type']): string {
  if (t === 'Insider') return MM.accent;
  if (t === 'Form 144') return MM.down;
  return MM.textSoft;
}

/** Anomaly badge for an evidence row — cluster buys and high-signal 8-Ks. */
export function EvidenceFlagBadge({ flag }: { flag?: EvidenceItem['flag'] }) {
  if (!flag) return null;
  const cluster = flag === 'cluster';
  return (
    <span
      style={{
        flex: '0 0 auto',
        borderRadius: 999,
        padding: '2px 7px',
        font: '700 8px Inter',
        letterSpacing: '.1em',
        textTransform: 'uppercase',
        background: cluster ? 'rgba(105,197,137,.14)' : 'rgba(90,143,199,.14)',
        color: cluster ? MM.up : '#8fb8e8',
        border: `1px solid ${cluster ? 'rgba(105,197,137,.35)' : 'rgba(90,143,199,.35)'}`,
      }}
    >
      {cluster ? 'cluster' : 'high signal'}
    </span>
  );
}

/** Tiny honest badge — only shows when a panel isn't live yet. */
export function PreviewBadge({ status }: { status: PanelStatus }) {
  if (status === 'live') return null;
  const text = status === 'error' ? 'Unavailable' : status === 'stale' ? 'Stale' : 'Preview · illustrative';
  const color = status === 'error' ? MM.down : MM.dim;
  return (
    <span
      style={{
        borderRadius: 999,
        border: `1px solid ${MM.border}`,
        padding: '2px 8px',
        font: '600 8px Inter',
        letterSpacing: '.12em',
        textTransform: 'uppercase',
        color,
      }}
    >
      {text}
    </span>
  );
}

export function PanelCard({
  title,
  status,
  subtitle,
  right,
  children,
  style,
  headerLayout = 'default',
}: {
  title: string;
  status: PanelStatus;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
  headerLayout?: 'default' | 'mobile-toolbar' | 'chart-toolbar';
}) {
  return (
    <div
      className="market-panel-card"
      style={{
        background: MM.panel,
        border: `1px solid ${MM.border}`,
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      <div
        className={`market-panel-drag-handle ${headerLayout === 'mobile-toolbar' ? 'market-panel-header--mobile-toolbar' : ''} ${headerLayout === 'chart-toolbar' ? 'market-panel-header--chart-toolbar' : ''}`}
        style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: subtitle ? 4 : 12 }}
      >
        <span className={headerLayout === 'chart-toolbar' ? 'market-panel-header__chart-title' : undefined} style={label}>{title}</span>
        <div className="market-panel-header__actions" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {right}
          <PreviewBadge status={status} />
        </div>
      </div>
      {subtitle && <div style={{ fontSize: 11, color: MM.dim, marginBottom: 12, fontStyle: 'italic' }}>{subtitle}</div>}
      {children}
    </div>
  );
}
