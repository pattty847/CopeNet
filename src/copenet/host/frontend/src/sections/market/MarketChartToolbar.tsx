import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { MM } from './marketUi';

type Timeframe = 'D' | 'W' | 'M';

export function MarketChartToolbar({
  alertControl,
  financialControls,
  timeframe,
  onTimeframe,
}: {
  alertControl: ReactNode;
  financialControls: ReactNode;
  timeframe: Timeframe;
  onTimeframe: (timeframe: Timeframe) => void;
}) {
  const railRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const rail = railRef.current;
    const content = contentRef.current;
    if (!rail || !content) return;
    const update = () => {
      const maxScroll = rail.scrollWidth - rail.clientWidth;
      setCanScrollLeft(rail.scrollLeft > 2);
      setCanScrollRight(maxScroll > 2 && rail.scrollLeft < maxScroll - 2);
    };
    update();
    rail.addEventListener('scroll', update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(rail);
    observer.observe(content);
    return () => {
      rail.removeEventListener('scroll', update);
      observer.disconnect();
    };
  }, []);

  const nudge = (direction: -1 | 1) => {
    const rail = railRef.current;
    if (!rail) return;
    rail.scrollBy({ left: direction * Math.max(120, rail.clientWidth * 0.72), behavior: 'smooth' });
  };

  return (
    <div className="market-chart-toolbar" role="toolbar" aria-label="Chart tools">
      <button
        type="button"
        className="market-chart-toolbar__nudge market-chart-toolbar__nudge--left"
        aria-label="Show previous chart tools"
        disabled={!canScrollLeft}
        onClick={() => nudge(-1)}
      >
        <ChevronLeft size={15} />
      </button>
      <div
        ref={railRef}
        className="market-chart-toolbar__rail"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') nudge(-1);
          if (event.key === 'ArrowRight') nudge(1);
        }}
      >
        <div ref={contentRef} className="market-chart-toolbar__content">
          {alertControl}
          {financialControls}
          <div className="market-chart-toolbar__timeframes" aria-label="Chart timeframe">
            {([
              ['D', '1D'],
              ['W', '1W'],
              ['M', '1M'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => onTimeframe(key)}
                aria-pressed={timeframe === key}
                style={{
                  cursor: 'pointer',
                  border: 'none',
                  borderRadius: 5,
                  padding: '4px 11px',
                  font: '600 10px Inter',
                  background: timeframe === key ? MM.accent : 'transparent',
                  color: timeframe === key ? '#1a1205' : MM.muted,
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <button
        type="button"
        className="market-chart-toolbar__nudge market-chart-toolbar__nudge--right"
        aria-label="Show more chart tools"
        disabled={!canScrollRight}
        onClick={() => nudge(1)}
      >
        <ChevronRight size={15} />
      </button>
    </div>
  );
}
