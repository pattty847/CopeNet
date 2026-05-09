import React from 'react';

interface SectionErrorBoundaryProps {
  sectionName: string;
  children: React.ReactNode;
}

interface SectionErrorBoundaryState {
  error: Error | null;
}

export class SectionErrorBoundary extends React.Component<SectionErrorBoundaryProps, SectionErrorBoundaryState> {
  state: SectionErrorBoundaryState = {
    error: null,
  };

  static getDerivedStateFromError(error: Error): SectionErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`SectionErrorBoundary(${this.props.sectionName})`, error, info);
  }

  componentDidUpdate(prevProps: SectionErrorBoundaryProps) {
    if (prevProps.sectionName !== this.props.sectionName && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div className="flex h-full min-h-[24rem] items-center justify-center px-6 py-8">
        <div className="w-full max-w-2xl rounded-3xl border border-operator-error/25 bg-operator-error/5 p-6 text-left shadow-shell-xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-operator-error">
            Interface Error
          </div>
          <h2 className="mt-3 text-[24px] font-semibold text-operator-text">
            The {this.props.sectionName} surface hit a runtime error.
          </h2>
          <p className="mt-3 text-[13px] leading-6 text-operator-muted">
            CopeNet caught the failure instead of leaving the page blank. Reload the page if needed, and share the message below so we can fix it cleanly.
          </p>
          <pre className="mt-4 overflow-x-auto rounded-2xl border border-operator-border bg-operator-bg/80 px-4 py-3 text-[12px] leading-6 text-operator-text whitespace-pre-wrap break-words">
            {this.state.error.stack || this.state.error.message}
          </pre>
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-xl border border-operator-border bg-operator-panel px-4 py-2 text-[12px] font-semibold text-operator-text transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
            >
              Reload page
            </button>
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="rounded-xl border border-operator-border bg-operator-panel px-4 py-2 text-[12px] font-semibold text-operator-text transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  }
}
