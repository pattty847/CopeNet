import { Check } from 'lucide-react';
import { LAUNCH_SLOTS, LAUNCH_TILES, resolveLaunchTiles } from '../quickLaunch';

/** Choosing which six tiles Quick Launch shows, and in what order.
 *
 *  Order is selection order, so the operator arranges by picking rather than dragging — a
 *  drag surface for six items is more machinery than the choice deserves. Saving an empty
 *  selection is refused, because an empty stored list is how "use the defaults" is spelled. */
export function LaunchPicker({
  selected,
  onToggle,
  onClose,
}: {
  selected: string[];
  onToggle: (id: string) => void;
  onClose: () => void;
}) {
  const active = resolveLaunchTiles(selected).map((tile) => tile.id);

  return (
    <div className="hd-tool-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
      {LAUNCH_TILES.map((tile) => {
        const index = active.indexOf(tile.id);
        const chosen = index >= 0;
        const full = active.length >= LAUNCH_SLOTS && !chosen;
        return (
          <button
            key={tile.id}
            type="button"
            className="hd-tool"
            disabled={full}
            style={full ? { opacity: 0.35, cursor: 'not-allowed' } : undefined}
            onClick={() => onToggle(tile.id)}
            title={full ? `Deselect one first — Quick Launch holds ${LAUNCH_SLOTS}` : undefined}
          >
            <span
              className="hd-tool__icon"
              style={chosen ? { borderColor: 'var(--mkt-accent-line)', background: 'var(--mkt-accent-soft)' } : undefined}
            >
              {chosen ? <Check size={12} /> : <tile.icon size={12} />}
            </span>
            <span className="hd-tool__text">
              <span className="hd-tool__label">
                {tile.label} {tile.detail}
              </span>
              <span className="hd-tool__detail">{chosen ? `slot ${index + 1}` : 'not shown'}</span>
            </span>
          </button>
        );
      })}
      <button
        type="button"
        className="hd-tool"
        style={{ gridColumn: 'span 2', justifyContent: 'center' }}
        onClick={onClose}
      >
        <span className="hd-tool__label">Done</span>
      </button>
    </div>
  );
}
