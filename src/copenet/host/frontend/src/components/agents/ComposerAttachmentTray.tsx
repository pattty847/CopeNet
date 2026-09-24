import { FileText, Loader2, X } from 'lucide-react';
import type { ChatAttachment } from '../../types/backend';

/** A composer-local attachment: an image upload in flight (object-URL preview +
 *  status) or a ready text attachment such as a discussed media transcript. */
export interface PendingAttachment {
  localId: string;
  filename: string;
  previewUrl: string;
  status: 'uploading' | 'ready' | 'error';
  attachment: ChatAttachment | null;
  error?: string;
}

export function isTextAttachment(attachment: ChatAttachment | null | undefined): boolean {
  return Boolean(attachment?.mimeType.startsWith('text/'));
}

/** Learning-oriented openers offered once a transcript is attached. Each fills the
 *  composer (it does not send) so the operator can still pick the runtime first. */
export const DISCUSS_PROMPTS: { label: string; prompt: string }[] = [
  {
    label: 'Explain it',
    prompt:
      'Explain what this video is saying in plain language. Lead with the core idea in two sentences, then the supporting points, and define any jargon.',
  },
  {
    label: 'Check the claims',
    prompt:
      'List the factual claims made in this video. For each, say how well it holds up (well supported / contested / wrong / unverifiable) and why. Use web search where you can, and flag anything said confidently that is actually shaky.',
  },
  {
    label: 'Steelman + push back',
    prompt:
      "Give the strongest version of the speaker's argument, then the best counterarguments a knowledgeable skeptic would raise.",
  },
  {
    label: 'Go deeper',
    prompt:
      'I want to learn more about this topic. Give me the key concepts to understand next, the people or sources worth reading, and three questions worth exploring.',
  },
  {
    label: 'Takeaways',
    prompt: 'Summarize the key takeaways as a short bulleted list I could save as notes.',
  },
];

export function ComposerAttachmentTray({
  attachments,
  onRemove,
}: {
  attachments: PendingAttachment[];
  onRemove: (localId: string) => void;
}) {
  if (attachments.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 border-b border-operator-border/60 px-3 py-2">
      {attachments.map((item) =>
        isTextAttachment(item.attachment) ? (
          <div
            key={item.localId}
            className="group flex h-9 max-w-full items-center gap-2 rounded-lg border border-operator-border bg-operator-bg pl-2.5 pr-1 text-xs text-operator-text"
            title={item.filename}
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-operator-accent" />
            <span className="truncate">{item.filename}</span>
            <button
              type="button"
              onClick={() => onRemove(item.localId)}
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-operator-muted transition-colors hover:text-operator-error"
              title="Remove"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div
            key={item.localId}
            className="group relative h-16 w-16 overflow-hidden rounded-lg border border-operator-border bg-operator-bg"
            title={item.error || item.filename}
          >
            <img src={item.previewUrl} alt={item.filename} className="h-full w-full object-cover" />
            {item.status === 'uploading' && (
              <div className="absolute inset-0 flex items-center justify-center bg-operator-bg/60">
                <Loader2 className="h-4 w-4 animate-spin text-operator-accent" />
              </div>
            )}
            {item.status === 'error' && (
              <div className="absolute inset-0 flex items-center justify-center bg-operator-error/30 text-[9px] font-semibold text-operator-error">
                Failed
              </div>
            )}
            <button
              type="button"
              onClick={() => onRemove(item.localId)}
              className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-operator-bg/80 text-operator-muted opacity-0 transition-opacity hover:text-operator-error group-hover:opacity-100"
              title="Remove"
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </div>
        ),
      )}
    </div>
  );
}

export function DiscussPromptChips({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 px-3 pt-2">
      {DISCUSS_PROMPTS.map((item) => (
        <button
          key={item.label}
          type="button"
          onClick={() => onPick(item.prompt)}
          title={item.prompt}
          className="rounded-full border border-operator-border bg-operator-bg px-3 py-1 text-xs font-medium text-operator-text transition-colors hover:border-operator-accent/50 hover:text-operator-accent"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
