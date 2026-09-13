import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown } from 'lucide-react';

/** Follow appended output only until the reader moves away from the bottom. */
export function TranscriptScroll({ sessionKey, className, children }: {
  sessionKey: string; className: string; children: ReactNode;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const lastTop = useRef(0);
  const [showLatest, setShowLatest] = useState(false);

  const jumpToLatest = () => {
    following.current = true;
    const node = viewport.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
      lastTop.current = node.scrollTop;
    }
    setShowLatest(false);
  };

  useLayoutEffect(() => { jumpToLatest(); }, [sessionKey]);
  useLayoutEffect(() => {
    const node = viewport.current;
    const body = content.current;
    if (!node || !body) return;
    const resize = new ResizeObserver(() => {
      if (following.current) {
        node.scrollTop = node.scrollHeight;
        lastTop.current = node.scrollTop;
      }
    });
    resize.observe(body);
    resize.observe(node);
    return () => resize.disconnect();
  }, []);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={viewport}
        data-testid="transcript-scroll"
        className={`min-h-0 flex-1 overflow-y-auto overscroll-contain ${className}`}
        style={{ scrollBehavior: 'auto', scrollbarGutter: 'stable' }}
        onWheel={(event) => {
          if (event.deltaY < 0) { following.current = false; setShowLatest(true); }
        }}
        onScroll={() => {
          const node = viewport.current!;
          const nearBottom = node.scrollHeight - node.clientHeight - node.scrollTop <= 4;
          // Even a small upward gesture pauses following immediately.
          if (node.scrollTop < lastTop.current) following.current = false;
          else if (nearBottom) following.current = true;
          lastTop.current = node.scrollTop;
          setShowLatest(!following.current);
        }}
      >
        <div ref={content}>{children}</div>
      </div>
      {showLatest && (
        <button type="button" onClick={jumpToLatest}
          className="absolute bottom-3 left-1/2 flex min-h-11 -translate-x-1/2 items-center gap-2 rounded-full border border-operator-border bg-operator-panel px-4 text-xs text-operator-text shadow-lg hover:text-operator-accent focus-visible:outline-2 focus-visible:outline-operator-accent">
          <ArrowDown className="h-4 w-4" /> Jump to latest
        </button>
      )}
    </div>
  );
}
