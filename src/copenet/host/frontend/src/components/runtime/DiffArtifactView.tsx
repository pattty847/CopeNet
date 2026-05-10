import { FileCode2, FilePlus2, FileMinus2, Info } from 'lucide-react';
import type { Artifact, ArtifactDiffBlock } from '../../runtime/types';

interface DiffArtifactViewProps {
  artifact: Artifact;
}

function DiffBlock({ block }: { block: ArtifactDiffBlock }) {
  return (
    <div className="rounded-xl border border-operator-border bg-operator-bg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-operator-border bg-operator-panel/40">
        <FileCode2 className="w-3.5 h-3.5 text-operator-muted/85" />
        <span className="font-mono text-[11px] text-operator-text/90 truncate">{block.path}</span>
        <span className="font-mono text-[10px] text-operator-muted/65 ml-auto shrink-0">
          {block.hunkHeader}
        </span>
      </div>
      <div className="font-mono text-[11.5px] leading-[1.55]">
        {block.lines.map((line, idx) => {
          const tone =
            line.kind === 'add'
              ? 'bg-operator-success/8 text-operator-success'
              : line.kind === 'remove'
              ? 'bg-operator-error/8 text-operator-error'
              : 'text-operator-muted/90';
          const prefix = line.kind === 'add' ? '+' : line.kind === 'remove' ? '−' : ' ';
          return (
            <div key={idx} className={`flex px-3 py-0.5 ${tone}`}>
              <span className="w-4 shrink-0 select-none opacity-50">{prefix}</span>
              <span className="whitespace-pre-wrap break-words">{line.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DiffArtifactView({ artifact }: DiffArtifactViewProps) {
  const totalAdditions = artifact.files?.reduce((s, f) => s + f.additions, 0) ?? 0;
  const totalDeletions = artifact.files?.reduce((s, f) => s + f.deletions, 0) ?? 0;

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="rounded-2xl border border-operator-border bg-operator-panel/30 px-3.5 py-3">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-operator-accent">
            Patch Plan
          </span>
          <span className="ml-auto inline-flex items-center gap-2 text-[10px] font-mono text-operator-muted/70">
            <span title={artifact.id} className="truncate max-w-[120px]">{artifact.id}</span>
            {artifact.runId && <span className="text-operator-muted/45">· {artifact.runId}</span>}
          </span>
        </div>
        <div className="text-[15px] text-operator-text font-semibold leading-snug">
          {artifact.title}
        </div>
        {artifact.oneLine && (
          <div className="text-[12px] text-operator-muted mt-1.5 leading-relaxed">
            {artifact.oneLine}
          </div>
        )}
        <div className="mt-2.5 flex items-center gap-3 text-[11px] tabular-nums">
          <span className="inline-flex items-center gap-1 rounded-full bg-operator-success/10 px-2 py-0.5 text-operator-success">
            <FilePlus2 className="w-3 h-3" /> {totalAdditions}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-operator-error/10 px-2 py-0.5 text-operator-error">
            <FileMinus2 className="w-3 h-3" /> {totalDeletions}
          </span>
          <span className="text-operator-muted/85">{artifact.files?.length ?? 0} files</span>
        </div>
      </div>

      {/* Files touched */}
      {artifact.files && artifact.files.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
            Files Touched
          </div>
          <ul className="space-y-1">
            {artifact.files.map((f) => (
              <li
                key={f.path}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-operator-border bg-operator-panel/30 text-[11px]"
              >
                <FileCode2 className="w-3 h-3 text-operator-muted shrink-0" />
                <span className="font-mono text-operator-text truncate flex-1">{f.path}</span>
                <span className="text-operator-success font-mono shrink-0">+{f.additions}</span>
                <span className="text-operator-error font-mono shrink-0">−{f.deletions}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Diff blocks */}
      {artifact.diffBlocks && artifact.diffBlocks.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
            Diff Preview
          </div>
          <div className="space-y-2">
            {artifact.diffBlocks.map((b, idx) => (
              <DiffBlock key={idx} block={b} />
            ))}
          </div>
        </div>
      )}

      {/* Wiring-pending notice */}
      <div className="flex items-start gap-2 rounded-xl border border-dashed border-operator-border/70 bg-operator-panel/20 px-3 py-2 text-[11px] leading-5 text-operator-muted/85">
        <Info className="mt-0.5 h-3 w-3 shrink-0 text-operator-muted/70" />
        <span>Apply and reject will wire to the runtime patch API when it lands.</span>
      </div>
    </div>
  );
}
