import type { UsageTile } from '../../../runtime/usageModel';

const TONE_CLASS: Record<UsageTile['tone'], string> = {
  default: 'text-shell-text',
  // A muted tile's value is UNKNOWN, not low. The dash plus the grey is what
  // stops "—" from reading as a measured zero.
  muted: 'text-shell-muted',
  warning: 'text-shell-error',
};

export function UsageTiles({ tiles }: { tiles: UsageTile[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.id} className="rounded-xl border border-shell-border bg-shell-panel px-3 py-2.5">
          <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-shell-muted">{tile.label}</p>
          <p className={`mt-1 font-mono text-[17px] leading-none ${TONE_CLASS[tile.tone]}`}>{tile.value}</p>
          <p className="mt-1.5 text-[10px] leading-snug text-shell-muted">{tile.detail}</p>
        </div>
      ))}
    </div>
  );
}
