// Cumulative P&L since the account opened — a step curve of closed P&L over time, with today's
// open positions added at the tail so the last point equals the panel headline. Realized-only in
// between: marking past holdings to market would need a price history for every symbol ever held,
// including delisted ones, so the curve shows facts rather than a fabricated smooth line.

import { useState } from 'react';

import type { CurvePoint } from '../../lib/wsMarketRpc';
import { MM, mono } from './marketUi';

const WIDTH = 760;
const HEIGHT = 200;
const PAD = { left: 58, right: 16, top: 16, bottom: 26 };

function money(value: number): string {
  const abs = Math.abs(value);
  const compact = abs >= 1000 ? `${(abs / 1000).toFixed(1)}k` : abs.toFixed(0);
  return `${value < 0 ? '−' : ''}$${compact}`;
}

function yearLabel(iso: string): string {
  return iso.slice(0, 4);
}

export function PnlCurve({ points }: { points: CurvePoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;

  const values = points.map((point) => point.total);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = Math.max(1, high - low);
  // Spaced by date, not by event index: closing trades cluster in bursts, and index spacing would
  // stretch a busy month to look like a busy year.
  const t = (iso: string) => new Date(`${iso}T00:00:00Z`).getTime();
  const start = t(points[0].date);
  const elapsed = Math.max(1, t(points[points.length - 1].date) - start);
  const x = (index: number) =>
    PAD.left + ((t(points[index].date) - start) / elapsed) * (WIDTH - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + ((high - value) / span) * (HEIGHT - PAD.top - PAD.bottom);

  const line = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index)} ${y(point.total)}`).join(' ');
  const zero = y(0);
  const area = `${line} L ${x(points.length - 1)} ${zero} L ${x(0)} ${zero} Z`;
  const last = points[points.length - 1];
  const positive = last.total >= 0;
  const stroke = positive ? MM.up : MM.down;

  // One label per distinct year keeps a six-year axis readable without crowding.
  const yearTicks = points.reduce<{ index: number; year: string }[]>((acc, point, index) => {
    const year = yearLabel(point.date);
    if (!acc.length || acc[acc.length - 1].year !== year) acc.push({ index, year });
    return acc;
  }, []);
  const active = hover == null ? null : points[hover];

  return (
    <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Cumulative profit and loss from ${points[0].date} to ${last.date}, ending at ${money(last.total)}`}
        style={{ width: '100%', minWidth: 420, height: 'auto', display: 'block' }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="pnl-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={positive ? 0.22 : 0.02} />
            <stop offset="100%" stopColor={stroke} stopOpacity={positive ? 0.02 : 0.22} />
          </linearGradient>
        </defs>

        <line x1={PAD.left} y1={zero} x2={WIDTH - PAD.right} y2={zero} stroke="rgba(254,252,244,.18)" strokeDasharray="3 4" />
        <text x={PAD.left - 8} y={zero + 4} textAnchor="end" fill={MM.dim} fontFamily={mono} fontSize="9">$0</text>
        {[high, low].map((tick) => (
          <text key={tick} x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fill={MM.dimmer} fontFamily={mono} fontSize="9">
            {money(tick)}
          </text>
        ))}

        <path d={area} fill="url(#pnl-area)" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
        <circle cx={x(points.length - 1)} cy={y(last.total)} r="3.5" fill={MM.panel} stroke={stroke} strokeWidth="2" />

        {yearTicks.map((tick) => (
          <text key={tick.year} x={x(tick.index)} y={HEIGHT - 8} textAnchor="middle" fill={MM.dimmer} fontFamily={mono} fontSize="9">
            {tick.year}
          </text>
        ))}

        {active && (
          <g>
            <line x1={x(hover as number)} y1={PAD.top} x2={x(hover as number)} y2={HEIGHT - PAD.bottom} stroke="rgba(254,252,244,.18)" />
            <circle cx={x(hover as number)} cy={y(active.total)} r="3.5" fill={MM.panel} stroke={stroke} strokeWidth="2" />
          </g>
        )}
        {points.map((point, index) => (
          <rect
            key={point.date}
            x={index ? (x(index) + x(index - 1)) / 2 : PAD.left}
            y={PAD.top}
            width={Math.max(2, (index < points.length - 1 ? (x(index + 1) + x(index)) / 2 : WIDTH - PAD.right) - (index ? (x(index) + x(index - 1)) / 2 : PAD.left))}
            height={HEIGHT - PAD.top - PAD.bottom}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>
      <div style={{ height: 16, fontFamily: mono, fontSize: 10, color: MM.dim, textAlign: 'right' }}>
        {active ? `${active.date} · ${money(active.total)}` : `${points.length} closing events since ${points[0].date}`}
      </div>
    </div>
  );
}
