import type { IChartApi, UTCTimestamp } from 'lightweight-charts';
import type { ChartSelection } from '../chartAgent/types';
import { leftAxisWidth } from '../chartDecorations';

/** Time-only selection spans price and indicator panes without creating chart data. */
export function createRangeOverlay(container: HTMLDivElement, chart: IChartApi) {
  const band = document.createElement('div');
  band.dataset.chartSelection = '';
  band.setAttribute('aria-hidden', 'true');
  Object.assign(band.style, { position: 'absolute', pointerEvents: 'none', top: '0', zIndex: '2',
    background: 'rgba(251,148,35,.09)', borderInline: '1px solid rgba(251,148,35,.6)', display: 'none' });
  container.appendChild(band);
  return {
    update(selection: ChartSelection | null | undefined) {
      const scale = chart.timeScale();
      const from = selection ? scale.timeToCoordinate(selection.from as UTCTimestamp) : null;
      const to = selection ? scale.timeToCoordinate(selection.to as UTCTimestamp) : null;
      if (from == null || to == null) { band.style.display = 'none'; return; }
      const width = chart.paneSize(0).width;
      const left = Math.max(0, Math.min(from, to) - 3);
      const right = Math.min(width, Math.max(from, to) + 3);
      Object.assign(band.style, { display: right > left ? 'block' : 'none', left: `${leftAxisWidth(chart) + left}px`,
        width: `${Math.max(0, right - left)}px`, bottom: `${scale.height()}px` });
    },
    destroy() { band.remove(); },
  };
}
