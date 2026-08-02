/**
 * RunStepCard — one tool call, collapsed to a line, expandable to arguments and
 * result. Lifted out of RunInspector so the Agents thread and the Observability
 * workspace render a tool call identically instead of diverging.
 *
 * Blocked and failed are different states and read differently: a block is a
 * policy decision the operator may want to change, a failure is a bug. The old
 * card collapsed both to a red X.
 */

import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, Shield, Wrench, XCircle } from 'lucide-react';
import type { RunStep, SessionArtifactRecord, ToolResultPreview } from '../../types/backend';
import { isBlockedStep, isFailedStep } from '../../runtime/runInternals';
import { paletteClasses, type InternalsPalette } from './internalsPalette';

function previewText(preview: ToolResultPreview): string {
  if (preview.type === 'raw') return preview.text;
  if (preview.type === 'file_read') return preview.lines.join('\n');
  if (preview.type === 'diff') return preview.diff;
  if (preview.type === 'repo_search') {
    return preview.matches.map((match) => `${match.path}:${match.line} ${match.snippet}`).join('\n');
  }
  return JSON.stringify(preview, null, 2);
}

/** The argument that identifies the call — what a person scans the list for. */
export function stepTarget(step: RunStep): string | null {
  if (step.target) return step.target;
  const args = step.arguments || {};
  for (const key of ['command', 'path', 'pattern', 'query', 'url', 'uri', 'symbol', 'file']) {
    const value = args[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

export function RunStepCard({
  step,
  artifact,
  palette = 'operator',
}: {
  step: RunStep;
  artifact?: SessionArtifactRecord;
  palette?: InternalsPalette;
}) {
  const [open, setOpen] = useState(false);
  const classes = paletteClasses(palette);
  const blocked = isBlockedStep(step);
  const failed = isFailedStep(step);
  const StatusIcon = blocked ? Shield : failed ? XCircle : CheckCircle2;
  const statusClass = blocked ? 'text-amber-400' : failed ? classes.error : classes.success;
  const target = stepTarget(step);

  return (
    <section className={`border-l-2 ${classes.borderSoft} pl-3`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`focus-ring flex w-full items-start gap-2 rounded-md px-1 py-1 text-left transition-colors ${classes.hover}`}
        aria-expanded={open}
      >
        {open
          ? <ChevronDown className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${classes.mutedSoft}`} />
          : <ChevronRight className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${classes.mutedSoft}`} />}
        <Wrench className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${classes.accent}`} />
        <span className="min-w-0 flex-1">
          <span className={`flex flex-wrap items-baseline gap-x-2 font-mono text-[11px] ${classes.text}`}>
            {step.toolId}
            {target && (
              <span className={`min-w-0 truncate text-[10.5px] ${classes.mutedSoft}`} title={target}>
                {target}
              </span>
            )}
          </span>
          <span className={`mt-0.5 block text-[11px] leading-4 ${classes.muted}`}>
            {step.summary || (blocked ? 'Blocked by policy.' : 'Tool completed.')}
          </span>
        </span>
        <StatusIcon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${statusClass}`} />
      </button>
      {open && (
        <div className={`mt-2 space-y-3 pb-2 pl-8 text-[11px] ${classes.muted}`}>
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.18em]">Arguments</div>
            <pre className={`max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg ${classes.surface} p-2.5 font-mono leading-5 ${classes.text}`}>
              {JSON.stringify(step.arguments || {}, null, 2)}
            </pre>
            {step.argumentsTruncated && Object.keys(step.argumentsTruncated).length > 0 && (
              <p className={`mt-1 text-[10px] ${classes.mutedSoft}`}>
                Clipped for storage: {Object.entries(step.argumentsTruncated).map(([key, chars]) => `${key} (${chars} chars)`).join(', ')}
              </p>
            )}
          </div>
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.18em]">Result</div>
            <div className={`max-h-80 overflow-auto rounded-lg ${classes.surface} p-2.5 font-mono leading-5 ${classes.text}`}>
              {artifact
                ? <pre className="whitespace-pre-wrap break-words">{artifact.body}</pre>
                : step.preview
                  ? <pre className="whitespace-pre-wrap break-words">{previewText(step.preview)}</pre>
                  : <span className={classes.mutedSoft}>No result body was retained.</span>}
            </div>
          </div>
          {(step.error || step.policyDecision) && (
            <div className={failed ? classes.error : blocked ? 'text-amber-400' : classes.muted}>
              {step.error || `${step.policyDecision}: ${step.policySummary || 'No policy detail.'}`}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
