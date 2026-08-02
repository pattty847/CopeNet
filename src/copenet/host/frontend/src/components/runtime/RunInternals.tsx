/**
 * RunInternals — the one per-turn internals view, mounted in three places:
 * in-thread under an assistant message, in the Observability run inspector, and
 * (next) in the session-level right drawer.
 *
 * The constraint from the plan is **insight without obstruction**: one muted
 * collapsed line per turn, expanding in place — not into a side panel, because
 * the question is about *this* message. Sections follow the order a person
 * actually debugs, which is also this repo's documented triage order: what it
 * saw, what it did, why it stopped, raw trace.
 *
 * Nothing here may shift layout while a run streams; expansion is always
 * user-initiated.
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Eye, FileCode2, Flag, Wrench } from 'lucide-react';
import type { SessionArtifactRecord } from '../../types/backend';
import type { InternalsFact, RunInternals as RunInternalsModel } from '../../runtime/runInternals';
import { RunStepCard } from './RunStepCard';
import { paletteClasses, toneClass, type InternalsPalette } from './internalsPalette';

/** "Not fetched yet" and "confirmed to have no trace" are different, and saying
 *  the second while the first is true prints a falsehood as fact. */
export type TraceStatus = 'loading' | 'absent' | 'loaded';

interface Props {
  internals: RunInternalsModel;
  artifacts?: SessionArtifactRecord[];
  palette?: InternalsPalette;
  traceStatus?: TraceStatus;
}

