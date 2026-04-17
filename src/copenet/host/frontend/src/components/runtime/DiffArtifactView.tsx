import { Check, FileCode2, FilePlus2, FileMinus2, X } from 'lucide-react';
import type { Artifact, ArtifactDiffBlock } from '../../runtime/types';

interface DiffArtifactViewProps {
  artifact: Artifact;
}

function DiffBlock({ block }: { block: ArtifactDiffBlock }) {
  return (
    <div className="rounded-xl border border-operator-border bg-operator-bg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-operator-border bg-operator-panel/50">
        <FileCode2 className="w-3.5 h-3.5 text-operator-muted" />
        <span className="font-mono text-[11px] text-operator-text">{block.path}</span>
        <span className="font-mono text-[10px] text-operator-muted/70 ml-auto">
          {block.hunkHeader}
        </span>
      </div>
      <div className="font-mono text-[11px] leading-relaxed">
        {block.lines.map((line, idx) => {
          const tone =
            line.kind === 'add'
              ? 'bg-operator-success/8 text-operator-success'
              : line.kind === 'remove'
              ? 'bg-operator-error/8 text-operator-error'
              : 'text-operator-muted';
          const prefix = line.kind === 'add' ? '+' : line.kind === 'remove' ? '−' : ' ';
          return (
            <div key={idx} className={`flex px-3 py-0.5 ${tone}`}>
              <span className="w-4 shrink-0 select-none opacity-60">{prefix}</span>
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
    <div className="space-y-3">
      {/* Summary strip */}
      <div className="rounded-xl border border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
            Patch Plan
          </span>
          <span className="text-[10px] font-mono text-operator-muted/70">{artifact.id}</span>
          {artifact.runId && (
            <span className="text-[10px] font-mono text-operator-muted/60 ml-auto">
              {artifact.runId}
            </span>
          )}
        </div>
        <div className="text-[14px] text-operator-text font-medium leading-snug">
          {artifact.title}
        </div>
        <div className="text-[12px] text-operator-muted mt-1 leading-relaxed">
          {artifact.oneLine}
        </div>
        <div className="flex items-center gap-3 mt-2 text-[11px]">
          <span className="flex items-center gap-1 text-operator-success">
            <FilePlus2 className="w-3 h-3" /> +{totalAdditions}
          </span>
          <span className="flex items-center gap-1 text-operator-error">
            <FileMinus2 className="w-3 h-3" /> −{totalDeletions}
          </span>
          <span className="text-operator-muted">· {artifact.files?.length ?? 0} files</span>
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

      {/* Approval row — placeholder */}
      <div className="flex items-center gap-2 pt-1">
        <button
          disabled
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-operator-success/15 text-operator-success text-[12px] font-medium border border-operator-success/30 cursor-not-allowed opacity-70"
          title="Apply — wiring pending"
        >
          <Check className="w-3.5 h-3.5" /> Apply
        </button>
        <button
          disabled
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-operator-panel text-operator-muted text-[12px] font-medium border border-operator-border cursor-not-allowed opacity-70"
          title="Reject — wiring pending"
        >
          <X className="w-3.5 h-3.5" /> Reject
        </button>
        <span className="text-[10px] text-operator-muted ml-2 leading-tight">
          Apply / reject will wire to the runtime patch API when it lands.
        </span>
      </div>
    </div>
  );
}
