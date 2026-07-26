import { ArrowUpRight } from 'lucide-react';

import { useAppStore } from '../../store/useAppStore';
import type { ActivityProofMember } from '../../runtime/types';

/** Pretty-print the exact arguments a tool was called with. */
function formatArguments(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

function clippedArgumentNote(truncated: Record<string, number>): string {
  const keys = Object.keys(truncated);
  if (keys.length === 0) return '';
  const parts = keys.map((key) => `${key} clipped from ${truncated[key].toLocaleString()} chars`);
  return parts.join(' · ');
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 font-mono text-[9.5px] uppercase tracking-wider text-operator-muted/55">{children}</div>
  );
}

function Block({ children }: { children: React.ReactNode }) {
  return (
    <pre className="max-h-64 overflow-auto rounded border border-operator-border/35 bg-operator-panel/25 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-operator-text/80 whitespace-pre-wrap break-words">
      {children}
    </pre>
  );
}

/**
 * The expanded proof for one tool call: what it was called with, and what came back.
 *
 * Before this, a tool step rendered as a single truncated line and was only
 * clickable when it happened to produce an artifact — so most calls were dead
 * ends in the drawer. Arguments and result body both reach the run record now,
 * and this is where they get read.
 */
export function ToolCallDetail({ member }: { member: ActivityProofMember }) {
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  const args = member.arguments && Object.keys(member.arguments).length > 0 ? member.arguments : null;
  const argNote = member.argumentsTruncated ? clippedArgumentNote(member.argumentsTruncated) : '';
  const output = member.fullOutput;

  return (
    <div className="ml-4 mt-0.5 mb-1 space-y-2 border-l border-operator-border/30 pl-2">
      {member.toolId && (
        <div className="font-mono text-[10px] text-operator-accent/75">{member.toolId}</div>
      )}

      {args ? (
        <div>
          <SectionLabel>Arguments</SectionLabel>
          <Block>{formatArguments(args)}</Block>
          {argNote && (
            <div className="mt-0.5 font-mono text-[9.5px] text-operator-muted/55">{argNote}</div>
          )}
        </div>
      ) : (
        <div className="font-mono text-[10px] text-operator-muted/45">Called with no arguments</div>
      )}

      <div>
        <SectionLabel>Result</SectionLabel>
        {output ? (
          <>
            <Block>{output}</Block>
            {member.fullOutputChars != null && (
              <div className="mt-0.5 font-mono text-[9.5px] text-operator-muted/55">
                Showing {output.length.toLocaleString()} of {member.fullOutputChars.toLocaleString()} chars
                {member.artifactId ? ' — full output saved as an artifact' : ''}
              </div>
            )}
          </>
        ) : (
          <div className="font-mono text-[10px] text-operator-muted/45">No output recorded</div>
        )}
      </div>

      {member.policySummary && (
        <div>
          <SectionLabel>Policy</SectionLabel>
          <div className="font-mono text-[10px] text-operator-muted/70">{member.policySummary}</div>
        </div>
      )}

      {member.artifactId && (
        <button
          type="button"
          onClick={() => setInspectorTarget({ kind: 'artifact', artifactId: member.artifactId! })}
          className="flex items-center gap-1 font-mono text-[10px] text-operator-accent/80 transition-colors hover:text-operator-accent"
        >
          Open full artifact
          <ArrowUpRight className="h-2.5 w-2.5" />
        </button>
      )}
    </div>
  );
}
