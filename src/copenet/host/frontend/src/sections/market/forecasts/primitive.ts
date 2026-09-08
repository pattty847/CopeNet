import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, PrimitiveHoveredItem, SeriesAttachedParameter } from 'lightweight-charts';
import { paintDrawing } from '../drawings/primitive';
import type { ChartObject } from '../chartAgent/types';
import { forecastDisplay, forecastLevels, forecastDate } from './model';
import { forecastSetup, type ForecastBridge, type ForecastRecord } from './types';

/** Separate immutable layer; no drawing mutation/undo or future timeline points. */
export class ForecastPrimitive implements ISeriesPrimitive {
  private state: SeriesAttachedParameter | null = null;
  private bridge: ForecastBridge | undefined;
  private comparison = false;
  private receipts = new Map<string, string>();
  private pending = new Map<string, string>();
  private retryAfter = new Map<string, number>();
  private hits: { id: string; y: number }[] = [];
  constructor(private readonly visible: () => boolean) {}
  attached(state: SeriesAttachedParameter) { this.state = state; }
  detached() { this.state = null; this.hits = []; }
  private receipt(record: ForecastRecord, status: 'rendered' | 'hidden' | 'failed', reason?: string) {
    const bridge = this.bridge;
    if (!bridge || !this.visible() || document.visibilityState !== 'visible') return;
    const key = `${record.revision}:${status}:${reason ?? ''}`;
    if (this.receipts.get(record.forecastId) === key) return;
    queueMicrotask(() => {
      if (this.bridge !== bridge || !this.state || this.receipts.get(record.forecastId) === key) return;
      if (this.pending.has(record.forecastId) || Date.now() < (this.retryAfter.get(record.forecastId) ?? 0)) return;
      this.pending.set(record.forecastId, key);
      Promise.resolve().then(() => bridge.onRendered({ forecastId: record.forecastId, revision: record.revision, viewId: bridge.viewId, status, reason }))
        .then(() => { this.receipts.set(record.forecastId, key); this.retryAfter.delete(record.forecastId); })
        .catch(() => { this.retryAfter.set(record.forecastId, Date.now() + 5000); })
        .finally(() => { this.pending.delete(record.forecastId); });
    });
  }
  setState(bridge: ForecastBridge | undefined, comparison: boolean) {
    this.bridge = bridge; this.comparison = comparison;
    if (comparison && bridge) for (const record of bridge.records.filter((row) => forecastSetup(row))) this.receipt(record, 'hidden', 'Forecast levels are hidden in comparison mode.');
    this.state?.requestUpdate();
  }
  private readonly renderer: IPrimitivePaneRenderer = { draw: (target) => {
    const state = this.state; const bridge = this.bridge;
    this.hits = [];
    if (!state || !bridge || this.comparison) return;
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const record of [...bridge.records].reverse()) {
        const setup = forecastSetup(record);
        if (!setup) continue;
        const display = forecastDisplay(record, bridge.splitFingerprint);
        if (bridge.hidden.has(record.forecastId) || display.reason) {
          this.receipt(record, 'hidden', display.reason ?? 'Forecast overlay hidden by operator.'); continue;
        }
        context.save();
        try {
          context.beginPath(); context.rect(0, 0, mediaSize.width, mediaSize.height); context.clip();
          const levels = forecastLevels(record, display.factor);
          const positions = levels.map((level) => ({ ...level, y: state.series.priceToCoordinate(level.price) }));
          if (positions.some((level) => level.y == null || !Number.isFinite(level.y))) throw new Error('Forecast price coordinates unavailable.');
          if (positions.every((level) => level.y! < 0) || positions.every((level) => level.y! > mediaSize.height)) {
            this.receipt(record, 'hidden', 'Forecast levels are outside the visible price range.'); continue;
          }
          const entry = positions[0].y!;
          const bands = [{ y: positions[1].y!, color: '#e46b66' }, { y: positions[positions.length - 1].y!, color: '#78bd91' }];
          for (const band of bands) {
            context.globalAlpha = 0.055; context.fillStyle = band.color;
            context.fillRect(0, Math.min(entry, band.y), mediaSize.width, Math.abs(entry - band.y));
          }
          for (const zone of setup.zones) {
            const a = state.series.priceToCoordinate(zone.lower / display.factor), b = state.series.priceToCoordinate(zone.upper / display.factor);
            if (a == null || b == null) continue;
            context.globalAlpha = 0.08; context.fillStyle = '#8fb8e8';
            context.fillRect(0, Math.min(a, b), mediaSize.width, Math.abs(a - b));
            context.globalAlpha = 1; context.font = '10px monospace'; context.textAlign = 'right';
            context.fillText(zone.label, mediaSize.width - 6, Math.min(a, b) + 12, mediaSize.width - 12);
            context.textAlign = 'left';
          }
          context.globalAlpha = 1;
          for (const level of positions) {
            const object: ChartObject = { id: `${record.forecastId}:${level.id}`, kind: 'level', anchors: [{ t: 0, value: level.price }],
              label: `${level.label} ${level.price.toFixed(2)}`, color: level.color, timeframe: 'D', visible: true, rationale: '', evidence: [], owner: { kind: 'agent' } };
            paintDrawing(context, { object, points: [{ x: 2, y: level.y! }], width: mediaSize.width, height: mediaSize.height }, false);
            if (level.y! >= 0 && level.y! <= mediaSize.height) this.hits.push({ id: record.forecastId, y: level.y! });
          }
          context.fillStyle = '#99958a'; context.font = '10px monospace';
          context.fillText(`${setup.direction} ${forecastDate(record.publishedAt)} · due ${forecastDate(record.deadlineAt)}`, Math.max(6, mediaSize.width - 215), 16, 205);
          this.receipt(record, 'rendered');
        } catch (reason) { this.receipt(record, 'failed', String(reason)); }
        finally { context.restore(); }
      }
    });
  } };
  private readonly views: IPrimitivePaneView[] = [{ zOrder: () => 'normal', renderer: () => this.renderer }];
  paneViews() { return this.views; }
  hitTest(_x: number, y: number): PrimitiveHoveredItem | null {
    const hit = [...this.hits].reverse().find((level) => Math.abs(level.y - y) < 8);
    return hit ? { externalId: `forecast:${hit.id}`, zOrder: 'normal', cursorStyle: 'pointer' } : null;
  }
}
