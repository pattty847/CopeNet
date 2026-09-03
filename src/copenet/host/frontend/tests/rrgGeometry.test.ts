import assert from 'node:assert/strict';
import test from 'node:test';
import { rrgLabelSize } from '../src/sections/market/rrgGeometry';

test('RRG labels stay 9.5px with exactly 1px of highlight at every layout width and zoom', () => {
  for (const widthScale of [0.3, 0.8, 1, 1.5]) {
    for (const zoom of [1, 2, 5]) {
      const normal = rrgLabelSize(false, zoom, widthScale) * zoom * widthScale;
      const highlighted = rrgLabelSize(true, zoom, widthScale) * zoom * widthScale;
      assert.ok(Math.abs(normal - 9.5) < 1e-10);
      assert.ok(Math.abs(highlighted - normal - 1) < 1e-10);
    }
  }
});
