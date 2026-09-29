import { BookOpen } from 'lucide-react';
import { MemorySurface } from '../profile/MemorySurface';
import { UserNotesSurface } from '../profile/UserNotesSurface';
import { ChromeDrawer } from './ChromeDrawer';

/** What CopeNet remembers about the operator, and what a model has proposed adding. Nothing
 *  a model proposes becomes durable until it is approved here. */
export function NotebookPanel({ onClose }: { onClose: () => void }) {
  return (
    <ChromeDrawer eyebrow="What CopeNet remembers" title="Notebook" icon={BookOpen} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <MemorySurface />
        <UserNotesSurface />
      </div>
    </ChromeDrawer>
  );
}

/** The Notebook badge: model proposals waiting for a decision. */
export function pendingNotebookCount(memoryDrafts: unknown[], userNoteDrafts: unknown[]): number {
  return memoryDrafts.length + userNoteDrafts.length;
}
