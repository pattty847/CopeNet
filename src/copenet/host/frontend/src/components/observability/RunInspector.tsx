import { useMemo, useState } from 'react';
import { Brain, Code2, FileText, MessageSquareText } from 'lucide-react';
import type { MessagePart, ObservabilityRunDetail } from '../../types/backend';
import { formatRunDuration } from '../../lib/formatting';
import { buildRunInternals } from '../../runtime/runInternals';
import { RunInternalsBody } from '../runtime/RunInternals';
import { RunStepCard } from '../runtime/RunStepCard';
import { ChatMarkdown } from '../ChatMarkdown';

type InspectorTab = 'internals' | 'timeline' | 'input' | 'raw';

// "Internals" is first because it answers the question; Timeline is the
// narrative read of the same run, and the old standalone Tools tab is now the
// "What it did" section inside Internals rather than a fourth rendering of the
// same tool steps.
const tabs: Array<{ id: InspectorTab; label: string }> = [
  { id: 'internals', label: 'Internals' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'input', label: 'Model input' },
  { id: 'raw', label: 'Raw trace' },
];

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-shell-bg p-3 font-mono text-[11px] leading-5 text-shell-text">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function Timeline({ detail }: { detail: ObservabilityRunDetail }) {
  const stepsByCall = new Map(detail.run.toolSteps.map((step) => [step.callId || step.toolId, step]));
  const artifactsById = new Map(detail.artifacts.map((artifact) => [artifact.artifactId, artifact]));
  const renderedCalls = new Set<string>();
  const parts = detail.messages.flatMap((message) => message.role === 'assistant' ? (message.parts || []) : []);

  const timelineParts: MessagePart[] = parts.length > 0 ? parts : [];
  return (
    <div className="space-y-5">
      <section className="border-l-2 border-shell-accent pl-3">
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-accent">
          <MessageSquareText className="h-3.5 w-3.5" /> User request
        </div>
        <p className="mt-1 whitespace-pre-wrap text-[12px] leading-5 text-shell-text">{detail.run.userMessage}</p>
      </section>

      {timelineParts.map((part, index) => {
        if (part.kind === 'thinking') {
          return (
            <section key={`thinking-${index}`} className="border-l-2 border-violet-400/50 pl-3">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-300">
                <Brain className="h-3.5 w-3.5" />
                {part.source === 'raw' ? 'Raw reasoning' : 'Reasoning summary'}
              </div>
              <div className="mt-1 text-[12px] leading-5 text-shell-text">
                <ChatMarkdown content={part.text} density="compact" />
              </div>
            </section>
          );
        }
        if (part.kind === 'tool_call') {
          const key = part.callId || part.toolId;
          if (renderedCalls.has(key)) return null;
          renderedCalls.add(key);
          const step = stepsByCall.get(key) || detail.run.toolSteps.find((candidate) => candidate.toolId === part.toolId && !renderedCalls.has(candidate.callId || ''));
          if (step) renderedCalls.add(step.callId || step.toolId);
          return step ? <RunStepCard key={`tool-${key}-${index}`} step={step} artifact={step.artifactId ? artifactsById.get(step.artifactId) : undefined} palette="shell" /> : null;
        }
        if (part.kind === 'tool_result' || part.kind === 'tool_batch') return null;
        if (part.kind === 'text' && part.content.trim()) {
          return (
            <section key={`text-${index}`} className="border-l-2 border-shell-success/50 pl-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-success">Assistant response</div>
              <div className="mt-1 text-[12px] leading-5 text-shell-text">
                <ChatMarkdown content={part.content} density="compact" />
              </div>
            </section>
          );
        }
        return null;
      })}

      {detail.run.toolSteps.filter((step) => !renderedCalls.has(step.callId || step.toolId)).map((step, index) => (
        <RunStepCard key={`fallback-tool-${step.callId || index}`} step={step} artifact={step.artifactId ? artifactsById.get(step.artifactId) : undefined} palette="shell" />
      ))}

      {timelineParts.every((part) => part.kind !== 'text') && detail.run.outputSummary && (
        <section className="border-l-2 border-shell-success/50 pl-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-success">Assistant response</div>
          <p className="mt-1 text-[12px] leading-5 text-shell-text">{detail.run.outputSummary}</p>
        </section>
      )}
    </div>
  );
}

