import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_CHART_STYLE, normalizeChartStyle } from '../src/sections/market/chartStyle/store';
import { restoreIndicator, styleIndicator, type IndicatorInstance } from '../src/sections/market/indicators/state';

test('a stored chart style is checked once at the storage boundary and falls back field by field', () => {
  const style = normalizeChartStyle({
    candles: { up: '#00ff00', down: 'red' }, volume: { opacity: 7 }, overlay: { color: '#123456', width: 9, style: 'wavy' },
    drawingDefaults: { trendline: { color: '#abcdef', lineWidth: 3, lineStyle: 'dotted', fillOpacity: 2 }, zone: { color: 'nope' } },
  });
  assert.deepEqual(style.candles, { up: '#00ff00', down: DEFAULT_CHART_STYLE.candles.down });
  assert.equal(style.volume.opacity, 1);
  assert.deepEqual(style.overlay, { color: '#123456', width: DEFAULT_CHART_STYLE.overlay.width, style: 'solid' });
  assert.deepEqual(style.drawingDefaults.trendline, { color: '#abcdef', lineWidth: 3, lineStyle: 'dotted', fillOpacity: 0.6 });
  assert.deepEqual(style.drawingDefaults.zone, {});
  assert.deepEqual(normalizeChartStyle(null), DEFAULT_CHART_STYLE);
});

test('an indicator output can be switched off on its own, and Cancel puts the instance back exactly', () => {
  const instance: IndicatorInstance = { instanceId: 'a', indicatorId: 'ema', config: { length: 20 }, visible: true };
  const styled = styleIndicator([instance], 'a', 'value', { visible: false, lineWidth: 3 });
  assert.deepEqual(styled[0].styles, { value: { visible: false, lineWidth: 3 } });
  assert.deepEqual(restoreIndicator(styled, instance), [instance]);
});
