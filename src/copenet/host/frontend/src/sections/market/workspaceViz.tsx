// Small visual primitives for the research drawer.
//
// The rule these exist to enforce: a number that has a SHAPE should be drawn, not printed.
// A 52-week range is a position within a band; volume against its average is a ratio bar;
// seven horizon returns are one row of cells, not seven table rows. The baseline printed
// all of them as `key: value` and threw the shape away.

import type { ReactNode } from 'react';
import { MM } from './marketUi';
import type { Tone } from './types';

export function signedPct(value?: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/** Convert a backend fraction (0.2) into the percent the UI shows (20). Named so the
 *  conversion is visible at the call site rather than being an unexplained `* 100`. */
export function fractionAsPercent(value?: number | null): number | null {
  return value == null || !Number.isFinite(value) ? null : value * 100;
}

export function toneOf(value?: number | null): Tone {
  return value == null || !Number.isFinite(value) || value === 0 ? 'flat' : value > 0 ? 'up' : 'down';
}

export function toneHex(tone: Tone): string {
  return tone === 'up' ? MM.up : tone === 'down' ? MM.down : MM.textSoft;
}

export function compactMoney(value?: number | null, prefix = '$'): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${prefix}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(0)}K`;
  return `${sign}${prefix}${abs.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function Card({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="tw-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <span className="tw-card__title">{title}</span>
        {right}
      </div>
      {children}
    </section>
  );
}

export function KeyValue({ k, v, tone = 'flat' }: { k: string; v: string; tone?: Tone }) {
  return (
    <div className="tw-kv">
      <span className="tw-kv__k">{k}</span>
      <span className="tw-kv__v" style={{ color: toneHex(tone) }}>{v}</span>
    </div>
  );
}

/** Where the current price sits between two bounds. The mark is the point of the control;
 *  the endpoints are supporting detail and are typeset as such. */
export function RangeBand({
  low,
  high,
  value,
  lowLabel,
  highLabel,
}: {
  low?: number | null;
  high?: number | null;
  value?: number | null;
  lowLabel?: string;
  highLabel?: string;
}) {
  const usable = low != null && high != null && value != null && high > low;
  const pct = usable ? Math.min(100, Math.max(0, ((value - low) / (high - low)) * 100)) : 0;
  return (
    <div className="tw-band">
      <div className="tw-band__track">
        {usable && <span className="tw-band__mark" style={{ left: `${pct}%` }} />}
      </div>
      <div className="tw-band__ends">
        <span>{lowLabel ?? (low != null ? low.toFixed(2) : '—')}</span>
        <span>{highLabel ?? (high != null ? high.toFixed(2) : '—')}</span>
      </div>
    </div>
  );
}

/** A 0..1 magnitude with an explicit colour. Used for drawdown depth and volume vs average,
 *  where "how far along" is the whole message. */
export function Meter({ fraction, color, label, value }: { fraction: number; color: string; label: string; value: string }) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(fraction) ? fraction : 0));
  return (
    <div className="tw-meter">
      <div className="tw-kv">
        <span className="tw-kv__k">{label}</span>
        <span className="tw-kv__v" style={{ color }}>{value}</span>
      </div>
      <div className="tw-meter__track">
        <span className="tw-meter__fill" style={{ left: 0, width: `${clamped * 100}%`, background: color, opacity: 0.65 }} />
      </div>
    </div>
  );
}

export function ReturnsStrip({ cells }: { cells: { k: string; v?: number | null }[] }) {
  return (
    <div className="tw-returns">
      {cells.map((cell) => (
        <div key={cell.k} className="tw-returns__cell">
          <span className="tw-returns__k">{cell.k}</span>
          <span className="tw-returns__v" style={{ color: toneHex(toneOf(cell.v)) }}>{signedPct(cell.v)}</span>
        </div>
      ))}
    </div>
  );
}

/** Minimal sparkline. Deliberately axis-free: it carries direction and shape, and the
 *  precise value lives next to it as a number. */
export function Sparkline({ points, color, height = 28 }: { points: number[]; color: string; height?: number }) {
  const clean = points.filter((value) => Number.isFinite(value));
  if (clean.length < 2) return <div className="tw-spark" style={{ height }} />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const step = 100 / (clean.length - 1);
  const path = clean
    .map((value, index) => `${index === 0 ? 'M' : 'L'}${(index * step).toFixed(2)},${(100 - ((value - min) / span) * 100).toFixed(2)}`)
    .join(' ');
  return (
    <svg className="tw-spark" style={{ height }} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

/** Quarterly bars with the latest highlighted — the shape of a fundamental series in the
 *  width of a card. Negative periods draw below the zero line rather than being clipped. */
export function BarSeries({ values, color, height = 34 }: { values: number[]; color: string; height?: number }) {
  const clean = values.filter((value) => Number.isFinite(value));
  if (!clean.length) return <div className="tw-spark" style={{ height }} />;
  const max = Math.max(...clean, 0);
  const min = Math.min(...clean, 0);
  const span = max - min || 1;
  const zero = (max / span) * 100;
  const width = 100 / clean.length;
  return (
    <svg className="tw-spark" style={{ height }} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {clean.map((value, index) => {
        const top = value >= 0 ? ((max - value) / span) * 100 : zero;
        const barHeight = Math.max(0.8, (Math.abs(value) / span) * 100);
        return (
          <rect
            key={index}
            x={index * width + width * 0.16}
            y={top}
            width={width * 0.68}
            height={barHeight}
            fill={color}
            opacity={index === clean.length - 1 ? 1 : 0.42}
          />
        );
      })}
    </svg>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="tw-empty">{children}</p>;
}
