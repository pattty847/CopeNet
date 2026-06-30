// Shared Market Monitor UI primitives. Palette mirrors the approved Claude Design dashboard
// (which used CopeNet's token handoff), so these hexes match the app's dark theme exactly.

import type { CSSProperties, ReactNode } from 'react';
import type { PanelStatus, Tone } from './types';

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
}: {
  title: string;
  status: PanelStatus;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        background: MM.panel,
        border: `1px solid ${MM.border}`,
        borderRadius: 14,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: subtitle ? 4 : 12 }}>
        <span style={label}>{title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {right}
          <PreviewBadge status={status} />
        </div>
      </div>
      {subtitle && <div style={{ fontSize: 11, color: MM.dim, marginBottom: 12, fontStyle: 'italic' }}>{subtitle}</div>}
      {children}
    </div>
  );
}