function FactRows({ facts, palette }: { facts: InternalsFact[]; palette: InternalsPalette }) {
  const classes = paletteClasses(palette);
  return (
    <dl className="space-y-1">
      {facts.map((fact) => (
        <div key={fact.label} className="flex items-baseline gap-2 text-[11px]">
          <dt className={`w-28 shrink-0 ${classes.mutedSoft}`}>{fact.label}</dt>
          <dd className={`font-mono ${classes.text}`}>{fact.value}</dd>
          {fact.hint && <dd className={`min-w-0 truncate text-[10px] ${classes.mutedSoft}`}>{fact.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

function Section({
  icon: Icon,
  title,
  palette,
  children,
}: {
  icon: typeof Eye;
  title: string;
  palette: InternalsPalette;
  children: React.ReactNode;
}) {
  const classes = paletteClasses(palette);
  return (
    <section>
      <h4 className={`mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] ${classes.mutedSoft}`}>
        <Icon className="h-3 w-3" />
        {title}
      </h4>
      {children}
    </section>
  );
}

/** The four sections. Exported on its own so the Observability inspector can
 *  render the body without the collapsed line wrapping it. */
export function RunInternalsBody({ internals, artifacts = [], palette = 'operator', traceStatus }: Props) {
  const classes = paletteClasses(palette);
  const [rawOpen, setRawOpen] = useState(false);
  const artifactsById = new Map(artifacts.map((artifact) => [artifact.artifactId, artifact]));
  const status: TraceStatus = traceStatus ?? (internals.hasTrace ? 'loaded' : 'absent');

  return (
    <div className="space-y-4">
      {internals.verdicts.length > 0 && (
        <ul className="space-y-1">
          {internals.verdicts.map((verdict) => (
            <li key={verdict.id} className={`flex items-start gap-1.5 text-[11px] leading-4 ${toneClass(verdict.tone, classes)}`}>
              <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-current" />
              {verdict.text}
            </li>
          ))}
        </ul>
      )}

      <Section icon={Eye} title="What it saw" palette={palette}>
        {internals.saw.detailAvailable ? (
          <div className="space-y-2.5">
            {internals.saw.promptBlocks.length > 0 && <FactRows facts={internals.saw.promptBlocks} palette={palette} />}
            {internals.saw.contextWindow.length > 0 && <FactRows facts={internals.saw.contextWindow} palette={palette} />}
            {internals.saw.offeredToolIds.length > 0 && (
              <div>
                <div className={`mb-1 text-[10px] ${classes.mutedSoft}`}>
                  {internals.saw.offeredToolIds.length} tools offered
                </div>
                <div className="flex flex-wrap gap-1">
                  {internals.saw.offeredToolIds.map((toolId) => (
                    <span
                      key={toolId}
                      className={`rounded ${classes.surface} px-1.5 py-0.5 font-mono text-[10px] ${classes.muted}`}
                    >
                      {toolId}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {internals.saw.withheldNote && (
              <p className="text-[10.5px] text-amber-400">{internals.saw.withheldNote}</p>
            )}
          </div>
        ) : (
          <p className={`text-[11px] ${classes.mutedSoft}`}>
            {status === 'loading'
              ? 'Loading trace…'
              : internals.hasTrace
                ? 'This run recorded no prompt or manifest detail.'
                : 'No trace for this run — it predates always-on tracing, or was purged.'}
          </p>
        )}
      </Section>

      <Section icon={Wrench} title="What it did" palette={palette}>
        {internals.did.length > 0 ? (
          <div className="space-y-1.5">
            {internals.did.map((step, index) => (
              <RunStepCard
                key={`${step.callId || step.toolId}-${index}`}
                step={step}
                artifact={step.artifactId ? artifactsById.get(step.artifactId) : undefined}
                palette={palette}
              />
            ))}
          </div>
        ) : (
          <p className={`text-[11px] ${classes.mutedSoft}`}>No tools were called.</p>
        )}
      </Section>

      <Section icon={Flag} title="Why it stopped" palette={palette}>
        <p className={`text-[11px] leading-4 ${toneClass(internals.stopped.tone, classes)}`}>{internals.stopped.text}</p>
      </Section>

      {internals.hasTrace && (
        <Section icon={FileCode2} title="Raw trace" palette={palette}>
          <button
            type="button"
            onClick={() => setRawOpen((value) => !value)}
            className={`focus-ring flex items-center gap-1.5 rounded text-[11px] ${classes.muted} ${classes.hoverText}`}
          >
            {rawOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {internals.events.length} trace events
          </button>
          {rawOpen && (
            <pre className={`mt-1.5 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg ${classes.surface} p-2.5 font-mono text-[10px] leading-4 ${classes.text}`}>
              {JSON.stringify(internals.events, null, 2)}
            </pre>
          )}
        </Section>
      )}
    </div>
  );
}

/** The collapsed one-liner: `model · 4.2s · 2 tools · 12k ctx`. Muted unless
 *  something deserves attention. */
export function RunInternalsLine({
  internals,
  palette = 'operator',
  expanded,
  onToggle,
  loading = false,
}: {
  internals: RunInternalsModel;
  palette?: InternalsPalette;
  expanded: boolean;
  onToggle: () => void;
  loading?: boolean;
}) {
  const classes = paletteClasses(palette);
  const { stat } = internals;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={`focus-ring inline-flex max-w-full items-center gap-1.5 rounded px-1 py-0.5 text-[10px] transition-colors ${classes.mutedSoft} ${classes.hoverText} ${classes.hover}`}
      title="What happened inside this turn. The token figure is the message-history estimate; the system prompt and tool schemas are sized separately inside."
    >
      {expanded ? <ChevronDown className="h-2.5 w-2.5 shrink-0" /> : <ChevronRight className="h-2.5 w-2.5 shrink-0" />}
      <span className="truncate font-mono tabular-nums">
        {stat.model} · {stat.durationLabel} · {stat.toolCount} tool{stat.toolCount === 1 ? '' : 's'}
        {stat.contextLabel ? ` · ${stat.contextLabel}` : ''}
      </span>
      {stat.badges.map((badge) => (
        <span key={badge.label} className={`shrink-0 ${toneClass(badge.tone, classes)}`}>
          · {badge.label}
        </span>
      ))}
      {loading && <span className="shrink-0">· loading…</span>}
    </button>
  );
}

/** Line + in-place expansion. This is the in-thread mount. */
export function RunInternalsPanel({
  internals,
  artifacts,
  palette = 'operator',
  traceStatus,
  expanded,
  onToggle,
  loading = false,
}: Props & { expanded: boolean; onToggle: () => void; loading?: boolean }) {
  const classes = paletteClasses(palette);
  return (
    <div className="min-w-0">
      <RunInternalsLine
        internals={internals}
        palette={palette}
        expanded={expanded}
        onToggle={onToggle}
        loading={loading}
      />
      {expanded && (
        <div className={`mt-2 rounded-lg border ${classes.borderSoft} ${classes.panel} px-3 py-3`}>
          <RunInternalsBody internals={internals} artifacts={artifacts} palette={palette} traceStatus={traceStatus} />
        </div>
      )}
    </div>
  );
}
