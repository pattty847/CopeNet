import React, { useEffect, useState } from 'react';
import { Message, ChatAttachment } from '../types/backend';
import { fetchChatAttachmentObjectUrl } from '../lib/appApi';
import { ToolTraceCard } from './ToolTraceCard';
import { TurnTrail } from './transcript/TurnTrail';
import { Copy, Check } from 'lucide-react';
import { Spinner } from './Spinner';
import { ChatMarkdown } from './ChatMarkdown';
import { formatMessageForClipboard } from '../lib/chatExport';
import { copyTextToClipboard } from '../lib/clipboard';
import { useAppStore } from '../store/useAppStore';
import { ToolGlyph, toolDisplayName } from './ToolPromptPalette';

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// One attached image. Uses the optimistic previewUrl (object URL set at send
// time) when present; otherwise lazily fetches the persisted bytes with auth.
function AttachmentImage({ attachment }: { attachment: ChatAttachment }) {
  const [src, setSrc] = useState<string | null>(attachment.previewUrl || null);

  useEffect(() => {
    if (attachment.previewUrl) {
      setSrc(attachment.previewUrl);
      return;
    }
    let revoked: string | null = null;
    let cancelled = false;
    fetchChatAttachmentObjectUrl(attachment.attachmentId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        revoked = url;
        setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setSrc(null);
      });
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [attachment.attachmentId, attachment.previewUrl]);

  if (!src) {
    return (
      <div className="flex h-20 w-20 items-center justify-center rounded-lg border border-operator-border bg-operator-bg text-[9px] text-operator-muted">
        {attachment.filename}
      </div>
    );
  }
  return (
    <a href={src} target="_blank" rel="noreferrer" title={attachment.filename}>
      <img
        src={src}
        alt={attachment.filename}
        className="max-h-48 max-w-[16rem] rounded-lg border border-operator-border object-cover"
      />
    </a>
  );
}

function MessageAttachments({ attachments }: { attachments: ChatAttachment[] }) {
  if (!attachments.length) return null;
  return (
    <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
      {attachments.map((attachment) => (
        <AttachmentImage key={attachment.attachmentId} attachment={attachment} />
      ))}
    </div>
  );
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [copied, setCopied] = useState(false);
  const setAppError = useAppStore((state) => state.setAppError);
  const tools = useAppStore((state) => state.tools);
  const toolById = new Map(tools.map((tool) => [tool.id, tool]));

  const handleCopy = async () => {
    try {
      await copyTextToClipboard(formatMessageForClipboard(message));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to copy message.');
    }
  };

  if (isSystem) {
    return (
      <div className="animate-message my-3 flex justify-center">
        <div className="px-3 py-1 text-[11px] text-operator-muted border border-operator-border/60 rounded-full whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="message-user animate-message group relative flex w-full justify-end pb-4">
        <div className="relative max-w-[80%] min-w-0">
          {message.requestedToolIds && message.requestedToolIds.length > 0 ? (
            <div className="mb-1.5 flex flex-wrap justify-end gap-1">
              {message.requestedToolIds.map((toolId) => {
                const tool = toolById.get(toolId);
                return (
                  <span
                    key={toolId}
                    title={tool?.description || toolId}
                    className="inline-flex items-center gap-1 rounded-full border border-operator-accent/18 bg-operator-accent/6 px-2 py-1 text-[9.5px] text-operator-muted"
                  >
                    <span className="text-operator-accent"><ToolGlyph toolId={toolId} /></span>
                    {tool ? toolDisplayName(tool) : toolId}
                  </span>
                );
              })}
            </div>
          ) : null}
          {message.attachments && message.attachments.length > 0 && (
            <MessageAttachments attachments={message.attachments} />
          )}
          {message.content && (
            <div className="rounded-2xl rounded-br-md border border-operator-accent/15 bg-operator-accent/5 px-3.5 py-2 text-[13.5px] leading-relaxed text-operator-text font-sans break-words">
              <ChatMarkdown content={message.content} density="compact" />
            </div>
          )}
          <div className="mt-1 flex items-center justify-end gap-1.5 px-1 text-[10px] text-operator-muted/70">
            <button
              type="button"
              onClick={() => void handleCopy()}
              aria-label={copied ? 'Copied message' : 'Copy message'}
              className="opacity-40 transition-opacity duration-150 hover:opacity-100 focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 inline-flex items-center gap-0.5 hover:text-operator-text"
              title="Copy message"
            >
              {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
            </button>
            <span className="tabular-nums">{formatTimestamp(message.timestamp)}</span>
          </div>
        </div>
      </div>
    );
  }

  // Assistant
  return (
    <div className="message-assistant animate-message group relative flex w-full pb-5 pl-4">
      <div className="message-rail absolute left-2 top-2 bottom-2 w-px bg-operator-border/55" />
      <div className="message-marker absolute left-[5px] top-2 w-2 h-2 rounded-full bg-operator-accent/60 ring-2 ring-operator-bg z-10" />

      <div className="relative min-w-0 flex-1">
        <div className="message-heading mb-1 flex items-center gap-2 px-1 text-[10px] font-medium uppercase tracking-[0.14em] text-operator-muted/85">
          <span>Assistant</span>
          <span className="tabular-nums text-operator-muted/55">{formatTimestamp(message.timestamp)}</span>
        </div>

        <div className="message-body px-1 text-[13.5px] leading-relaxed text-operator-text font-sans break-words">
          {message.optimistic && !message.content && !message.parts?.length ? (
            <div
              className="mt-2.5 flex min-h-8 items-center"
              role="status"
              aria-label="Waiting for assistant response"
            >
              <Spinner variant="orbit" className="text-operator-muted" />
            </div>
          ) : null}

          {message.parts && message.parts.length > 0 ? (
            <TurnTrail
              parts={message.parts}
              isLive={!!(message.optimistic && message.state === 'delta')}
              sessionKey={message.sessionKey}
              runId={message.runId}
            />
          ) : (
            <>
              {message.content && <ChatMarkdown content={message.content} />}
              {message.toolExecution && (
                <div className="mt-2.5 flex flex-col gap-1.5">
                  <ToolTraceCard trace={message.toolExecution} />
                </div>
              )}
            </>
          )}

          {message.errorMessage && !message.content && !message.parts?.length && (
            <div className="rounded-lg border border-operator-error/25 bg-operator-error/5 px-3 py-2 text-[12.5px] text-operator-error whitespace-pre-wrap">
              {message.errorMessage}
            </div>
          )}
        </div>

        <div className="mt-1 flex items-center px-1 text-[10px] text-operator-muted/70">
          <button
            type="button"
            onClick={() => void handleCopy()}
            aria-label={copied ? 'Copied message' : 'Copy message'}
            className="opacity-40 transition-opacity duration-150 hover:opacity-100 focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 inline-flex items-center gap-0.5 hover:text-operator-text"
            title="Copy message"
          >
            {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
      </div>
    </div>
  );
}
