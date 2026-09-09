import { useReturnBriefing } from '../runtime/adapter';
import { HomeCockpit } from './home/HomeCockpit';
import { ReturnBriefing } from './profile/ReturnBriefing';

/** Home is one screen: the cockpit fills the frame and never scrolls.
 *
 *  The return briefing is the exception. When the backend has one waiting it is genuinely
 *  the cold-open — "here is what happened while you were away" — so it takes the screen
 *  until dismissed, and the cockpit is what you land on after. It is an overlay rather than
 *  a row because the cockpit's whole point is that nothing on it scrolls out of view. */
export function HomePage() {
  const returnBriefing = useReturnBriefing();

  return (
    <div className="relative h-full min-h-0">
      <HomeCockpit />
      {returnBriefing && (
        <div className="absolute inset-0 z-20 overflow-y-auto bg-shell-bg/95 p-4 backdrop-blur-sm">
          <ReturnBriefing />
        </div>
      )}
    </div>
  );
}
