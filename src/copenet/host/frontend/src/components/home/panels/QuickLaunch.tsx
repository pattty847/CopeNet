import { ChevronRight, Zap } from 'lucide-react';
import { Card } from './Card';
import { resolveLaunchTiles, type LaunchDestination } from '../quickLaunch';

/** Quick Launch: six ways back into the work, in the operator's own order.
 *
 *  Order and selection are persisted server-side with the focus list, because the same desk
 *  is opened from the Mac and from the phone. */
export function QuickLaunch({
  savedIds,
  onLaunch,
  onCustomize,
}: {
  savedIds: string[];
  onLaunch: (destination: LaunchDestination) => void;
  onCustomize: () => void;
}) {
  const tiles = resolveLaunchTiles(savedIds);

  return (
    <Card
      title="Quick launch"
      icon={Zap}
      span={5}
      head={
        <>
          <div className="hd-card__spacer" />
          <button type="button" className="hd-link" onClick={onCustomize}>
            Customize
          </button>
        </>
      }
    >
      <div className="hd-launch-grid">
        {tiles.map((tile) => (
          <button key={tile.id} type="button" className="hd-launch" onClick={() => onLaunch(tile.destination)}>
            <span className="hd-launch__icon">
              <tile.icon size={13} />
            </span>
            <span className="hd-launch__text">
              <span className="hd-launch__label">{tile.label}</span>
              <span className="hd-launch__detail">{tile.detail}</span>
            </span>
            <ChevronRight size={12} className="hd-launch__go" />
          </button>
        ))}
      </div>
    </Card>
  );
}
