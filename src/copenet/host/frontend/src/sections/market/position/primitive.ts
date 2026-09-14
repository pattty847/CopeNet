import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter } from 'lightweight-charts';
import type { HeldPosition } from './types';
import { money, percent, scenario } from './model';

/** Price-pane coordinates update with every paint, including logarithmic scale and vertical pan. */
export class PositionPrimitive implements ISeriesPrimitive {
  private attachedState: SeriesAttachedParameter | null = null;
  private cursorPrice: number | null = null;
  constructor(private position: HeldPosition, private shading: boolean) {}
  attached(state: SeriesAttachedParameter) { this.attachedState = state; }
  detached() { this.attachedState = null; }
  cursor(price: number | null) { this.cursorPrice = price; this.attachedState?.requestUpdate(); }
  private readonly renderer: IPrimitivePaneRenderer = { draw: (target) => {
    const state = this.attachedState;
    if (!state) return;
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      context.save();
      context.beginPath(); context.rect(0, 0, mediaSize.width, mediaSize.height); context.clip();
      const { avg_cost: cost, last_price: last } = this.position;
      if (this.shading && cost != null && last != null) {
        const a = state.series.priceToCoordinate(cost), b = state.series.priceToCoordinate(last);
        if (a != null && b != null) {
          context.fillStyle = (last - cost) * this.position.quantity >= 0 ? 'rgba(120,189,145,.045)' : 'rgba(228,107,102,.045)';
          context.fillRect(0, Math.min(a, b), mediaSize.width, Math.abs(a - b));
        }
      }
      if (this.cursorPrice != null) {
        const estimate = scenario(this.position, this.cursorPrice);
        if (estimate) {
          const text = `At ${money(this.cursorPrice, this.position.currency)}: ${money(estimate.dollars, this.position.currency)} (${percent(estimate.percent)}) · current shares`;
          context.font = '11px monospace';
          const width = Math.min(mediaSize.width - 16, context.measureText(text).width + 16);
          context.fillStyle = '#151516'; context.fillRect(mediaSize.width - width - 8, mediaSize.height - 32, width, 24);
          context.fillStyle = '#d6d2c7'; context.textAlign = 'right';
          context.fillText(text, mediaSize.width - 16, mediaSize.height - 16, Math.max(1, width - 16));
        }
      }
      context.restore();
    });
  } };
  private readonly views: IPrimitivePaneView[] = [{ zOrder: () => 'normal', renderer: () => this.renderer }];
  paneViews() { return this.views; }
}
