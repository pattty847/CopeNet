import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { IndicatorSettings } from '../src/sections/market/indicators/IndicatorSettings';
import { indicatorById } from '../src/sections/market/indicators/registry';
import { addIndicator } from '../src/sections/market/indicators/state';

test('parallel indicator settings bind labels to unique controls', () => {
  const definition = indicatorById('ema')!;
  const instances = addIndicator(addIndicator([], 'ema'), 'ema');
  const noop = () => {};
  const html = renderToStaticMarkup(
    <>
      {instances.map((instance) => (
        <IndicatorSettings
          key={instance.instanceId}
          definition={definition}
          instance={instance}
          onConfigure={noop}
          onStyle={noop}
          onDuplicate={noop}
          onReset={noop}
          onRemove={noop}
        />
      ))}
    </>,
  );

  const ids = [...html.matchAll(/id="([^"]+-ind-period)"/g)].map((match) => match[1]);
  const labels = [...html.matchAll(/for="([^"]+-ind-period)"/g)].map((match) => match[1]);
  assert.equal(ids.length, 2);
  assert.equal(new Set(ids).size, 2);
  assert.deepEqual(labels, ids);
});
