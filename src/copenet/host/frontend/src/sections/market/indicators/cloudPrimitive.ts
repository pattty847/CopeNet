import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import type { IndicatorPoint } from './compute';

interface CloudPoint {
  t: number;
  primary: number;
  signal: number;
}

interface ProjectedCloudPoint extends CloudPoint {
  x: number;
  primaryY: number;
  signalY: number;
}

/** A chart-native fill between two indicator lines. It is attached to the primary series so
 *  Lightweight Charts supplies the same time scale, price transform, pane clipping and DPR
 *  handling as the lines themselves. */
export class IndicatorCloudPrimitive implements ISeriesPrimitive<Time> {
  private state: SeriesAttachedParameter<Time> | null = null;
  private points: CloudPoint[] = [];

  constructor(
    private readonly bullishColor: string,
    private readonly bearishColor: string,
  ) {}

  attached(state: SeriesAttachedParameter<Time>): void {
    this.state = state;
  }

  detached(): void {
    this.state = null;
  }

  setData(primary: IndicatorPoint[], signal: IndicatorPoint[]): void {
    const signalByTime = new Map(signal.map((point) => [point.t, point.value]));
    this.points = primary.flatMap((point) => {
      const signalValue = signalByTime.get(point.t);
      return signalValue == null ? [] : [{ t: point.t, primary: point.value, signal: signalValue }];
    });
    this.state?.requestUpdate();
  }

  private readonly renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      const state = this.state;
      if (!state || this.points.length < 2) return;
      target.useMediaCoordinateSpace(({ context, mediaSize }) => {
        const projected = this.points.map((point): ProjectedCloudPoint | null => {
          const x = state.chart.timeScale().timeToCoordinate(point.t as UTCTimestamp);
          const primaryY = state.series.priceToCoordinate(point.primary);
          const signalY = state.series.priceToCoordinate(point.signal);
          if (x == null || primaryY == null || signalY == null) return null;
          if (![x, primaryY, signalY].every(Number.isFinite)) return null;
          return { ...point, x, primaryY, signalY };
        });

        context.save();
        try {
          context.beginPath();
          context.rect(0, 0, mediaSize.width, mediaSize.height);
          context.clip();
          for (let index = 1; index < projected.length; index += 1) {
            const left = projected[index - 1];
            const right = projected[index];
            if (!left || !right) continue;
            paintInterval(context, left, right, this.bullishColor, this.bearishColor);
          }
        } finally {
          context.restore();
        }
      });
    },
  };

  private readonly views: IPrimitivePaneView[] = [{ zOrder: () => 'bottom', renderer: () => this.renderer }];

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}

/** Paint one trapezoid, splitting it at the exact crossover so a regime change never colours
 *  a whole candle interval with the state from only one endpoint. */
function paintInterval(
  context: CanvasRenderingContext2D,
  left: ProjectedCloudPoint,
  right: ProjectedCloudPoint,
  bullishColor: string,
  bearishColor: string,
): void {
  // Use screen-space spreads: Lightweight Charts connects projected points with straight
  // segments even on a logarithmic scale, so this is the intersection the operator sees.
  const leftSpread = left.signalY - left.primaryY;
  const rightSpread = right.signalY - right.primaryY;
  if (leftSpread * rightSpread < 0) {
    const fraction = leftSpread / (leftSpread - rightSpread);
    const crossingX = left.x + (right.x - left.x) * fraction;
    const crossingY = left.primaryY + (right.primaryY - left.primaryY) * fraction;
    const crossing = { x: crossingX, primaryY: crossingY, signalY: crossingY };
    fillTrapezoid(context, left, crossing, leftSpread > 0 ? bullishColor : bearishColor);
    fillTrapezoid(context, crossing, right, rightSpread > 0 ? bullishColor : bearishColor);
    return;
  }
  fillTrapezoid(context, left, right, leftSpread >= 0 ? bullishColor : bearishColor);
}

function fillTrapezoid(
  context: CanvasRenderingContext2D,
  left: Pick<ProjectedCloudPoint, 'x' | 'primaryY' | 'signalY'>,
  right: Pick<ProjectedCloudPoint, 'x' | 'primaryY' | 'signalY'>,
  color: string,
): void {
  context.beginPath();
  context.moveTo(left.x, left.primaryY);
  context.lineTo(right.x, right.primaryY);
  context.lineTo(right.x, right.signalY);
  context.lineTo(left.x, left.signalY);
  context.closePath();
  context.fillStyle = color;
  context.fill();
}
