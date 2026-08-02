/**
 * The run-internals view mounts on two surfaces with two token sets: the Agents
 * thread uses `operator-*`, the Observability workspace uses `shell-*`. They have
 * the same roles and the same accent, but different border alphas and muted
 * values, so a component hard-coded to one looks subtly wrong in the other.
 *
 * An explicit table beats interpolating class names: Tailwind can only see class
 * strings it can find in the source, so `text-${palette}-muted` would compile to
 * nothing.
 */

export type InternalsPalette = 'operator' | 'shell';

export interface PaletteClasses {
  text: string;
  muted: string;
  mutedSoft: string;
  border: string;
  borderSoft: string;
  panel: string;
  surface: string;
  accent: string;
  success: string;
  error: string;
  hover: string;
  hoverText: string;
}

const OPERATOR: PaletteClasses = {
  text: 'text-operator-text',
  muted: 'text-operator-muted',
  mutedSoft: 'text-operator-muted/70',
  border: 'border-operator-border',
  borderSoft: 'border-operator-border/45',
  panel: 'bg-operator-panel/25',
  surface: 'bg-operator-bg/45',
  accent: 'text-operator-accent',
  success: 'text-operator-success',
  error: 'text-operator-error',
  hover: 'hover:bg-operator-panel/30',
  hoverText: 'hover:text-operator-text',
};

const SHELL: PaletteClasses = {
  text: 'text-shell-text',
  muted: 'text-shell-muted',
  mutedSoft: 'text-shell-muted/70',
  border: 'border-shell-border',
  borderSoft: 'border-shell-border/60',
  panel: 'bg-shell-panel-strong/40',
  surface: 'bg-shell-bg',
  accent: 'text-shell-accent',
  success: 'text-shell-success',
  error: 'text-shell-error',
  hover: 'hover:bg-shell-bg/70',
  hoverText: 'hover:text-shell-text',
};

export function paletteClasses(palette: InternalsPalette): PaletteClasses {
  return palette === 'shell' ? SHELL : OPERATOR;
}

/** Amber is the warn tone in both palettes; neither token set defines one. */
export function toneClass(tone: 'neutral' | 'warn' | 'error', classes: PaletteClasses): string {
  if (tone === 'error') return classes.error;
  if (tone === 'warn') return 'text-amber-400';
  return classes.muted;
}
