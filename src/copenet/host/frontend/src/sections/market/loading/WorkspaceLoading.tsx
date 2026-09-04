import type { ReactNode } from 'react';
import './workspaceLoading.css';

export function LoadingStatus({ label }: { label: string }) {
  return (
    <div className="workspace-loading__status" role="status">
      <span aria-hidden="true" />
      {label}
    </div>
  );
}

export function SkeletonLines({ rows = 5 }: { rows?: number }) {
  return (
    <div className="workspace-loading__lines" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index}>
          <i />
          <i />
          <i />
        </div>
      ))}
    </div>
  );
}

export function SkeletonPanel({ kind = 'rows' }: { kind?: 'rows' | 'chart' }) {
  return (
    <div className={`workspace-loading__panel workspace-loading__panel--${kind}`} aria-hidden="true">
      <div className="workspace-loading__heading">
        <i />
        <i />
      </div>
      {kind === 'chart' ? <div className="workspace-loading__chart" /> : <SkeletonLines />}
    </div>
  );
}

/** One animation per loading region; the outlines themselves stay still. */
export function WorkspaceLoading({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="workspace-loading" aria-busy="true">
      <LoadingStatus label={label} />
      <div className="workspace-loading__outlines" aria-hidden="true">
        {children}
      </div>
    </div>
  );
}

export function WorkspaceLoadError({ title, error, onRetry }: { title: string; error: string; onRetry: () => void }) {
  return (
    <div className="workspace-load-error" role="alert">
      <div>
        <strong>{title}</strong>
        <p>{error}</p>
      </div>
      <button type="button" className="tw-btn" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
