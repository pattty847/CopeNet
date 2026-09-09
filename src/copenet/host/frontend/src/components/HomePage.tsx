import { useReturnBriefing } from '../runtime/adapter';
import { HomeDesk } from './home/HomeDesk';
import { ReturnBriefing } from './profile/ReturnBriefing';

/** Home is the desk. The return briefing is the exception: when the backend has one
 *  waiting it genuinely is the cold-open — "here is what happened while you were away" —
 *  so it takes the screen until dismissed, and the desk is what you land on after. */
export function HomePage() {
  const returnBriefing = useReturnBriefing();

  return (
    <div className="relative min-h-full">
      <HomeDesk />
      {returnBriefing && (
        <div className="absolute inset-0 z-20 overflow-y-auto bg-shell-bg/95 p-4 backdrop-blur-sm">
          <ReturnBriefing />
        </div>
      )}
    </div>
  );
}