export function RunInspector({ detail, loading, error }: { detail: ObservabilityRunDetail | null; loading: boolean; error: string | null }) {
  const [tab, setTab] = useState<InspectorTab>('internals');
  const inputSnapshot = useMemo(
    () => detail?.events.find((event) => event.event === 'model_input_snapshot')?.payload || null,
    [detail],
  );

  if (loading) return <div className="grid min-h-[34rem] place-items-center text-[12px] text-shell-muted">Loading run evidence…</div>;
  if (error) return <div className="grid min-h-[34rem] place-items-center px-6 text-center text-[12px] text-shell-error">{error}</div>;
  if (!detail) {
    return (
      <div className="grid min-h-[34rem] place-items-center px-6 text-center">
        <div>
          <FileText className="mx-auto h-6 w-6 text-shell-muted" />
          <p className="mt-3 text-[13px] text-shell-text">Select a run to inspect it.</p>
          <p className="mt-1 text-[11px] text-shell-muted">Tool calls, reasoning summaries, prompts, and raw trace events appear here.</p>
        </div>
      </div>
    );
  }

  const run = detail.run;
  return (
    <article className="min-w-0 bg-shell-panel">
      <header className="border-b border-shell-border px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.15em] text-shell-muted">
              <span className="text-shell-accent">{run.provider}</span>
              <span>{run.model || 'default model'}</span>
              <span>{formatRunDuration(run.startedAt, run.completedAt)}</span>
              <span>{run.toolSteps.length} tools</span>
            </div>
            <h2 className="mt-2 line-clamp-2 text-[15px] font-medium leading-5 text-shell-text">{run.userMessage || run.outputSummary}</h2>
          </div>
          {/* Three states, not two: lifecycle-traced is now the norm, and a run with
              no trace at all means the file was pruned or predates always-on tracing. */}
          <div
            className={`rounded-full px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.15em] ${detail.debugCaptured ? 'bg-amber-400/10 text-amber-300' : 'bg-shell-bg text-shell-muted'}`}
            title={
              detail.debugCaptured
                ? 'Prompts, tool arguments, and tool result bodies were captured for this run.'
                : detail.lifecycleCaptured
                  ? 'Lifecycle events were traced. Turn on Debug capture to also record prompts and tool payloads.'
                  : 'No trace file for this run — it was purged, or it ran before tracing became unconditional.'
            }
          >
            {detail.debugCaptured ? 'debug captured' : detail.lifecycleCaptured ? 'lifecycle traced' : 'no trace'}
          </div>
        </div>
        <nav className="mt-4 flex gap-1 overflow-x-auto" aria-label="Run inspector views">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`focus-ring rounded-md px-3 py-1.5 text-[11px] font-medium transition-colors ${tab === item.id ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted hover:text-shell-text'}`}
              aria-current={tab === item.id ? 'page' : undefined}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="max-h-[48rem] overflow-y-auto px-4 py-5 sm:px-5">
        {tab === 'timeline' && <Timeline detail={detail} />}
        {tab === 'input' && (
          inputSnapshot ? <JsonBlock value={inputSnapshot} /> : (
            <div className="rounded-lg border border-dashed border-shell-border px-5 py-8 text-center">
              <Code2 className="mx-auto h-5 w-5 text-shell-muted" />
              <p className="mt-3 text-[12px] text-shell-text">No model-input snapshot for this run.</p>
              <p className="mt-1 text-[11px] leading-5 text-shell-muted">Enable Debug capture, then start a new run. Existing runs cannot be captured retroactively.</p>
            </div>
          )
        )}
        {tab === 'internals' && (
          <RunInternalsBody
            internals={buildRunInternals(run, detail.events)}
            artifacts={detail.artifacts}
            palette="shell"
          />
        )}
        {tab === 'raw' && (
          detail.events.length > 0 ? <JsonBlock value={detail.events} /> : <p className="py-10 text-center text-[12px] text-shell-muted">Raw events were not captured for this run.</p>
        )}
      </div>
    </article>
  );
}
