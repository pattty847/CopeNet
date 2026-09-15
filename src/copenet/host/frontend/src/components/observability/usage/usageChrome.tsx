import type { ReactNode } from 'react';
import { TOKEN_KIND_LABELS, type TokenKind } from '../../../runtime/usageModel';

/** Shared chart furniture for the Usage view: the panel frame, the series palette,
 *  and the legend. Everything here is presentation only — the numbers are derived
 *  in `runtime/usageModel.ts`.
 *
 *  The two palettes are SELECTED per theme, not flipped: each was validated
 *  against its own surface (light #ffffff, dark #080809) for the lightness band,
 *  chroma floor, colourblind separation and contrast. Do not swap one set into the
 *  other theme — the dark steps are deliberately deeper than the app's UI accent,
 *  which is too light to sit in a dark chart's lightness band. */
export const SERIES_VARS: Record<TokenKind, string> = {
  output: 'var(--usage-series-output)',
  freshInput: 'var(--usage-series-fresh)',
  cacheRead: 'var(--usage-series-cache)',
};

export const SERIES_ORDER: TokenKind[] = ['output', 'freshInput', 'cacheRead'];

export function UsagePanel({
  title,
  subtitle,
  children,
  actions,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-shell-border bg-shell-panel p-3">
      <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.14em] text-shell-text">{title}</h2>
        {subtitle && <p className="text-[10.5px] text-shell-muted">{subtitle}</p>}
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

/** Identity is never colour alone: each key shows its swatch beside its name. */
export function SeriesLegend({ kinds = SERIES_ORDER }: { kinds?: TokenKind[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {kinds.map((kind) => (
        <li key={kind} className="flex items-center gap-1.5 text-[10px] text-shell-muted">
          <span
            aria-hidden
            className="h-2 w-2 rounded-[2px]"
            style={{ background: SERIES_VARS[kind] }}
          />
          {TOKEN_KIND_LABELS[kind]}
        </li>
      ))}
    </ul>
  );
}

/** The one place the view says "nothing here", so an empty section never looks
 *  like a section that failed to load. */
export function UsageEmpty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-[11px] text-shell-muted">{children}</p>;
}

export function StatRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-shell-border py-1.5 last:border-b-0">
      <span className="text-[11px] text-shell-muted">{label}</span>
      <span className="font-mono text-[11px] text-shell-text" title={hint}>
        {value}
      </span>
    </div>
  );
}
